import logging
import sys
import unittest
from unittest.mock import patch

from blueboard_macro_handler.actions.dispatcher import ActionDispatcher
from blueboard_macro_handler.actions.windows import Input, WindowsKeyboard, keyCode
from blueboard_macro_handler.config import ActionSpec


class FakeKeyboard:
    def __init__(self): self.combos, self.released, self.closed = [], 0, 0
    def sendCombo(self, keys): self.combos.append(keys)
    def releaseAll(self): self.released += 1
    def close(self): self.closed += 1


class PackageActionsTests(unittest.TestCase):
    def testDryRunHasNoSideEffects(self) -> None:
        keyboard = FakeKeyboard()
        self.assertFalse(ActionDispatcher(False, keyboard).invoke(ActionSpec("keyboard", keys=("ALT", "TAB"))))
        self.assertEqual(keyboard.combos, [])

    def testArbitraryKeyboardComboDispatches(self) -> None:
        keyboard = FakeKeyboard()
        with self.assertLogs("blueboard.actions", level=logging.INFO) as captured:
            self.assertTrue(ActionDispatcher(True, keyboard).invoke(ActionSpec("keyboard", keys=("CTRL", "F12"))))
        self.assertEqual(keyboard.combos, [("CTRL", "F12")])
        self.assertIn("keys=CTRL+F12", captured.output[0])

    def testWindowsAbiAndKeyValidation(self) -> None:
        if sys.platform == "win32":
            self.assertEqual(__import__("ctypes").sizeof(Input), 40)
        self.assertEqual(keyCode("F12"), 0x7B)
        with self.assertRaises(ValueError): keyCode("NOT_A_KEY")

    def testWindowsNativeSequence(self) -> None:
        received = {}
        def send(count, inputs, size): received.update(count=count, size=size); return count
        WindowsKeyboard(send).sendCombo(("CTRL", "R"))
        expectedSize = 40 if sys.platform == "win32" else __import__("ctypes").sizeof(Input)
        self.assertEqual(received, {"count": 4, "size": expectedSize})

    def testLaunchUsesArgumentArrayWithoutShell(self) -> None:
        action = ActionSpec("launch", program="example", args=("--safe",))
        with patch("blueboard_macro_handler.actions.dispatcher.subprocess.Popen") as launch:
            self.assertTrue(ActionDispatcher(True).invoke(action))
        launch.assert_called_once_with(["example", "--safe"], shell=False)
