import unittest

from blueboard_macro_handler.config import ActionSpec, KatanaConfig
from blueboard_macro_handler.katana.controller import KatanaController
from blueboard_macro_handler.models import RunMetrics


class FakeTransport:
    def __init__(self) -> None:
        self.opened = []
        self.sent = []
        self.closed = 0
        self.failNext = False

    def listOutputNames(self):
        return ("KATANA",)

    def open(self, name):
        self.opened.append(name)

    def send(self, command):
        if self.failNext:
            self.failNext = False
            raise RuntimeError("transport failed")
        self.sent.append(command.data)

    def close(self):
        self.closed += 1


class KatanaControllerTests(unittest.TestCase):
    def makeController(self, presetStates=None):
        config = KatanaConfig(
            "KATANA",
            midiChannel=1,
            effectControls={"booster": 16, "delay": 19},
            presetStates=presetStates or {},
        )
        transport = FakeTransport()
        metrics = RunMetrics()
        return KatanaController(config, transport, metrics), transport, metrics

    def testPresetSelectionLoadsExpectedEffectState(self) -> None:
        controller, transport, metrics = self.makeController({0: {"booster": False, "delay": True}})
        controller.selectPreset(0)
        self.assertEqual(transport.sent, [(0xC0, 0)])
        self.assertEqual(controller.currentPreset, 0)
        self.assertEqual(controller.effectState, {"booster": False, "delay": True})
        self.assertEqual(metrics.katanaCommands, 1)

    def testKnownStateTogglesDeterministically(self) -> None:
        controller, transport, _metrics = self.makeController({0: {"booster": False}})
        controller.selectPreset(0)
        controller.toggleEffect("booster")
        controller.toggleEffect("booster")
        self.assertEqual(transport.sent, [(0xC0, 0), (0xB0, 16, 127), (0xB0, 16, 0)])

    def testUnknownStateFailsBeforeOpeningTransport(self) -> None:
        controller, transport, _metrics = self.makeController()
        with self.assertRaisesRegex(RuntimeError, "state is unknown"):
            controller.toggleEffect("booster")
        self.assertEqual(transport.opened, [])

    def testSetEffectStateDoesNotNeedPredictedInitialState(self) -> None:
        controller, transport, _metrics = self.makeController()
        controller.execute(ActionSpec("katana", command="setEffectState", effect="delay", enabled=True))
        self.assertEqual(transport.sent, [(0xB0, 19, 127)])
        self.assertTrue(controller.effectState["delay"])

    def testFailureClosesAndNextCommandReopens(self) -> None:
        controller, transport, metrics = self.makeController()
        transport.failNext = True
        with self.assertRaisesRegex(RuntimeError, "transport failed"):
            controller.selectPreset(0)
        controller.selectPreset(1)
        self.assertEqual(transport.opened, ["KATANA", "KATANA"])
        self.assertEqual(metrics.katanaCommandFailures, 1)
        self.assertEqual(metrics.katanaReconnects, 1)

    def testCloseReleasesTransport(self) -> None:
        controller, transport, _metrics = self.makeController()
        controller.selectPreset(0)
        controller.close()
        self.assertEqual(transport.closed, 1)
        self.assertFalse(controller.isOpen)


if __name__ == "__main__":
    unittest.main()
