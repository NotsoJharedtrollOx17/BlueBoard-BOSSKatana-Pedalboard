import json
import tempfile
import unittest
from pathlib import Path

from blueboard_macro_handler.config import (
    ConfigError,
    configAsDict,
    katanaPedalboardConfig,
    loadConfig,
    officialEffectControls,
    writeConfig,
)


class KatanaConfigTests(unittest.TestCase):
    def writeConfig(self, value) -> Path:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as temporary:
            json.dump(value, temporary)
            path = Path(temporary.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def baseConfig(self) -> dict:
        return {
            "katana": {
                "outputName": "KATANA",
                "midiChannel": 1,
                "model": "katana100MkII",
                "firmware": "2.00",
                "presetStates": {"0": {"booster": False}},
            },
            "bindings": [
                {
                    "cc": 20,
                    "action": {"type": "katana", "command": "toggleEffect", "effect": "booster"},
                }
            ],
        }

    def testLoadsOfficialProfileAndTypedAction(self) -> None:
        config = loadConfig(self.writeConfig(self.baseConfig()))
        self.assertEqual(config.katana.outputName, "KATANA")
        self.assertEqual(config.katana.effectControls, officialEffectControls)
        self.assertEqual(config.katana.presetStates[0], {"booster": False})
        self.assertEqual(config.bindings[0].action.command, "toggleEffect")

    def testRoundTripRetainsKatanaFields(self) -> None:
        normalized = configAsDict(loadConfig(self.writeConfig(self.baseConfig())))
        self.assertEqual(normalized["katana"]["midiChannel"], 1)
        self.assertEqual(normalized["katana"]["presetStates"], {"0": {"booster": False}})
        self.assertEqual(normalized["bindings"][0]["action"]["effect"], "booster")

    def testKatanaActionRequiresTopLevelConfiguration(self) -> None:
        value = {
            "bindings": [
                {"cc": 20, "action": {"type": "katana", "command": "selectPreset", "preset": 0}}
            ]
        }
        with self.assertRaisesRegex(ConfigError, "top-level katana"):
            loadConfig(self.writeConfig(value))

    def testRejectsInvalidChannelsCommandsAndEffects(self) -> None:
        values = []
        invalidChannel = self.baseConfig()
        invalidChannel["katana"]["midiChannel"] = 17
        values.append(invalidChannel)
        invalidCommand = self.baseConfig()
        invalidCommand["bindings"][0]["action"]["command"] = "writeSysEx"
        values.append(invalidCommand)
        invalidEffect = self.baseConfig()
        invalidEffect["bindings"][0]["action"]["effect"] = "noiseSuppressor"
        values.append(invalidEffect)
        for value in values:
            with self.subTest(value=value), self.assertRaises(ConfigError):
                loadConfig(self.writeConfig(value))

    def testRejectsDuplicateEffectControllers(self) -> None:
        value = self.baseConfig()
        value["katana"]["effectControls"] = {"booster": 16, "delay": 16}
        with self.assertRaisesRegex(ConfigError, "must be unique"):
            loadConfig(self.writeConfig(value))

    def testRepositoryAndPackagedDefaultsStayAlignedAndHarmless(self) -> None:
        root = Path(__file__).resolve().parents[2]
        repository = loadConfig(root / "python" / "config" / "blueboard.json")
        packaged = loadConfig(root / "python" / "src" / "blueboard_macro_handler" / "default_config.json")
        self.assertEqual(configAsDict(repository), configAsDict(packaged))
        self.assertTrue(all(binding.action is None for binding in packaged.bindings))

    def testGeneratedPedalboardProfileUsesDetectedOutputAndDocumentedMapping(self) -> None:
        config = katanaPedalboardConfig("KATANA 1")
        self.assertEqual(config.katana.outputName, "KATANA 1")
        self.assertEqual([binding.cc for binding in config.bindings], [20, 21, 22, 23])
        self.assertEqual(config.bindings[0].action.preset, 0)
        self.assertEqual(config.bindings[2].action.effect, "booster")
        self.assertEqual(config.bindings[3].action.effect, "delay")

    def testWriteConfigRefusesAccidentalReplacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pedalboard.json"
            writeConfig(katanaPedalboardConfig("KATANA 1"), path)
            with self.assertRaisesRegex(ConfigError, "already exists"):
                writeConfig(katanaPedalboardConfig("KATANA 2"), path)
            self.assertEqual(loadConfig(path).katana.outputName, "KATANA 1")


if __name__ == "__main__":
    unittest.main()
