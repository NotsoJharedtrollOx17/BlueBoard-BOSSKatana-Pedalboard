import logging
import unittest

from blueboard_macro_handler.config import ActionSpec, AppConfig, Binding
from blueboard_macro_handler.models import MidiEvent, MidiMessageType, RunMetrics
from blueboard_macro_handler.router import Router


class FakeActions:
    def __init__(self, fail=False): self.values, self.fail = [], fail
    def invoke(self, action):
        if self.fail: raise RuntimeError("test failure")
        self.values.append(action)
        return True
    def releaseAll(self): pass


class FakeLedFeedback:
    def __init__(self): self.values = []
    def setLed(self, cc, isOn, **_kwargs):
        self.values.append((cc, isOn))
        return True


class PackageRouterTests(unittest.TestCase):
    def event(self, value, cc=20, channel=0): return MidiEvent(MidiMessageType.controlChange, channel, cc, value, 1.0)

    def testRunsOnlyConfiguredEdgeAndSuppressesDuplicate(self) -> None:
        actions = FakeActions()
        router = Router(AppConfig((Binding(20, "press", ActionSpec("keyboard", keys=("R",))),)), actions)
        router.handleEvent(self.event(127)); router.handleEvent(self.event(127)); router.handleEvent(self.event(0))
        self.assertEqual(len(actions.values), 1)

    def testUnmappedAndWrongChannelDoNothing(self) -> None:
        actions = FakeActions()
        config = AppConfig((Binding(20, "press", None), Binding(21, "press", ActionSpec("log"), channel=2)))
        router = Router(config, actions)
        router.handleEvent(self.event(127)); router.handleEvent(self.event(127, cc=21))
        self.assertEqual(actions.values, [])

    def testBackendFailureIsCountedAndDoesNotEscape(self) -> None:
        metrics = RunMetrics()
        router = Router(AppConfig((Binding(20, "press", ActionSpec("keyboard", keys=("R",))),)), FakeActions(fail=True), metrics)
        router.handleEvent(self.event(127))
        self.assertEqual(metrics.actionFailures, 1)

    def testLogNamesButtonAndConfiguredMacro(self) -> None:
        actions = FakeActions()
        router = Router(AppConfig((Binding(20, "press", ActionSpec("keyboard", keys=("CTRL", "R"))),)), actions)
        with self.assertLogs("blueboard.router", level=logging.INFO) as captured:
            router.handleEvent(self.event(127))
        self.assertIn("button=A", captured.output[0])
        self.assertIn("edge=press", captured.output[0])
        self.assertIn("source=ble-midi", captured.output[0])
        self.assertIn("macro=CTRL+R", captured.output[0])

    def testUnmappedButtonIsExplicitlyReported(self) -> None:
        router = Router(AppConfig((Binding(22, "press", None),)), FakeActions())
        with self.assertLogs("blueboard.router", level=logging.INFO) as captured:
            router.handleEvent(self.event(127, cc=22))
        self.assertIn("button=C", captured.output[0])
        self.assertIn("macro=unmapped", captured.output[0])

    def testEveryAcceptedButtonEdgeEmitsOneFeedbackRequest(self) -> None:
        ledFeedback = FakeLedFeedback()
        router = Router(AppConfig(()), FakeActions(), ledFeedback=ledFeedback)
        router.handleEvent(self.event(127))
        router.handleEvent(self.event(127))
        router.handleEvent(self.event(0))
        self.assertEqual(ledFeedback.values, [(20, True), (20, False)])

    def testFeedbackIsIndependentFromMacroFailure(self) -> None:
        ledFeedback = FakeLedFeedback()
        config = AppConfig((Binding(20, "press", ActionSpec("keyboard", keys=("R",))),))
        router = Router(config, FakeActions(fail=True), ledFeedback=ledFeedback)
        router.handleEvent(self.event(127))
        self.assertEqual(ledFeedback.values, [(20, True)])

    def testFeedbackIgnoresNonBlueBoardChannelsAndControllers(self) -> None:
        ledFeedback = FakeLedFeedback()
        router = Router(AppConfig(()), FakeActions(), ledFeedback=ledFeedback)
        router.handleEvent(self.event(127, channel=1))
        router.handleEvent(self.event(127, cc=19))
        self.assertEqual(ledFeedback.values, [])
