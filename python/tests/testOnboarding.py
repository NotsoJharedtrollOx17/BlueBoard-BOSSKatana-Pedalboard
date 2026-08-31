import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from blueboard_macro_handler.cli import buildParser
from blueboard_macro_handler.client import DiscoveredDevice
from blueboard_macro_handler.config import katanaPedalboardConfig, writeConfig
from blueboard_macro_handler.onboarding import collectDiscoverySnapshot, onboardPedalboard


class RecordingTransport:
    outputNames = ("KATANA 1", "KATANA DAW CTRL 2", "KATANA CTRL 3")

    def __init__(self) -> None:
        self.opened = []
        self.sent = []
        self.listCalls = 0

    def listOutputNames(self):
        self.listCalls += 1
        return self.outputNames

    def listInputNames(self):
        return getattr(self, "inputNames", self.outputNames)

    def open(self, name):
        self.opened.append(name)

    def send(self, command):
        self.sent.append(command)


class OnboardingTests(unittest.TestCase):
    def testOnboardingDefaultsToTwentySecondScan(self) -> None:
        args = buildParser().parse_args(["onboard"])
        self.assertEqual(args.scan_timeout, 20.0)

    def testDiscoveryRunsMidiAndBlueBoardWorkConcurrently(self) -> None:
        midiStarted = threading.Event()
        blueBoardStarted = threading.Event()
        transport = RecordingTransport()

        def listOutputNames():
            midiStarted.set()
            if not blueBoardStarted.wait(1):
                raise AssertionError("BlueBoard discovery did not overlap MIDI discovery")
            return transport.outputNames

        transport.listOutputNames = listOutputNames

        async def discover(_name, _timeout):
            blueBoardStarted.set()
            for _attempt in range(100):
                if midiStarted.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(midiStarted.is_set())
            return [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())]

        snapshot = asyncio.run(
            collectDiscoverySnapshot(
                "BlueBoard",
                1,
                midiTransportFactory=lambda: transport,
                discoverFunction=discover,
            )
        )
        self.assertEqual(snapshot.outputNames[0], "KATANA 1")
        self.assertEqual(snapshot.inputNames[0], "KATANA 1")
        self.assertEqual(snapshot.devices[0].address, "AA:BB")
        self.assertEqual(transport.opened, [])
        self.assertEqual(transport.sent, [])

    def testNonInteractiveOnboardingReusesOneSnapshotAndNeverOpensMidi(self) -> None:
        transport = RecordingTransport()
        discoveryCalls = 0

        async def discover(_name, _timeout):
            nonlocal discoveryCalls
            discoveryCalls += 1
            return [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())]

        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "katana-pedalboard.local.json"
            statePath = Path(directory) / "state.json"
            args = buildParser().parse_args([
                "onboard",
                "--config", str(configPath),
                "--state-file", str(statePath),
                "--model", "katana100",
                "--layout", "panel-first",
                "--non-interactive",
                "--accept-profile-state-defaults",
            ])
            output: list[str] = []
            asyncio.run(
                onboardPedalboard(
                    args,
                    outputFunction=output.append,
                    interactive=False,
                    midiTransportFactory=lambda: transport,
                    discoverFunction=discover,
                    environmentCheckFunction=lambda: (),
                )
            )
            config = json.loads(configPath.read_text(encoding="utf-8"))
            state = json.loads(statePath.read_text(encoding="utf-8"))

        self.assertEqual(transport.listCalls, 1)
        self.assertEqual(discoveryCalls, 1)
        self.assertEqual(transport.opened, [])
        self.assertEqual(transport.sent, [])
        self.assertEqual(config["katana"]["outputName"], "KATANA 1")
        self.assertEqual(config["katana"]["inputName"], "KATANA 1")
        self.assertTrue(config["katana"]["stateSync"]["enabled"])
        self.assertEqual(config["bindings"][0]["action"]["preset"], 4)
        self.assertEqual(state["lastAddress"], "AA:BB")
        self.assertTrue(any("reusing the discovery snapshot" in line.casefold() for line in output))
        self.assertTrue(any(line == "Onboarding complete: READY" for line in output))

    def testLinuxOnboardingSavesAndShowsIndependentStableSelectors(self) -> None:
        transport = RecordingTransport()
        transport.inputNames = ("KATANA Input:KATANA MIDI 1 24:0",)
        transport.outputNames = ("KATANA Output:KATANA MIDI 1 27:0",)

        async def discover(_name, _timeout):
            return [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())]

        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "katana-pedalboard.local.json"
            args = buildParser().parse_args([
                "onboard",
                "--config", str(configPath),
                "--state-file", str(Path(directory) / "state.json"),
                "--model", "katana100",
                "--layout", "panel-first",
                "--input", transport.inputNames[0],
                "--output", transport.outputNames[0],
                "--firmware", "4.00",
                "--non-interactive",
                "--accept-profile-state-defaults",
            ])
            output: list[str] = []
            with patch("blueboard_macro_handler.onboarding.sys.platform", "linux"):
                asyncio.run(onboardPedalboard(
                    args,
                    outputFunction=output.append,
                    interactive=False,
                    midiTransportFactory=lambda: transport,
                    discoverFunction=discover,
                ))
            config = json.loads(configPath.read_text(encoding="utf-8"))

        self.assertEqual(config["katana"]["inputName"], "KATANA MIDI 1")
        self.assertEqual(config["katana"]["outputName"], "KATANA MIDI 1")
        self.assertIn("MIDI input current : KATANA Input:KATANA MIDI 1 24:0", output)
        self.assertIn("MIDI output saved  : KATANA MIDI 1", output)

    def testInteractiveRetryRefreshesOnlyFailedBlueBoardDiscovery(self) -> None:
        transport = RecordingTransport()
        discoveryCalls = 0

        async def discover(_name, _timeout):
            nonlocal discoveryCalls
            discoveryCalls += 1
            if discoveryCalls == 1:
                return []
            return [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())]

        with tempfile.TemporaryDirectory() as directory:
            args = buildParser().parse_args([
                "onboard",
                "--config", str(Path(directory) / "config.json"),
                "--state-file", str(Path(directory) / "state.json"),
                "--model", "katana100",
                "--layout", "panel-first",
                "--midi-channel", "1",
                "--firmware", "unknown",
                "--accept-profile-state-defaults",
            ])
            answers = iter(("", "y"))
            asyncio.run(
                onboardPedalboard(
                    args,
                    inputFunction=lambda _prompt: next(answers),
                    outputFunction=lambda _line: None,
                    interactive=True,
                    midiTransportFactory=lambda: transport,
                    discoverFunction=discover,
                )
            )

        self.assertEqual(transport.listCalls, 1)
        self.assertEqual(discoveryCalls, 2)
        self.assertEqual(transport.opened, [])

    def testOnboardingCancellationPreservesExistingConfiguration(self) -> None:
        transport = RecordingTransport()

        async def discover(_name, _timeout):
            return [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())]

        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "katana-pedalboard.local.json"
            writeConfig(katanaPedalboardConfig("OLD KATANA"), configPath)
            original = configPath.read_bytes()
            args = buildParser().parse_args([
                "onboard",
                "--config", str(configPath),
                "--state-file", str(Path(directory) / "state.json"),
            ])
            asyncio.run(
                onboardPedalboard(
                    args,
                    inputFunction=lambda _prompt: "n",
                    outputFunction=lambda _line: None,
                    interactive=True,
                    midiTransportFactory=lambda: transport,
                    discoverFunction=discover,
                )
            )
            self.assertEqual(configPath.read_bytes(), original)
            self.assertFalse((Path(directory) / "state.json").exists())
        self.assertEqual(transport.opened, [])

    def testNonInteractiveDiscoveryFailureDoesNotWriteConfiguration(self) -> None:
        class FailingTransport(RecordingTransport):
            def listOutputNames(self):
                raise RuntimeError("backend unavailable")

        transport = FailingTransport()

        async def discover(_name, _timeout):
            return [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())]

        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "config.json"
            args = buildParser().parse_args([
                "onboard",
                "--config", str(configPath),
                "--state-file", str(Path(directory) / "state.json"),
                "--model", "katana100",
                "--non-interactive",
                "--accept-profile-state-defaults",
            ])
            with self.assertRaisesRegex(RuntimeError, "hardware discovery"):
                asyncio.run(
                    onboardPedalboard(
                        args,
                        outputFunction=lambda _line: None,
                        interactive=False,
                        midiTransportFactory=lambda: transport,
                        discoverFunction=discover,
                    )
                )
            self.assertFalse(configPath.exists())
        self.assertEqual(transport.opened, [])
        self.assertEqual(transport.sent, [])

    def testVerifyExistingUsesFreshDoctorDiscoveryWithoutPromptingOrWriting(self) -> None:
        transport = RecordingTransport()
        discoveryCalls = 0

        async def discover(_name, _timeout):
            nonlocal discoveryCalls
            discoveryCalls += 1
            return [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, object())]

        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / "katana-pedalboard.local.json"
            statePath = Path(directory) / "state.json"
            writeConfig(katanaPedalboardConfig("KATANA 1"), configPath)
            original = configPath.read_bytes()
            args = buildParser().parse_args([
                "onboard",
                "--config", str(configPath),
                "--state-file", str(statePath),
                "--verify-existing",
            ])
            output: list[str] = []
            asyncio.run(
                onboardPedalboard(
                    args,
                    inputFunction=lambda _prompt: self.fail("verification must not prompt"),
                    outputFunction=output.append,
                    midiTransportFactory=lambda: transport,
                    discoverFunction=discover,
                    environmentCheckFunction=lambda: (),
                )
            )
            self.assertEqual(configPath.read_bytes(), original)

        self.assertEqual(transport.listCalls, 1)
        self.assertEqual(discoveryCalls, 1)
        self.assertEqual(transport.opened, [])
        self.assertEqual(transport.sent, [])
        self.assertIn("Existing configuration verified; no files were changed.", output)

    def testVerifyExistingRejectsMissingProfile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = buildParser().parse_args([
                "onboard",
                "--config", str(Path(directory) / "missing.json"),
                "--verify-existing",
            ])
            with self.assertRaisesRegex(Exception, "does not exist"):
                asyncio.run(onboardPedalboard(args, interactive=False))


if __name__ == "__main__":
    unittest.main()
