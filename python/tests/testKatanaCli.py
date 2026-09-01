import argparse
import asyncio
import json
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from blueboard_macro_handler.cli import (
    asyncCommand,
    buildParser,
    configurationSummaryLines,
    configurePedalboard,
    doctorPedalboard,
    listMidiInputs,
    listMidiOutputs,
    probeKatanaEffects,
    runSysExProbe,
    selectKatanaOutput,
    sendKatanaTest,
)
from blueboard_macro_handler.client import DiscoveredDevice
from blueboard_macro_handler.config import ConfigError, katanaPedalboardConfig, writeConfig
from blueboard_macro_handler.katana.commands import createSysExData
from blueboard_macro_handler.katana.parameters import parameterDefinitions
from blueboard_macro_handler.katana.transport import ReceivedMidiMessage


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

    def listInputNames(self):
        return self.outputNames

    def open(self, name):
        self.outputName = name
        self.opened.append(name)

    def openInput(self, name, callback):
        self.inputName = name
        self.callback = callback
        self.opened.append(("input", name))

    def send(self, command):
        self.sent.append(command.data)

    def close(self):
        self.closed += 1


class FakeSysExTransport(FakeTransport):
    def send(self, command):
        super().send(command)
        if command.data[7] == 0x11:
            address = command.data[8:12]
            reply = createSysExData(0, address, (0,)).data
            self.callback(ReceivedMidiMessage("sysex", reply[1:-1]))


class KatanaCliTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeTransport.instances.clear()
        FakeTransport.outputNames = ("KATANA", "MIDI Through")

    def testMidiOutputsIsReadOnly(self) -> None:
        with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch("builtins.print") as output:
            listMidiOutputs()
        output.assert_any_call("KATANA")
        self.assertEqual(FakeTransport.instances[-1].opened, [])

    def testMidiInputsIsReadOnly(self) -> None:
        with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch("builtins.print") as output:
            listMidiInputs()
        output.assert_any_call("KATANA")
        self.assertEqual(FakeTransport.instances[-1].opened, [])

    def testSysExProbeRequiresExplicitPortsAndCanCancelWithoutOpening(self) -> None:
        parser = buildParser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["sysex-probe", "--model", "katana100", "--read", "effect-states"])
        args = parser.parse_args([
            "sysex-probe", "--model", "katana100", "--input", "KATANA", "--output", "KATANA",
            "--read", "effect-states",
        ])
        output = []
        with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport):
            report = runSysExProbe(args, lambda _prompt: "CANCEL", output.append)
        self.assertIsNone(report)
        self.assertEqual(FakeTransport.instances, [])

    def testRuntimeAndDoctorUseTheQualifiedPackagedProfileByDefault(self) -> None:
        parser = buildParser()
        run = parser.parse_args(["run"])
        doctor = parser.parse_args(["doctor"])
        self.assertEqual(run.config, doctor.config)
        default = json.loads(run.config.read_text(encoding="utf-8"))
        self.assertEqual(default["katana"]["firmware"], "4.00")
        self.assertEqual(default["katana"]["inputName"], "KATANA 0")
        self.assertEqual(default["katana"]["outputName"], "KATANA 1")

    def testSysExProbeReadsAllEffectsAndSavesConfirmedFixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "capture.json"
            args = buildParser().parse_args([
                "sysex-probe", "--model", "katana100", "--input", "KATANA", "--output", "KATANA",
                "--read", "effect-states", "--timeout-ms", "20", "--retries", "0",
                "--save-fixture", str(fixture),
            ])
            answers = iter(("READ", "SAVE"))
            output = []
            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeSysExTransport):
                report = runSysExProbe(args, lambda _prompt: next(answers), output.append)
            self.assertTrue(report.success)
            self.assertEqual(len(report.observations), 6)
            saved = json.loads(fixture.read_text(encoding="utf-8"))
            self.assertEqual(saved["projectVersion"], "1.0.0")
            self.assertTrue(saved["success"])
            self.assertTrue(any("complete wire bytes" in line for line in output))

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

    def testBoundedDryRunStopsCleanlyWithoutOpeningKatana(self) -> None:
        class DurationClient:
            receivedStopEvent = None

            def __init__(self, *_args, **_kwargs) -> None:
                pass

            async def run(self, stopEvent) -> None:
                self.__class__.receivedStopEvent = stopEvent
                await stopEvent.wait()

        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "config.json"
            writeConfig(katanaPedalboardConfig("KATANA"), configPath)
            args = buildParser().parse_args([
                "run", "--config", str(configPath), "--duration-seconds", "0.01",
            ])
            with patch("blueboard_macro_handler.cli.BlueBoardClient", DurationClient):
                metrics = asyncio.run(asyncCommand(args))

        self.assertIsNotNone(DurationClient.receivedStopEvent)
        self.assertEqual(metrics.stopReason, "duration-limit")
        self.assertEqual(metrics.katanaCommands, 0)
        self.assertEqual(FakeTransport.instances, [])

    def testRunRejectsNonPositiveDuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "config.json"
            writeConfig(katanaPedalboardConfig("KATANA"), configPath)
            args = buildParser().parse_args([
                "run", "--config", str(configPath), "--duration-seconds", "0",
            ])
            with self.assertRaisesRegex(ValueError, "duration-seconds must be positive"):
                asyncio.run(asyncCommand(args))

    def testActiveRunBootstrapsDuplexStateBeforeBlueBoardClient(self) -> None:
        class ImmediateClient:
            def __init__(self, *_args, **_kwargs) -> None:
                transport = FakeTransport.instances[-1]
                self.__class__.katanaWasReady = transport.opened[:2] == [("input", "KATANA"), "KATANA"]

            async def run(self, _stopEvent) -> None:
                return

        production = {
            name: replace(
                definition,
                firmwareRange="4.00",
                evidence="capturedMkI",
                readAccess="production",
            )
            for name, definition in parameterDefinitions.items()
        }
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "config.json"
            writeConfig(katanaPedalboardConfig("KATANA", firmware="4.00"), configPath)
            args = buildParser().parse_args([
                "run", "--config", str(configPath), "--execute-actions",
            ])
            with ExitStack() as stack:
                stack.enter_context(patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeSysExTransport))
                stack.enter_context(patch("blueboard_macro_handler.cli.BlueBoardClient", ImmediateClient))
                stack.enter_context(patch(
                    "blueboard_macro_handler.katana.parameters.parameterDefinitions", production
                ))
                stack.enter_context(patch(
                    "blueboard_macro_handler.katana.session.parameterDefinitions", production
                ))
                metrics = asyncio.run(asyncCommand(args))
        transport = FakeTransport.instances[-1]
        self.assertTrue(ImmediateClient.katanaWasReady)
        self.assertEqual(metrics.katanaStateSyncs, 1)
        self.assertEqual(metrics.katanaSysExRequests, 6)
        self.assertEqual(transport.closed, 1)

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
            args = buildParser().parse_args([
                "configure",
                "--config", str(configPath),
                "--state-file", str(statePath),
                "--scan-timeout", "1",
                "--model", "katana100",
                "--non-interactive",
                "--accept-profile-state-defaults",
            ])

            async def discover(name, timeout):
                self.assertEqual((name, timeout), ("BlueBoard", 1.0))
                return [device]

            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch(
                "blueboard_macro_handler.cli.discoverBlueBoards", discover
            ):
                asyncio.run(configurePedalboard(args, outputFunction=lambda _line: None, interactive=False))

            config = json.loads(configPath.read_text(encoding="utf-8"))
            state = json.loads(statePath.read_text(encoding="utf-8"))
            self.assertEqual(config["katana"]["outputName"], "KATANA 1")
            self.assertEqual(config["katana"]["inputName"], "KATANA 1")
            self.assertTrue(config["katana"]["stateSync"]["enabled"])
            self.assertEqual(config["katana"]["model"], "katana100")
            self.assertEqual(config["bindings"][0]["action"]["preset"], 4)
            self.assertEqual(config["bindings"][2]["action"]["effect"], "booster")
            self.assertEqual(state["lastAddress"], "BC:6A:29:34:DD:76")
            self.assertEqual(FakeTransport.instances[-1].opened, [])

    def testInteractiveConfigurePromptsForModelLayoutStateAndWrite(self) -> None:
        device = DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "katana.local.json"
            statePath = Path(directory) / "state.json"
            args = buildParser().parse_args([
                "configure", "--config", str(configPath), "--state-file", str(statePath)
            ])
            answers = iter(("", "", "", "", "y", "y"))

            async def discover(_name, _timeout):
                return [device]

            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch(
                "blueboard_macro_handler.cli.discoverBlueBoards", discover
            ):
                asyncio.run(
                    configurePedalboard(
                        args,
                        lambda _prompt: next(answers),
                        lambda _line: None,
                        interactive=True,
                    )
                )
            config = json.loads(configPath.read_text(encoding="utf-8"))
            self.assertEqual(config["katana"]["model"], "katana100")
            self.assertEqual(config["bindings"][0]["action"]["preset"], 4)

    def testInteractiveConfigureSelectsAmbiguousOutputAndBlueBoard(self) -> None:
        FakeTransport.outputNames = ("KATANA 1", "KATANA 2")
        devices = [
            DiscoveredDevice("iRig BlueBoard One", "AA:01", -40, object()),
            DiscoveredDevice("iRig BlueBoard Two", "AA:02", -50, object()),
        ]
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "katana.local.json"
            statePath = Path(directory) / "state.json"
            args = buildParser().parse_args([
                "configure", "--config", str(configPath), "--state-file", str(statePath)
            ])
            answers = iter(("2", "", "", "", "", "2", "y", "y"))

            async def discover(_name, _timeout):
                return devices

            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch(
                "blueboard_macro_handler.cli.discoverBlueBoards", discover
            ):
                asyncio.run(
                    configurePedalboard(
                        args,
                        lambda _prompt: next(answers),
                        lambda _line: None,
                        interactive=True,
                    )
                )
            config = json.loads(configPath.read_text(encoding="utf-8"))
            state = json.loads(statePath.read_text(encoding="utf-8"))
            self.assertEqual(config["katana"]["outputName"], "KATANA 2")
            self.assertEqual(state["lastAddress"], "AA:02")

    def testConfigureCancellationPreservesExistingConfiguration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "katana-pedalboard.local.json"
            statePath = Path(directory) / "state.json"
            writeConfig(katanaPedalboardConfig("KATANA 1"), configPath)
            original = configPath.read_bytes()
            args = buildParser().parse_args([
                "configure", "--config", str(configPath), "--state-file", str(statePath)
            ])
            asyncio.run(
                configurePedalboard(
                    args,
                    lambda _prompt: "n",
                    lambda _line: None,
                    interactive=True,
                )
            )
            self.assertEqual(configPath.read_bytes(), original)
            self.assertEqual(FakeTransport.instances, [])

    def testForcedReplacementCreatesIgnoredStyleTimestampedBackup(self) -> None:
        device = DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "katana-pedalboard.local.json"
            statePath = Path(directory) / "state.json"
            writeConfig(katanaPedalboardConfig("OLD KATANA"), configPath)
            args = buildParser().parse_args([
                "configure", "--config", str(configPath), "--state-file", str(statePath),
                "--model", "katana100", "--non-interactive", "--accept-profile-state-defaults", "--force",
            ])

            async def discover(_name, _timeout):
                return [device]

            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch(
                "blueboard_macro_handler.cli.discoverBlueBoards", discover
            ):
                asyncio.run(configurePedalboard(args, outputFunction=lambda _line: None, interactive=False))
            backups = tuple(Path(directory).glob("*.backup-*.local.json"))
            self.assertEqual(len(backups), 1)
            self.assertIn("OLD KATANA", backups[0].read_text(encoding="utf-8"))

    def testNonInteractiveConfigureRequiresModelAndStateAcknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = buildParser().parse_args([
                "configure", "--config", str(Path(directory) / "config.json"), "--non-interactive"
            ])
            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), self.assertRaisesRegex(
                ConfigError, "--model"
            ):
                asyncio.run(configurePedalboard(args, outputFunction=lambda _line: None, interactive=False))

    def testDoctorChecksDevicesWithoutOpeningOrSendingMidi(self) -> None:
        device = DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "config.json"
            statePath = Path(directory) / "state.json"
            writeConfig(katanaPedalboardConfig("KATANA"), configPath)
            args = argparse.Namespace(config=configPath, state_file=statePath, scan_timeout=1.0)

            async def discover(_name, _timeout):
                return [device]

            output: list[str] = []
            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch(
                "blueboard_macro_handler.cli.discoverBlueBoards", discover
            ), patch("blueboard_macro_handler.onboarding.inspectLinuxEnvironment", return_value=()):
                asyncio.run(doctorPedalboard(args, output.append))
            transport = FakeTransport.instances[-1]
            self.assertEqual(transport.opened, [])
            self.assertEqual(transport.sent, [])
            self.assertTrue(any(line.startswith("READY") for line in output))

    def testDoctorAggregatesReadinessFailureWithoutOpeningMidi(self) -> None:
        FakeTransport.outputNames = ("Other MIDI",)
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "config.json"
            statePath = Path(directory) / "state.json"
            writeConfig(katanaPedalboardConfig("KATANA"), configPath)
            args = argparse.Namespace(config=configPath, state_file=statePath, scan_timeout=0.1)

            async def discover(_name, _timeout):
                return []

            output: list[str] = []
            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), patch(
                "blueboard_macro_handler.cli.discoverBlueBoards", discover
            ), patch("blueboard_macro_handler.onboarding.inspectLinuxEnvironment", return_value=()), self.assertRaisesRegex(
                RuntimeError, "3 readiness"
            ):
                asyncio.run(doctorPedalboard(args, output.append))
            self.assertEqual(FakeTransport.instances[-1].opened, [])
            self.assertTrue(any(line.startswith("NOT READY") for line in output))

    def testConfigurationSummaryUsesModelCorrectHumanLabels(self) -> None:
        lines = configurationSummaryLines(katanaPedalboardConfig("KATANA 1"))
        self.assertIn("Button A: Panel (Program Change 4)", lines)
        self.assertIn("Button C: toggle Booster/Mod (CC16)", lines)
        self.assertIn("Button D: toggle Delay/FX (CC17)", lines)

    def testEffectProbeSelectsPresetAndTestsOnlyRequestedMkIISwitch(self) -> None:
        args = argparse.Namespace(
            output="KATANA", config=None, model="katana100MkII", channel=1, program=0, effects=("delay",)
        )
        answers = iter(("PROBE", "", "y", "n"))
        output: list[str] = []
        with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport):
            metrics = probeKatanaEffects(args, lambda _prompt: next(answers), output.append)
        transport = FakeTransport.instances[-1]
        self.assertEqual(transport.sent, [(0xC0, 0), (0xB0, 19, 127), (0xB0, 19, 0)])
        self.assertEqual(transport.closed, 1)
        self.assertEqual(metrics.katanaCommands, 3)
        self.assertTrue(any("delay" in line.casefold() and "19" in line for line in output))

    def testEffectProbeUsesConfiguredOriginalProfileAndFirstPreset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "config.json"
            writeConfig(katanaPedalboardConfig("KATANA 1"), configPath)
            args = argparse.Namespace(
                output=None, config=configPath, model=None, channel=None, program=None, effects=("delay",)
            )
            answers = iter(("PROBE", "", "y", "y"))
            with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport):
                probeKatanaEffects(args, lambda _prompt: next(answers), lambda _line: None)
            self.assertEqual(FakeTransport.instances[-1].sent, [(0xC0, 4), (0xB0, 17, 127), (0xB0, 17, 0)])

    def testEffectProbeRequiresModelWithRawOutput(self) -> None:
        args = argparse.Namespace(output="KATANA", config=None, model=None, channel=None, program=None, effects=None)
        with self.assertRaisesRegex(ConfigError, "--model"):
            probeKatanaEffects(args)

    def testEffectProbeTurnsActiveSwitchOffWhenInterrupted(self) -> None:
        args = argparse.Namespace(
            output="KATANA", config=None, model="katana100MkII", channel=1, program=0, effects=("fx",)
        )
        answers = iter(("PROBE", ""))

        def inputFunction(_prompt):
            try:
                return next(answers)
            except StopIteration as error:
                raise KeyboardInterrupt from error

        with patch("blueboard_macro_handler.cli.MidoMidiTransport", FakeTransport), self.assertRaises(
            KeyboardInterrupt
        ):
            probeKatanaEffects(args, inputFunction, lambda _line: None)
        transport = FakeTransport.instances[-1]
        self.assertEqual(transport.sent, [(0xC0, 0), (0xB0, 18, 127), (0xB0, 18, 0)])
        self.assertEqual(transport.closed, 1)


if __name__ == "__main__":
    unittest.main()
