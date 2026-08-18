import unittest

from blueboard_macro_handler.actions.dispatcher import ActionDispatcher
from blueboard_macro_handler.config import ActionSpec
from blueboard_macro_handler.router import actionDescription


class FakeKatana:
    def __init__(self) -> None:
        self.actions = []
        self.closed = 0

    def execute(self, action) -> None:
        self.actions.append(action)

    def close(self) -> None:
        self.closed += 1


class KatanaActionTests(unittest.TestCase):
    def testDryRunNeverRequiresOrCallsKatana(self) -> None:
        action = ActionSpec("katana", command="selectPreset", preset=0)
        self.assertFalse(ActionDispatcher(execute=False).invoke(action))

    def testExecuteDispatchesAndCloseClosesKatana(self) -> None:
        katana = FakeKatana()
        dispatcher = ActionDispatcher(execute=True, katana=katana)
        action = ActionSpec("katana", command="toggleEffect", effect="booster")
        self.assertTrue(dispatcher.invoke(action))
        dispatcher.close()
        self.assertEqual(katana.actions, [action])
        self.assertEqual(katana.closed, 1)

    def testExecutionWithoutConfiguredKatanaFailsClearly(self) -> None:
        action = ActionSpec("katana", command="selectPreset", preset=0)
        with self.assertRaisesRegex(RuntimeError, "not configured"):
            ActionDispatcher(execute=True).invoke(action)

    def testRouterDescriptionContainsSemanticKatanaTarget(self) -> None:
        self.assertEqual(
            actionDescription(ActionSpec("katana", command="selectPreset", preset=0)),
            "katana:selectPreset:0",
        )
        self.assertEqual(
            actionDescription(ActionSpec("katana", command="toggleEffect", effect="delay")),
            "katana:toggleEffect:delay",
        )


if __name__ == "__main__":
    unittest.main()
