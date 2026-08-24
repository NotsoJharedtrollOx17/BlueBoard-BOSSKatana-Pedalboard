import argparse
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from blueboard_macro_handler.cli import (
    buildParser,
    configurePedalboard,
    listMidiOutputs,
    selectKatanaOutput,
    sendKatanaTest,
)
from blueboard_macro_handler.client import DiscoveredDevice


class FakeTransport:
    instances: ClassVar[list] = []
    outputNames: ClassVar[tuple[str, ...]] = ("KATANA", "MIDI Through")

    def __init__(self) -> None:
        self.outputName = None
        self.opened = []
        self.sent = []
        self.closed = 0
        self.__class__.instances.append(self)

    def listOutputNames(self):
        return self.outputNames

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
        FakeTransport.outputNames = ("KATANA", "MIDI Through")

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

    def testSelectsMainKatanaPortWithoutControlPorts(self) -> None:
        names = ("Microsoft GS Wavetable Synth 0", "KATANA 1", "KATANA DAW CTRL 2", "KATANA CTRL 3")
        self.assertEqual(selectKatanaOutput(None, names), "KATANA 1")

    def testAmbiguousMainKatanaPortsRequireOverride(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            selectKatanaOutput(None, ("KATANA 1", "KATANA 2"))

    def testConfigureDiscoversHardwareAndWritesLocalProfileWithoutOpeningMidi(self) -> None:
        FakeTransport.outputNames = ("KATANA 1", "KATANA DAW CTRL 2", "KATANA CTRL 3")
        device = DiscoveredDevice("iRig BlueBoard", "BC:6A:29:34:DD:76", -65, object())
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "katana.local.json"
            statePath = Path(directory) / "state.json"
            args = argparse.Namespace(
                output=None,
                name="BlueBoard",
                scan_timeout=1.0,
                config=configPath,
                state_file=statePath,
                force=False,
            )

            async def discover(name, timeout):
                self.assertEqual((name, timeout), ("BlueBoard", 1.0))
                return [device]

            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch(
                "blueboard_macro_handler.cli.discoverBlueBoards", discover
            ), patch("builtins.print"):
                asyncio.run(configurePedalboard(args))

            config = json.loads(configPath.read_text(encoding="utf-8"))
            state = json.loads(statePath.read_text(encoding="utf-8"))
            self.assertEqual(config["katana"]["outputName"], "KATANA 1")
            self.assertEqual(config["bindings"][2]["action"]["effect"], "booster")
            self.assertEqual(state["lastAddress"], "BC:6A:29:34:DD:76")
            self.assertEqual(FakeTransport.instances[-1].opened, [])


if __name__ == "__main__":
    unittest.main()
