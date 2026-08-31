import importlib.util
import unittest
from pathlib import Path

from blueboard_macro_handler.actions.dispatcher import ActionDispatcher
from blueboard_macro_handler.config import ActionSpec


class PackageActionTests(unittest.TestCase):
    def testLogActionIsHarmlessInDryRunAndActiveModes(self) -> None:
        action = ActionSpec("log", message="diagnostic")
        self.assertFalse(ActionDispatcher(execute=False).invoke(action))
        self.assertFalse(ActionDispatcher(execute=True).invoke(action))

    def testUnknownRuntimeActionFailsClosed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported action type"):
            ActionDispatcher(execute=True).invoke(ActionSpec("unknown"))

    def testMacroBackendModulesAreAbsent(self) -> None:
        self.assertIsNone(importlib.util.find_spec("blueboard_macro_handler.actions.linux"))
        self.assertIsNone(importlib.util.find_spec("blueboard_macro_handler.actions.windows"))
        self.assertIsNone(importlib.util.find_spec("blueboard_macro_handler.actions.base"))

    def testMacroDependenciesAndExtrasAreAbsent(self) -> None:
        project = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8").casefold()
        self.assertNotIn("linux =", project)
        self.assertNotIn("all =", project)
        self.assertNotIn("evdev", project)
        self.assertNotIn("uinput", project)


if __name__ == "__main__":
    unittest.main()
