import json
import tempfile
import unittest
from pathlib import Path

from blueboard_macro_handler.config import (
    ConfigError,
    configAsDict,
    katanaPedalboardConfig,
    katanaProfile,
    loadConfig,
    officialEffectControls,
    originalKatana100EffectControls,
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

    def testLoadsOriginalKatanaProfileWithGroupedSwitches(self) -> None:
        value = self.baseConfig()
        value["katana"]["model"] = "katana100"
        value["katana"]["firmware"] = "4.00"
        config = loadConfig(self.writeConfig(value))
        self.assertEqual(config.katana.effectControls, originalKatana100EffectControls)

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

    def testGeneratedPedalboardProfileDefaultsToValidatedOriginalPanelMapping(self) -> None:
        config = katanaPedalboardConfig("KATANA 1")
        self.assertEqual(config.katana.outputName, "KATANA 1")
        self.assertEqual(config.katana.model, "katana100")
        self.assertEqual(config.katana.effectControls, originalKatana100EffectControls)
        self.assertEqual([binding.cc for binding in config.bindings], [20, 21, 22, 23])
        self.assertEqual([config.bindings[0].action.preset, config.bindings[1].action.preset], [4, 1])
        self.assertEqual(config.bindings[2].action.effect, "booster")
        self.assertEqual(config.bindings[3].action.effect, "delay")
        self.assertEqual(config.katana.presetStates[4], {"booster": False, "delay": False})

    def testGeneratedMkIIProfileUsesIndependentControlsAndChannelLayout(self) -> None:
        config = katanaPedalboardConfig("KATANA", model="katana100MkII")
        self.assertEqual(config.katana.model, "katana100MkII")
        self.assertEqual(config.katana.effectControls, officialEffectControls)
        self.assertEqual([config.bindings[0].action.preset, config.bindings[1].action.preset], [0, 1])

    def testProfileRegistryCarriesModelCorrectGroupedLabels(self) -> None:
        original = katanaProfile("katana100")
        mkII = katanaProfile("katana100MkII")
        self.assertEqual(original.effectLabels["booster"], "Booster/Mod")
        self.assertEqual(original.effectLabels["delay"], "Delay/FX")
        self.assertEqual(mkII.effectLabels["delay"], "Delay")

    def testGeneratedProfileRejectsInvalidModelAndChannel(self) -> None:
        with self.assertRaisesRegex(ConfigError, "model"):
            katanaPedalboardConfig("KATANA", model="unknown")
        with self.assertRaisesRegex(ConfigError, "channel"):
            katanaPedalboardConfig("KATANA", midiChannel=17)

    def testWriteConfigRefusesAccidentalReplacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pedalboard.json"
            writeConfig(katanaPedalboardConfig("KATANA 1"), path)
            with self.assertRaisesRegex(ConfigError, "already exists"):
                writeConfig(katanaPedalboardConfig("KATANA 2"), path)
            self.assertEqual(loadConfig(path).katana.outputName, "KATANA 1")


if __name__ == "__main__":
    unittest.main()
