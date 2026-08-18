import unittest
from typing import ClassVar
from unittest.mock import patch

from blueboard_macro_handler.cli import buildParser, listMidiOutputs, sendKatanaTest


class FakeTransport:
    instances: ClassVar[list] = []

    def __init__(self) -> None:
        self.outputName = None
        self.opened = []
        self.sent = []
        self.closed = 0
        self.__class__.instances.append(self)

    def listOutputNames(self):
        return ("KATANA", "MIDI Through")

    def open(self, name):
        self.outputName = name
        self.opened.append(name)

    def send(self, command):
        self.sent.append(command.data)

    def close(self):
        self.closed += 1


class KatanaCliTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeTransport.instances.clear()

    def testMidiOutputsIsReadOnly(self) -> None:
        with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch("builtins.print") as output:
            listMidiOutputs()
        output.assert_any_call("KATANA")
        self.assertEqual(FakeTransport.instances[-1].opened, [])

    def testKatanaTestSendsOneExplicitProgramChangeAndCloses(self) -> None:
        args = buildParser().parse_args(["katana-test", "--output", "KATANA", "--program", "0"])
        with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport):
            metrics = sendKatanaTest(args)
        transport = FakeTransport.instances[-1]
        self.assertEqual(transport.opened, ["KATANA"])
        self.assertEqual(transport.sent, [(0xC0, 0)])
        self.assertEqual(transport.closed, 1)
        self.assertEqual(metrics.katanaCommands, 1)

    def testKatanaControlTestRequiresValue(self) -> None:
        args = buildParser().parse_args(["katana-test", "--output", "KATANA", "--control", "16"])
        with self.assertRaisesRegex(ValueError, "--value is required"):
            sendKatanaTest(args)


if __name__ == "__main__":
    unittest.main()
