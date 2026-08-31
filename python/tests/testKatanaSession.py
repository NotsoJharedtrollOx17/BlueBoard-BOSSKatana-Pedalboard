import unittest

from blueboard_macro_handler.katana.commands import createSysExData
from blueboard_macro_handler.katana.parameters import parameterDefinitions
from blueboard_macro_handler.katana.session import (
    CURRENT_SELECTION_ADDRESS,
    EDITOR_MODE_ADDRESS,
    KatanaSysExProbe,
)
from blueboard_macro_handler.katana.transport import ReceivedMidiMessage


class FakeDuplexTransport:
    def __init__(self, replies=None) -> None:
        self.inputNames = ("KATANA 1", "KATANA CTRL 3")
        self.outputNames = ("KATANA 1", "KATANA DAW CTRL 2")
        self.inputName = None
        self.outputName = None
        self.callback = None
        self.events = []
        self.sent = []
        self.closed = 0
        self.replies = replies or {}

    def listInputNames(self):
        return self.inputNames

    def listOutputNames(self):
        return self.outputNames

    def openInput(self, name, callback):
        self.events.append(("open-input", name))
        self.inputName = "KATANA 1"
        self.callback = callback

    def open(self, name):
        self.events.append(("open-output", name))
        self.outputName = "KATANA 1"

    def send(self, command):
        self.events.append(("send", command.data))
        self.sent.append(command.data)
        if command.data[7] != 0x11:
            return
        address = command.data[8:12]
        for reply in self.replies.get(address, ()):
            if isinstance(reply, ReceivedMidiMessage):
                self.callback(reply)
            else:
                response = createSysExData(0, reply[0], reply[1]).data
                self.callback(ReceivedMidiMessage("sysex", response[1:-1]))

    def close(self):
        self.closed += 1


