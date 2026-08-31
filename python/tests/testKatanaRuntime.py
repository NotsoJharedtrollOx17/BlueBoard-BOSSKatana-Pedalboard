import threading
import unittest
from contextlib import ExitStack
from dataclasses import replace
from unittest.mock import patch

from blueboard_macro_handler.config import ActionSpec, KatanaConfig, StateSyncConfig
from blueboard_macro_handler.katana.commands import createSysExData
from blueboard_macro_handler.katana.parameters import parameterDefinitions
from blueboard_macro_handler.katana.runtime import KatanaRuntime, deriveGroupState
from blueboard_macro_handler.katana.transport import ReceivedMidiMessage
from blueboard_macro_handler.models import RunMetrics

productionDefinitions = {
    name: replace(
        definition,
        firmwareRange="4.00",
        evidence="capturedMkI",
        readAccess="production",
    )
    for name, definition in parameterDefinitions.items()
}


class RuntimeTransport:
    def __init__(self, values=None) -> None:
        self.values = values or {name: False for name in productionDefinitions}
        self.callback = None
        self.events = []
        self.sent = []
        self.closed = 0
        self.failNextStandardSend = False
        self.blockStandardSend: threading.Event | None = None
        self.releaseStandardSend = threading.Event()

    def listInputNames(self):
        return ("KATANA IN",)

    def listOutputNames(self):
        return ("KATANA OUT",)

    def openInput(self, name, callback):
        self.events.append(("open-input", name))
        self.callback = callback

    def open(self, name):
        self.events.append(("open-output", name))

    def send(self, command):
        data = command.data
        self.sent.append(data)
        if len(data) > 8 and data[7] == 0x11:
            address = data[8:12]
            for name, definition in productionDefinitions.items():
                if definition.address == address and name in self.values:
                    value = 1 if self.values[name] else 0
                    reply = createSysExData(0, address, (value,)).data
                    self.callback(ReceivedMidiMessage("sysex", reply[1:-1]))
                    return
            return
        if self.blockStandardSend is not None:
            self.blockStandardSend.set()
            self.releaseStandardSend.wait(1)
        if self.failNextStandardSend:
            self.failNextStandardSend = False
            raise RuntimeError("transport failed")

    def close(self):
        self.closed += 1
        self.callback = None


