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

    def testSysExRegistryShipsEmptyUntilMkIICaptureExists(self) -> None:
        self.assertEqual(parameterDefinitions, {})
        placeholder = ParameterDefinition(
            "booster.drive",
            (0, 0, 0, 0),
            1,
            0,
            100,
            "katana100MkII",
            "2.00",
            "unverifiedPlaceholder",
        )
        self.assertFalse(placeholder.mayWrite)


if __name__ == "__main__":
    unittest.main()