class KatanaSessionTests(unittest.TestCase):
    def makeProbe(self, transport, *, target="effect-states", timeoutMs=20, retries=0):
        probe = KatanaSysExProbe(
            transport,
            timeoutMs=timeoutMs,
            retries=retries,
            editorSettleMs=0,
            sleepFunction=lambda _seconds: None,
        )
        probe.open("KATANA 1", "KATANA 1", target=target)
        return probe

    def testEffectProbeOpensInputFirstAndMatchesImmediateReplies(self) -> None:
        replies = {
            definition.address: ((definition.address, (index % 2,)),)
            for index, definition in enumerate(parameterDefinitions.values())
        }
        transport = FakeDuplexTransport(replies)
        probe = self.makeProbe(transport)
        report = probe.probe()
        probe.close()
        self.assertEqual(transport.events[:2], [("open-input", "KATANA 1"), ("open-output", "KATANA 1")])
        self.assertTrue(report.success)
        self.assertEqual(len(report.observations), 6)
        self.assertEqual(report.metrics.katanaSysExRequests, 6)
        self.assertEqual(report.metrics.katanaSysExReplies, 6)
        self.assertEqual([item.decoded for item in report.observations], [False, True, False, True, False, True])

    def testCurrentSelectionAlwaysExitsEditorMode(self) -> None:
        transport = FakeDuplexTransport({CURRENT_SELECTION_ADDRESS: ((CURRENT_SELECTION_ADDRESS, (0, 0)),)})
        probe = self.makeProbe(transport, target="current-selection")
        report = probe.probe()
        self.assertEqual(report.observations[0].decoded, "Panel")
        self.assertEqual(transport.sent[0], createSysExData(0, EDITOR_MODE_ADDRESS, (1,)).data)
        self.assertEqual(transport.sent[-1], createSysExData(0, EDITOR_MODE_ADDRESS, (0,)).data)

        timedOutTransport = FakeDuplexTransport()
        timedOutProbe = self.makeProbe(timedOutTransport, target="current-selection")
        timedOutReport = timedOutProbe.probe()
        self.assertFalse(timedOutReport.success)
        self.assertEqual(timedOutTransport.sent[-1], createSysExData(0, EDITOR_MODE_ADDRESS, (0,)).data)

    def testTimeoutRetriesAreBounded(self) -> None:
        transport = FakeDuplexTransport()
        probe = self.makeProbe(transport, timeoutMs=1, retries=1)
        report = probe.probe()
        self.assertEqual(len(report.failures), 6)
        self.assertEqual(report.metrics.katanaSysExRequests, 12)
        self.assertEqual(report.metrics.katanaSysExTimeouts, 12)
        self.assertEqual(report.metrics.katanaSysExRetries, 6)

    def testWrongAddressDoesNotSatisfyRequest(self) -> None:
        first = next(iter(parameterDefinitions.values()))
        wrong = tuple(parameterDefinitions.values())[1]
        replies = {first.address: ((wrong.address, (0,)), (first.address, (1,)))}
        transport = FakeDuplexTransport(replies)
        probe = self.makeProbe(transport)
        report = probe.probe()
        self.assertTrue(report.observations[0].decoded)
        self.assertEqual(report.metrics.katanaSysExUnexpectedReplies, 1)
        self.assertEqual(len(report.traffic), 8)

    def testInvalidChecksumIsPreservedAndCounted(self) -> None:
        first = next(iter(parameterDefinitions.values()))
        valid = createSysExData(0, first.address, (1,)).data
        invalid = (*valid[:-2], (valid[-2] + 1) & 0x7F, valid[-1])
        message = ReceivedMidiMessage("sysex", invalid[1:-1])
        transport = FakeDuplexTransport({first.address: (message,)})
        probe = self.makeProbe(transport)
        report = probe.probe()
        self.assertEqual(report.metrics.katanaSysExChecksumFailures, 1)
        self.assertTrue(any(record.error == "invalid Roland SysEx checksum" for record in report.traffic))

    def testUnknownBooleanValueIsNotTreatedAsTrue(self) -> None:
        first = next(iter(parameterDefinitions.values()))
        transport = FakeDuplexTransport({first.address: ((first.address, (2,)),)})
        report = self.makeProbe(transport).probe()
        self.assertIsNone(report.observations[0].decoded)
        self.assertIn("unknown strict-boolean value", report.observations[0].error)

    def testCurrentSelectionSendFailureStillAttemptsEditorExit(self) -> None:
        class FailingRequestTransport(FakeDuplexTransport):
            def send(self, command):
                if command.data[7] == 0x11:
                    self.sent.append(command.data)
                    raise RuntimeError("request send failed")
                super().send(command)

        transport = FailingRequestTransport()
        probe = self.makeProbe(transport, target="current-selection")
        with self.assertRaisesRegex(RuntimeError, "request send failed"):
            probe.probe()
        self.assertEqual(transport.sent[-1], createSysExData(0, EDITOR_MODE_ADDRESS, (0,)).data)
        self.assertTrue(any(record.error == "request send failed" for record in probe.report.traffic))

    def testPanelSnapshotRetainsMultipleChunks(self) -> None:
        address = (0x00, 0x00, 0x04, 0x00)
        transport = FakeDuplexTransport(
            {address: ((address, (0, 1, 2)), ((0x00, 0x00, 0x04, 0x20), (3, 4)))}
        )
        probe = self.makeProbe(transport, target="panel-snapshot")
        report = probe.probe()
        self.assertTrue(report.success)
        self.assertEqual(len(report.observations), 2)
        self.assertEqual(report.observations[1].rawData, (3, 4))

    def testFixtureContainsCompleteWireTrafficAndNoUserPath(self) -> None:
        transport = FakeDuplexTransport({CURRENT_SELECTION_ADDRESS: ((CURRENT_SELECTION_ADDRESS, (0, 1)),)})
        report = self.makeProbe(transport, target="current-selection").probe()
        fixture = report.asFixture()
        self.assertEqual(fixture["projectVersion"], "0.8.0")
        self.assertTrue(fixture["traffic"][0]["bytes"].startswith("F0 41"))
        self.assertEqual(fixture["observations"][0]["decoded"], "CH1")


if __name__ == "__main__":
    unittest.main()