class KatanaRuntimeTests(unittest.TestCase):
    def makeRuntime(self, values=None, *, timeoutMs=50):
        config = KatanaConfig(
            "KATANA OUT",
            model="katana100",
            firmware="4.00",
            effectControls={"booster": 16, "delay": 17, "reverb": 18, "effectLoop": 19},
            presetStates={4: {"booster": False, "delay": True}},
            inputName="KATANA IN",
            stateSync=StateSyncConfig(True, timeoutMs, 0),
        )
        transport = RuntimeTransport(values)
        metrics = RunMetrics()
        return KatanaRuntime(config, transport, metrics), transport, metrics

    def productionPatch(self):
        stack = ExitStack()
        stack.enter_context(patch(
            "blueboard_macro_handler.katana.parameters.parameterDefinitions",
            productionDefinitions,
        ))
        stack.enter_context(patch(
            "blueboard_macro_handler.katana.session.parameterDefinitions",
            productionDefinitions,
        ))
        return stack

    def testStartupPublishesAllSixQueriedValuesAndGroupedState(self) -> None:
        values = {name: False for name in productionDefinitions}
        values["effects.mod.enabled"] = True
        values["effects.delay.enabled"] = True
        runtime, transport, metrics = self.makeRuntime(values)
        with self.productionPatch():
            snapshot = runtime.start().result(timeout=1)
        self.addCleanup(runtime.close)
        self.assertEqual(transport.events[:2], [("open-input", "KATANA IN"), ("open-output", "KATANA OUT")])
        self.assertEqual(len(snapshot.effects), 6)
        self.assertTrue(deriveGroupState(snapshot, "booster"))
        self.assertTrue(deriveGroupState(snapshot, "delay"))
        self.assertEqual(runtime.effectState["booster"], True)
        self.assertEqual(metrics.katanaStateSyncs, 1)
        self.assertEqual(metrics.katanaSysExRequests, 6)

    def testBothOnMembersRemainRepresentable(self) -> None:
        values = {name: False for name in productionDefinitions}
        values["effects.boost.enabled"] = True
        values["effects.mod.enabled"] = True
        runtime, _transport, _metrics = self.makeRuntime(values)
        with self.productionPatch():
            snapshot = runtime.start().result(timeout=1)
        self.addCleanup(runtime.close)
        self.assertTrue(snapshot.effects["effects.boost.enabled"].value)
        self.assertTrue(snapshot.effects["effects.mod.enabled"].value)
        self.assertTrue(deriveGroupState(snapshot, "booster"))

    def testPartialSnapshotGatesOnlyUnknownGroup(self) -> None:
        values = {name: False for name in productionDefinitions}
        values.pop("effects.boost.enabled")
        values.pop("effects.mod.enabled")
        runtime, _transport, metrics = self.makeRuntime(values)
        with self.productionPatch():
            snapshot = runtime.start().result(timeout=1)
            unknown = runtime.execute(ActionSpec("katana", command="toggleEffect", effect="booster"))
            known = runtime.execute(ActionSpec("katana", command="toggleEffect", effect="delay"))
            with self.assertRaisesRegex(RuntimeError, "unknown"):
                unknown.result(timeout=1)
            known.result(timeout=1)
        self.addCleanup(runtime.close)
        self.assertIsNone(deriveGroupState(snapshot, "booster"))
        self.assertFalse(deriveGroupState(snapshot, "delay"))
        self.assertEqual(metrics.katanaStateSyncFailures, 1)

    def testActionsAreQueuedWithoutBlockingCaller(self) -> None:
        runtime, transport, _metrics = self.makeRuntime()
        blocker = threading.Event()
        transport.blockStandardSend = blocker
        with self.productionPatch():
            runtime.start().result(timeout=1)
            future = runtime.execute(ActionSpec("katana", command="selectPreset", preset=4))
            self.assertTrue(blocker.wait(1))
            self.assertFalse(future.done())
            transport.releaseStandardSend.set()
            future.result(timeout=1)
        self.addCleanup(runtime.close)
        self.assertEqual(runtime.currentPreset, 4)
        self.assertEqual(runtime.effectState, {"booster": False, "delay": True})
        self.assertTrue(all(value.source == "stale" for value in runtime.snapshot.effects.values()))

    def testSendFailureInvalidatesAndNextActionReopensAndResynchronizes(self) -> None:
        runtime, transport, metrics = self.makeRuntime()
        with self.productionPatch():
            runtime.start().result(timeout=1)
            transport.failNextStandardSend = True
            failed = runtime.execute(ActionSpec("katana", command="selectPreset", preset=4))
            with self.assertRaisesRegex(RuntimeError, "transport failed"):
                failed.result(timeout=1)
            self.assertFalse(runtime.isOpen)
            recovered = runtime.execute(ActionSpec("katana", command="toggleEffect", effect="booster"))
            recovered.result(timeout=1)
        self.addCleanup(runtime.close)
        self.assertEqual([event[0] for event in transport.events].count("open-input"), 2)
        self.assertEqual(metrics.katanaReconnects, 1)
        self.assertEqual(metrics.katanaInputReconnects, 1)
        self.assertEqual(metrics.katanaStateSyncs, 2)

    def testUnapprovedFirmwareDegradesWithoutSendingAStateDependentToggle(self) -> None:
        runtime, transport, metrics = self.makeRuntime()
        runtime.config = replace(runtime.config, firmware="unknown")
        with self.productionPatch():
            snapshot = runtime.start().result(timeout=1)
            future = runtime.execute(ActionSpec("katana", command="toggleEffect", effect="booster"))
            with self.assertRaisesRegex(RuntimeError, "unknown"):
                future.result(timeout=1)
        self.addCleanup(runtime.close)
        self.assertTrue(all(value.value is None for value in snapshot.effects.values()))
        self.assertEqual(metrics.katanaStateSyncFailures, 1)
        self.assertFalse(any(len(data) == 3 and data[0] & 0xF0 == 0xB0 for data in transport.sent))


if __name__ == "__main__":
    unittest.main()
