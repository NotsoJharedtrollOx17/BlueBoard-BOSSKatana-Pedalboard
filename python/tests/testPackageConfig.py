import json
import tempfile
import unittest
from pathlib import Path

from blueboard_macro_handler.config import ConfigError, loadConfig


class PackageConfigTests(unittest.TestCase):
    def writeConfig(self, value) -> Path:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as temporary:
            json.dump(value, temporary)
            path = Path(temporary.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def testLoadsTypedKeyboardAndUnmappedActions(self) -> None:
        path = self.writeConfig({"bindings": [{"cc": 20, "action": {"type": "keyboard", "keys": ["ctrl", "r"]}}, {"cc": 22, "action": None}]})
        config = loadConfig(path)
        self.assertEqual(config.bindings[0].action.keys, ("CTRL", "R"))
        self.assertIsNone(config.bindings[1].action)

    def testLegacyActionNamesRemainCompatible(self) -> None:
        config = loadConfig(self.writeConfig({"bindings": [{"cc": 20, "action": "ctrlShiftR"}]}))
        self.assertEqual(config.bindings[0].action.keys, ("CTRL", "SHIFT", "R"))

    def testRejectsInvalidCcAndUdpPort(self) -> None:
        for binding in ({"cc": 128, "action": None}, {"cc": 20, "action": {"type": "udp", "port": 70000}}):
            with self.subTest(binding=binding), self.assertRaises(ConfigError):
                loadConfig(self.writeConfig({"bindings": [binding]}))
