import unittest

from blueboard_macro_handler.katana.commands import createSysExData, createSysExRead
from blueboard_macro_handler.katana.protocol import (
    KatanaSysExFrame,
    calculateRolandChecksum,
    decodeBase128,
    encodeBase128,
    incrementAddress,
    parseKatanaSysEx,
    verifyRolandChecksum,
)


class KatanaProtocolTests(unittest.TestCase):
    def testEditorModeDataMessagesMatchReferenceVectors(self) -> None:
        self.assertEqual(
            createSysExData(0, (0x7F, 0x00, 0x00, 0x01), (0x01,)).data,
            (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x12, 0x7F, 0x00, 0x00, 0x01, 0x01, 0x7F, 0xF7),
        )
        self.assertEqual(
            createSysExData(0, (0x7F, 0x00, 0x00, 0x01), (0x00,)).data,
            (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x12, 0x7F, 0x00, 0x00, 0x01, 0x00, 0x00, 0xF7),
        )

    def testReadRequestsMatchReferenceVectors(self) -> None:
        vectors = (
            (
                (0x00, 0x01, 0x00, 0x00),
                2,
                (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x11, 0x00, 0x01, 0x00, 0x00, 0, 0, 0, 2, 0x7D, 0xF7),
            ),
            (
                (0x7F, 0x00, 0x00, 0x00),
                1,
                (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x11, 0x7F, 0x00, 0x00, 0x00, 0, 0, 0, 1, 0x00, 0xF7),
            ),
            (
                (0x60, 0x00, 0x00, 0x30),
                1,
                (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x11, 0x60, 0x00, 0x00, 0x30, 0, 0, 0, 1, 0x6F, 0xF7),
            ),
            (
                (0x60, 0x00, 0x01, 0x40),
                1,
                (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x11, 0x60, 0x00, 0x01, 0x40, 0, 0, 0, 1, 0x5E, 0xF7),
            ),
            (
                (0x60, 0x00, 0x03, 0x4C),
                1,
                (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x11, 0x60, 0x00, 0x03, 0x4C, 0, 0, 0, 1, 0x50, 0xF7),
            ),
            (
                (0x60, 0x00, 0x05, 0x60),
                1,
                (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x11, 0x60, 0x00, 0x05, 0x60, 0, 0, 0, 1, 0x3A, 0xF7),
            ),
            (
                (0x60, 0x00, 0x06, 0x10),
                1,
                (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x11, 0x60, 0x00, 0x06, 0x10, 0, 0, 0, 1, 0x09, 0xF7),
            ),
            (
                (0x60, 0x00, 0x06, 0x55),
                1,
                (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x11, 0x60, 0x00, 0x06, 0x55, 0, 0, 0, 1, 0x44, 0xF7),
            ),
            (
                (0x00, 0x00, 0x04, 0x00),
                0x2A,
                (0xF0, 0x41, 0x00, 0x00, 0x00, 0x00, 0x33, 0x11, 0x00, 0x00, 0x04, 0x00, 0, 0, 0, 0x2A, 0x52, 0xF7),
            ),
        )
        for address, size, expected in vectors:
            with self.subTest(address=address):
                self.assertEqual(createSysExRead(0, address, size).data, expected)

    def testBase128BoundariesAndAddressCarry(self) -> None:
        vectors = (
            (0, (0x00, 0x00, 0x00, 0x00)),
            (0x7F, (0x00, 0x00, 0x00, 0x7F)),
            (0x80, (0x00, 0x00, 0x01, 0x00)),
            (0x0FFFFFFF, (0x7F, 0x7F, 0x7F, 0x7F)),
        )
        for scalar, encoded in vectors:
            with self.subTest(scalar=scalar):
                self.assertEqual(encodeBase128(scalar), encoded)
                self.assertEqual(decodeBase128(encoded), scalar)
        self.assertEqual(incrementAddress((0x00, 0x00, 0x00, 0x7F), 1), (0x00, 0x00, 0x01, 0x00))

    def testBase128RejectsInvalidValuesAndOverflow(self) -> None:
        invalidCalls = (
            lambda: encodeBase128(True),
            lambda: encodeBase128(-1),
            lambda: encodeBase128(0x10000000),
            lambda: encodeBase128(0, width=0),
            lambda: decodeBase128(()),
            lambda: decodeBase128((True,)),
            lambda: decodeBase128((0x80,)),
            lambda: incrementAddress((0, 0, 0), 1),
            lambda: incrementAddress((0x7F, 0x7F, 0x7F, 0x7F), 1),
        )
        for call in invalidCalls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

    def testChecksumCalculationAndVerification(self) -> None:
        self.assertEqual(calculateRolandChecksum((0, 0, 0, 0)), 0)
        values = (0x60, 0x00, 0x00, 0x30, 0x01)
        self.assertEqual(calculateRolandChecksum(values), 0x6F)
        self.assertTrue(verifyRolandChecksum(values, 0x6F))
        self.assertFalse(verifyRolandChecksum(values, 0x00))
        with self.assertRaises(ValueError):
            calculateRolandChecksum((True,))
        with self.assertRaises(ValueError):
            verifyRolandChecksum(values, 0x80)

    def testParserNormalizesFullWireAndMidoPayloadForms(self) -> None:
        fullWire = createSysExRead(0, (0x60, 0x00, 0x00, 0x30), 1).data
        expected = KatanaSysExFrame(0, "rq1", (0x60, 0x00, 0x00, 0x30), (0, 0, 0, 1), (), 0x6F)
        self.assertEqual(parseKatanaSysEx(fullWire, includesFraming=True), expected)
        self.assertEqual(parseKatanaSysEx(fullWire[1:-1], includesFraming=False), expected)

        reply = (0xF0, 0x41, 0, 0, 0, 0, 0x33, 0x12, 0x60, 0, 0, 0x30, 1, 0x6F, 0xF7)
        parsedReply = parseKatanaSysEx(reply, includesFraming=True)
        self.assertEqual(parsedReply.command, "dt1")
        self.assertEqual(parsedReply.data, (1,))
        self.assertIsNone(parsedReply.size)

        editorMode = createSysExData(0, (0x7F, 0, 0, 1), (1,)).data
        parsedEditorMode = parseKatanaSysEx(editorMode, includesFraming=True)
        self.assertEqual(parsedEditorMode.command, "dt1")
        self.assertEqual(parsedEditorMode.address, (0x7F, 0, 0, 1))
        self.assertEqual(parsedEditorMode.data, (1,))

    def testParserRejectsMalformedMessages(self) -> None:
        valid = createSysExRead(0, (0x60, 0x00, 0x00, 0x30), 1).data
        wrongManufacturer = valid[:1] + (0x42,) + valid[2:]
        wrongModel = valid[:6] + (0x34,) + valid[7:]
        wrongCommand = valid[:7] + (0x10,) + valid[8:]
        wrongChecksum = valid[:-2] + (0x00,) + valid[-1:]
        malformedSizeBody = (0xF0, 0x41, 0, 0, 0, 0, 0x33, 0x11, 0x60, 0, 0, 0x30, 0, 0, 1, 0x6F, 0xF7)
        zeroSizeChecksum = calculateRolandChecksum((0x60, 0x00, 0x00, 0x30, 0, 0, 0, 0))
        zeroSizeRq1 = (0xF0, 0x41, 0, 0, 0, 0, 0x33, 0x11, 0x60, 0, 0, 0x30, 0, 0, 0, 0, zeroSizeChecksum, 0xF7)
        emptyDataChecksum = calculateRolandChecksum((0x60, 0x00, 0x00, 0x30))
        emptyDt1 = (0xF0, 0x41, 0, 0, 0, 0, 0x33, 0x12, 0x60, 0, 0, 0x30, emptyDataChecksum, 0xF7)
        booleanPayload = valid[:2] + (True,) + valid[3:]
        invalidCalls = (
            lambda: parseKatanaSysEx(valid[1:], includesFraming=True),
            lambda: parseKatanaSysEx(valid[:-1], includesFraming=True),
            lambda: parseKatanaSysEx(valid, includesFraming=False),
            lambda: parseKatanaSysEx(valid[:6], includesFraming=True),
            lambda: parseKatanaSysEx(wrongManufacturer, includesFraming=True),
            lambda: parseKatanaSysEx(wrongModel, includesFraming=True),
            lambda: parseKatanaSysEx(wrongCommand, includesFraming=True),
            lambda: parseKatanaSysEx(wrongChecksum, includesFraming=True),
            lambda: parseKatanaSysEx(malformedSizeBody, includesFraming=True),
            lambda: parseKatanaSysEx(zeroSizeRq1, includesFraming=True),
            lambda: parseKatanaSysEx(emptyDt1, includesFraming=True),
            lambda: parseKatanaSysEx(booleanPayload, includesFraming=True),
        )
        for call in invalidCalls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()
        with self.assertRaises(TypeError):
            parseKatanaSysEx(valid, includesFraming=1)

    def testBuildersRejectInvalidInputs(self) -> None:
        invalidCalls = (
            lambda: createSysExRead(True, (0, 0, 0, 0), 1),
            lambda: createSysExRead(0, (0, 0, 0), 1),
            lambda: createSysExRead(0, (0, 0, 0, 0x80), 1),
            lambda: createSysExRead(0, (0, 0, 0, 0), 0),
            lambda: createSysExRead(0, (0, 0, 0, 0), True),
            lambda: createSysExRead(0, (0, 0, 0, 0), 0x10000000),
            lambda: createSysExData(0, (0, 0, 0, 0), ()),
            lambda: createSysExData(0, (0, 0, 0, 0), (True,)),
            lambda: createSysExData(0, (0, 0, 0, 0), (0x80,)),
        )
        for call in invalidCalls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()


if __name__ == "__main__":
    unittest.main()
