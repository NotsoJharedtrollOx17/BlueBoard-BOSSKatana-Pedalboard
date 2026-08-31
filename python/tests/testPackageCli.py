import json
import logging
import tempfile
import unittest
from pathlib import Path

from blueboard_macro_handler.ble_midi import encodeBleMidi
from blueboard_macro_handler.cli import buildParser, loadReplayPackets, logWelcome, main
from blueboard_macro_handler.logging_utils import configureLogging


class PackageCliTests(unittest.TestCase):
    def testReplayFixtureLoads(self) -> None:
        packets = loadReplayPackets(Path(__file__).parent / "fixtures" / "blueboardPackets.json")
        self.assertEqual(len(packets), 8)
        self.assertEqual(packets[0], bytes.fromhex("80 80 B0 14 7F"))

    def testValidateDefaultConfig(self) -> None:
        self.assertEqual(main(["validate"]), 0)

    def testInvalidReplayReturnsError(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as value:
            json.dump({"packets": ["invalid"]}, value)
        path = Path(value.name)
        self.addCleanup(path.unlink, missing_ok=True)
        self.assertEqual(main(["replay", str(path)]), 2)

    def testOutboundEncoderProducesBleMidiFrame(self) -> None:
        packet = encodeBleMidi(0xB0, bytes((20, 127)), timestamp=0)
        self.assertEqual(packet, bytes.fromhex("80 80 B0 14 7F"))

    def testRunAcceptsLedFeedbackFlag(self) -> None:
        args = buildParser().parse_args(["run", "--led-feedback", "--reset-leds"])
        self.assertTrue(args.led_feedback)
        self.assertTrue(args.reset_leds)

    def testDebugLoggingSuppressesUnrelatedBleakDeviceDetails(self) -> None:
        configureLogging(debug=True)
        self.assertEqual(logging.getLogger("blueboard.client").getEffectiveLevel(), logging.DEBUG)
        self.assertEqual(logging.getLogger("bleak").getEffectiveLevel(), logging.WARNING)
        self.assertEqual(logging.getLogger("dbus_fast").getEffectiveLevel(), logging.WARNING)

    def testWelcomeLogIdentifiesAuthorAndProject(self) -> None:
        with self.assertLogs("blueboard.cli", level="INFO") as captured:
            logWelcome("replay")
        output = "\n".join(captured.output)
        self.assertIn("Developer : Abraham Jhared Flores Azcona", output)
        self.assertIn("License   : MIT License (Copyright 2026 Abraham Jhared Flores Azcona)", output)
        self.assertIn("Mode      : offline BLE-MIDI packet replay (blueboard-katana replay)", output)
        self.assertIn("Independent project", output)
