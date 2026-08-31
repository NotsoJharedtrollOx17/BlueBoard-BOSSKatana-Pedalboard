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

    def testLoadsTypedLogAndUnmappedActions(self) -> None:
        path = self.writeConfig({"bindings": [
            {"cc": 20, "action": {"type": "log", "message": "ready"}},
            {"cc": 22, "action": None},
        ]})
        config = loadConfig(path)
        self.assertEqual(config.bindings[0].action.message, "ready")
        self.assertIsNone(config.bindings[1].action)

    def testRemovedMacroActionsFailWithMigrationGuidance(self) -> None:
        removed = (
            {"type": "keyboard", "keys": ["ctrl", "r"]},
            {"type": "udp", "host": "127.0.0.1", "port": 9000},
            {"type": "launch", "program": "example"},
            "ctrlShiftR",
        )
        for action in removed:
            with self.subTest(action=action), self.assertRaisesRegex(ConfigError, "removed macro|was removed"):
                loadConfig(self.writeConfig({"bindings": [{"cc": 20, "action": action}]}))

    def testPersistentPairingIsRejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "never changes persistent BlueZ pairing"):
            loadConfig(self.writeConfig({
                "device": {"name": "BlueBoard", "scanTimeout": 20, "pair": True},
                "bindings": [{"cc": 20, "action": None}],
            }))

    def testRejectsInvalidCcAndUnknownActionType(self) -> None:
        for binding in ({"cc": 128, "action": None}, {"cc": 20, "action": {"type": "osc"}}):
            with self.subTest(binding=binding), self.assertRaises(ConfigError):
                loadConfig(self.writeConfig({"bindings": [binding]}))
