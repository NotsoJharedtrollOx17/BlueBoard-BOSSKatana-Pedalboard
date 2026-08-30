import unittest

from blueboard_macro_handler.katana.commands import createControlChange, createProgramChange
from blueboard_macro_handler.katana.parameters import (
    ParameterDefinition,
    calculateRolandChecksum,
    parameterDefinitions,
)


class KatanaCommandTests(unittest.TestCase):
    def testProgramChangeUsesZeroBasedWireChannel(self) -> None:
        self.assertEqual(createProgramChange(0, 0).data, (0xC0, 0))
        self.assertEqual(createProgramChange(15, 127).data, (0xCF, 127))

    def testControlChangeSupportsOfficialOffOnBoundary(self) -> None:
        for value in (0, 63, 64, 127):
            with self.subTest(value=value):
                self.assertEqual(createControlChange(0, 16, value).data, (0xB0, 16, value))

    def testCommandRangesAreStrict(self) -> None:
        invalidCalls = (
            lambda: createProgramChange(-1, 0),
            lambda: createProgramChange(16, 0),
            lambda: createProgramChange(0, 128),
            lambda: createControlChange(0, -1, 0),
            lambda: createControlChange(0, 1, 128),
            lambda: createControlChange(True, 1, 1),
        )
        for call in invalidCalls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

    def testRolandChecksumVectorsAndSevenBitGuard(self) -> None:
        self.assertEqual(calculateRolandChecksum((0x10, 0x00, 0x00, 0x00)), 0x70)
        self.assertEqual(calculateRolandChecksum((0x00, 0x00, 0x00, 0x00)), 0x00)
        with self.assertRaises(ValueError):
            calculateRolandChecksum((0x80,))

    def testSysExRegistryContainsOnlyProbeOnlyMkIEffectFlags(self) -> None:
        expected = {
            "effects.boost.enabled": ((0x60, 0x00, 0x00, 0x30), "communityMkI"),
            "effects.mod.enabled": ((0x60, 0x00, 0x01, 0x40), "communityMkI"),
            "effects.fx.enabled": ((0x60, 0x00, 0x03, 0x4C), "communityMkI"),
            "effects.delay.enabled": ((0x60, 0x00, 0x05, 0x60), "communityMkI"),
            "effects.reverb.enabled": ((0x60, 0x00, 0x06, 0x10), "communityMkI"),
            "effects.effectLoop.enabled": ((0x60, 0x00, 0x06, 0x55), "legacyKatana"),
        }
        self.assertEqual(set(parameterDefinitions), set(expected))
        for name, definition in parameterDefinitions.items():
            with self.subTest(name=name):
                self.assertEqual((definition.address, definition.evidence), expected[name])
                self.assertEqual(definition.model, "katana100")
                self.assertEqual(definition.firmwareRange, "unknown")
                self.assertEqual(definition.dataLength, 1)
                self.assertEqual(definition.readAccess, "probe")
                self.assertEqual(definition.writeAccess, "none")
                self.assertTrue(definition.mayProbe)
                self.assertFalse(definition.mayReadInProduction)
                self.assertFalse(definition.mayWrite)
                self.assertFalse(definition.decodeValue((0,)))
                self.assertTrue(definition.decodeValue((1,)))
                with self.assertRaises(ValueError):
                    definition.decodeValue(())
                with self.assertRaises(ValueError):
                    definition.decodeValue((0, 0))
                with self.assertRaises(ValueError):
                    definition.decodeValue((2,))

    def testParameterDefinitionEnforcesEvidenceAccessBoundary(self) -> None:
        baseArguments = {
            "name": "effects.test.enabled",
            "address": (0, 0, 0, 1),
            "dataLength": 1,
            "model": "katana100",
            "firmwareRange": "unknown",
            "evidence": "communityMkI",
            "readAccess": "probe",
            "writeAccess": "none",
            "decoder": "strictBoolean",
        }
        with self.assertRaisesRegex(ValueError, "production reads"):
            ParameterDefinition(**{**baseArguments, "readAccess": "production"})
        with self.assertRaisesRegex(ValueError, "validated writes"):
            ParameterDefinition(**{**baseArguments, "writeAccess": "validated"})
        with self.assertRaisesRegex(ValueError, "seven-bit"):
            ParameterDefinition(**{**baseArguments, "address": (0, 0, 0, 0x80)})
        with self.assertRaisesRegex(ValueError, "positive integer"):
            ParameterDefinition(**{**baseArguments, "dataLength": True})


if __name__ == "__main__":
    unittest.main()
