import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from blueboard_macro_handler.client import (
    BlueBoardClient,
    BlueBoardGattProfile,
    DiscoveredDevice,
    discoverBlueBoardGattProfile,
    parseGatttoolCharacteristics,
    parseGatttoolDescriptors,
    parseGatttoolNotification,
    resolveBlueBoardGattProfile,
    testedBlueBoardGattProfile,
)
from blueboard_macro_handler.models import RunMetrics
from blueboard_macro_handler.state import loadLastAddress, saveLastAddress


class FakeServices:
    def get_service(self, _uuid): return object()
    def get_characteristic(self, _uuid):
        descriptor = type("Descriptor", (), {
            "handle": 0x0023,
            "uuid": "00002902-0000-1000-8000-00805f9b34fb",
        })()
        return type("Characteristic", (), {
            "handle": 0x0022,
            "properties": ["write"],
            "descriptors": [descriptor],
        })()


class FakeBleakClient:
    instance = None
    def __init__(self, device, **_kwargs):
        self.device, self.services, self.is_connected = device, FakeServices(), True
        self.started = self.stopped = False
        FakeBleakClient.instance = self
    async def __aenter__(self): return self
    async def __aexit__(self, *_args): self.is_connected = False
    async def start_notify(self, _uuid, callback):
        self.started = True
        callback(None, bytearray.fromhex("80 80 B0 14 7F"))
        await asyncio.sleep(0.01)
    async def stop_notify(self, _uuid): self.stopped = True
    async def write_gatt_char(self, *args, **kwargs): self.lastWrite = (args, kwargs)


class OmittedServiceBleakClient(FakeBleakClient):
    def __init__(self, device, **kwargs):
        super().__init__(device, **kwargs)
        self.services = type("OmittedServices", (), {"get_service": lambda _self, _uuid: None})()


class FakeGatttoolStdin:
    def __init__(self): self.values = []
    def write(self, value): self.values.append(value)
    async def drain(self): pass


class FakeGatttoolStdout:
    def __init__(self, lines): self.lines = iter(lines)
    async def readline(self): return next(self.lines, b"")


class HealthCheckGatttoolStdout:
    def __init__(self): self.calls = 0
    async def readline(self):
        self.calls += 1
        if self.calls == 1:
            return b"Connection successful\n"
        if self.calls == 2:
            return b"Characteristic value was written successfully\n"
        if self.calls == 3:
            await asyncio.Future()
        return b"Disconnected\n"


class FakeGatttoolProcess:
    def __init__(self, lines):
        self.stdin, self.stdout, self.returncode = FakeGatttoolStdin(), FakeGatttoolStdout(lines), None
        self.terminated = False
    async def wait(self):
        self.returncode = 0
        return self.returncode
    def terminate(self): self.terminated = True
    def kill(self): self.returncode = -9


class FakeGatttoolQueryProcess:
    def __init__(self, output, returncode=0):
        self.output = output.encode("ascii")
        self.returncode = returncode
        self.killed = False
    async def communicate(self): return self.output, None
    async def wait(self): return self.returncode
    def kill(self): self.killed = True; self.returncode = -9


def discoveryProcesses(valueHandle=0x0022, cccHandle=0x0023):
    characteristics = (
        f"handle = 0x0021, char properties = 0x1c, char value handle = 0x{valueHandle:04x}, "
        "uuid = 7772e5db-3868-4112-a1a9-f2669d106bf3\n"
    )
    descriptors = f"handle = 0x{cccHandle:04x}, uuid = 00002902-0000-1000-8000-00805f9b34fb\n"
    return FakeGatttoolQueryProcess(characteristics), FakeGatttoolQueryProcess(descriptors)


class FakeLedFeedback:
    def __init__(self): self.bound = self.unbound = 0
    async def bind(self, _writer, *, response=False):
        self.bound += 1
        self.response = response
    async def unbind(self): self.unbound += 1


class PackageClientTests(unittest.IsolatedAsyncioTestCase):
    async def testConnectSubscribeConsumeAndStop(self) -> None:
        events, stopEvent, metrics, feedback = [], asyncio.Event(), RunMetrics(), FakeLedFeedback()
        device = type("Device", (), {"address": "AA:BB"})()
        discovered = [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, device)]
        def receive(event): events.append(event); stopEvent.set()
        client = BlueBoardClient(receive, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1, metrics=metrics, ledFeedback=feedback)
        with patch("blueboard_macro_handler.client.discoverBlueBoards", AsyncMock(return_value=discovered)), patch("bleak.BleakClient", FakeBleakClient):
            await client.run(stopEvent)
        self.assertEqual(len(events), 1)
        self.assertTrue(FakeBleakClient.instance.started)
        self.assertTrue(FakeBleakClient.instance.stopped)
        self.assertEqual(metrics.packets, 1)
        self.assertEqual((feedback.bound, feedback.unbound), (1, 1))
        self.assertTrue(feedback.response)

    async def testStopEventCancelsAnInProgressDiscovery(self) -> None:
        stopEvent, discoveryCancelled = asyncio.Event(), asyncio.Event()

        async def discover(_name, _timeout):
            try:
                await asyncio.Future()
            finally:
                discoveryCancelled.set()

        async def requestStop() -> None:
            await asyncio.sleep(0)
            stopEvent.set()

        client = BlueBoardClient(
            lambda _event: None,
            lambda: None,
            nameSubstring="BlueBoard",
            address=None,
            pair=False,
            scanTimeout=20,
        )
        with patch("blueboard_macro_handler.client.discoverBlueBoards", discover):
            stopTask = asyncio.create_task(requestStop())
            await asyncio.wait_for(client.run(stopEvent), timeout=1)
            await stopTask
        self.assertTrue(discoveryCancelled.is_set())

    async def testResetLedsDisconnectsAfterFeedbackInitialization(self) -> None:
        metrics, feedback = RunMetrics(), FakeLedFeedback()
        device = type("Device", (), {"address": "AA:BB"})()
        discovered = [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, device)]
        client = BlueBoardClient(
            lambda _event: None,
            lambda: None,
            nameSubstring="BlueBoard",
            address=None,
            pair=False,
            scanTimeout=1,
            metrics=metrics,
            ledFeedback=feedback,
            resetLeds=True,
        )
        with patch("blueboard_macro_handler.client.discoverBlueBoards", AsyncMock(return_value=discovered)), patch(
            "bleak.BleakClient", FakeBleakClient
        ):
            await client.run()
        self.assertTrue(FakeBleakClient.instance.stopped)
        self.assertEqual((feedback.bound, feedback.unbound), (1, 1))

    def testLedFeedbackUsesWriteResponseWhenAvailable(self) -> None:
        client = BlueBoardClient(lambda _: None, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1)
        responseClient = type("Client", (), {"services": FakeServices()})()
        self.assertTrue(client.ledFeedbackUsesWriteResponse(responseClient))

    def testLedFeedbackFallsBackToUnacknowledgedWrites(self) -> None:
        services = type(
            "Services",
            (),
            {"get_characteristic": lambda _self, _uuid: type("Characteristic", (), {"properties": ["write-without-response"]})()},
        )()
        client = BlueBoardClient(lambda _: None, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1)
        responseClient = type("Client", (), {"services": services})()
        self.assertFalse(client.ledFeedbackUsesWriteResponse(responseClient))

    async def testSavedAddressFallsBackToNameDiscovery(self) -> None:
        device = type("Device", (), {"address": "AA:BB"})()
        client = BlueBoardClient(lambda _: None, lambda: None, nameSubstring="BlueBoard", address="CC:DD", pair=False, scanTimeout=1)
        with patch("blueboard_macro_handler.client.discoverBlueBoards", AsyncMock(return_value=[DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, device)])):
            self.assertIs(await client.findDevice(), device)

    async def testWritePacketIsSerialized(self) -> None:
        active = maxActive = 0

        class SlowBleakClient:
            is_connected = True
            async def write_gatt_char(self, *_args, **_kwargs):
                nonlocal active, maxActive
                active += 1
                maxActive = max(maxActive, active)
                await asyncio.sleep(0)
                active -= 1

        client = BlueBoardClient(lambda _: None, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1)
        client.currentClient = SlowBleakClient()
        client.gattProfile = BlueBoardGattProfile("test", 0x0042, 0x0043, "bluez-service")
        await asyncio.gather(*(client.writePacket(bytes((value,))) for value in range(4)))
        self.assertEqual(maxActive, 1)

    async def testBleakWritePacketUsesTheActiveProfileHandle(self) -> None:
        writes = []

        class ConnectedBleakClient:
            is_connected = True

            async def write_gatt_char(self, *args, **kwargs):
                writes.append((args, kwargs))

        client = BlueBoardClient(
            lambda _event: None,
            lambda: None,
            nameSubstring="BlueBoard",
            address=None,
            pair=False,
            scanTimeout=1,
        )
        client.currentClient = ConnectedBleakClient()
        client.gattProfile = BlueBoardGattProfile("test", 0x0042, 0x0043, "bluez-service")
        await client.writePacket(b"test", response=True)
        self.assertEqual(writes, [((0x0042, b"test"), {"response": True})])

    async def testWritePacketUsesActiveGatttoolSession(self) -> None:
        client = BlueBoardClient(lambda _: None, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1)
        writer = FakeGatttoolStdin()
        client.gatttoolStdin = writer
        client.gattProfile = BlueBoardGattProfile("test", 0x0042, 0x0043, "discovered")
        await client.writePacket(bytes.fromhex("80 80 b0 14 7f"), response=False)
        self.assertEqual(writer.values, [b"char-write-cmd 0x0042 8080b0147f\n"])

    async def testInteractiveGatttoolSubscribesAndBindsFeedback(self) -> None:
        stopEvent, feedback = asyncio.Event(), FakeLedFeedback()
        lines = [
            b"Connection successful\n",
            b"Characteristic value was written successfully\n",
            b"Notification handle = 0x0042 value: 80 80 b0 14 7f\n",
        ]
        process = FakeGatttoolProcess(lines)
        characteristicProcess, descriptorProcess = discoveryProcesses(0x0042, 0x0043)

        def receive(_event): stopEvent.set()

        client = BlueBoardClient(receive, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1, ledFeedback=feedback)
        with patch("blueboard_macro_handler.client.shutil.which", side_effect=lambda name: "/usr/bin/gatttool" if name == "gatttool" else None), patch(
            "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=(characteristicProcess, descriptorProcess, process)),
        ):
            await client.runBluezGatttoolFallback("AA:BB", "iRig BlueBoard", stopEvent)
        self.assertEqual(process.stdin.values[:2], [b"connect\n", b"char-write-req 0x0043 0100\n"])
        self.assertEqual((feedback.bound, feedback.unbound), (1, 1))
        self.assertTrue(process.terminated)

    async def testGatttoolKeepsValidatedNoninteractivePathWithoutFeedback(self) -> None:
        stopEvent = asyncio.Event()
        process = FakeGatttoolProcess([
            b"Characteristic value was written successfully\n",
            b"Notification handle = 0x0022 value: 80 80 b0 14 7f\n",
        ])
        characteristicProcess, descriptorProcess = discoveryProcesses()

        def receive(_event): stopEvent.set()

        client = BlueBoardClient(receive, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1)
        createProcess = AsyncMock(side_effect=(characteristicProcess, descriptorProcess, process))
        with patch("blueboard_macro_handler.client.shutil.which", side_effect=lambda name: "/usr/bin/gatttool" if name == "gatttool" else None), patch("blueboard_macro_handler.client.asyncio.create_subprocess_exec", createProcess):
            await client.runBluezGatttoolFallback("AA:BB", "iRig BlueBoard", stopEvent)
        command = createProcess.await_args_list[-1].args
        self.assertIn("--listen", command)
        self.assertIsNone(createProcess.await_args.kwargs["stdin"])
        self.assertEqual(process.stdin.values, [])
        self.assertTrue(process.terminated)

    async def testGatttoolProcessLossReturnsToTheReconnectLoop(self) -> None:
        stopEvent = asyncio.Event()
        device = type("Device", (), {"address": "AA:BB"})()
        discovered = [DiscoveredDevice("iRig BlueBoard", "AA:BB", -50, device)]
        fallbackCalls = 0

        async def fallback(_address, _name, _stopEvent):
            nonlocal fallbackCalls
            fallbackCalls += 1
            if fallbackCalls == 1:
                raise RuntimeError("gatttool compatibility connection was lost")
            stopEvent.set()

        metrics = RunMetrics()
        client = BlueBoardClient(
            lambda _event: None,
            lambda: None,
            nameSubstring="BlueBoard",
            address=None,
            pair=False,
            scanTimeout=1,
            metrics=metrics,
        )
        with (
            patch("blueboard_macro_handler.client.discoverBlueBoards", AsyncMock(return_value=discovered)),
            patch("bleak.BleakClient", OmittedServiceBleakClient),
            patch("blueboard_macro_handler.client.sys.platform", "linux"),
            patch.object(client, "runBluezGatttoolFallback", side_effect=fallback),
        ):
            await client.run(stopEvent)
        self.assertEqual(fallbackCalls, 2)
        self.assertEqual(metrics.reconnects, 1)

    async def testInteractiveGatttoolDetectsSilentDisconnect(self) -> None:
        feedback = FakeLedFeedback()
        process = FakeGatttoolProcess([])
        process.stdout = HealthCheckGatttoolStdout()
        characteristicProcess, descriptorProcess = discoveryProcesses()
        client = BlueBoardClient(lambda _event: None, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1, ledFeedback=feedback)
        with (
            patch(
                "blueboard_macro_handler.client.shutil.which",
                side_effect=lambda name: "/usr/bin/gatttool" if name == "gatttool" else None,
            ),
            patch("blueboard_macro_handler.client.gatttoolHealthCheckSeconds", 0.001),
            patch(
                "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
                AsyncMock(side_effect=(characteristicProcess, descriptorProcess, process)),
            ),
            self.assertRaisesRegex(RuntimeError, "connection was lost"),
        ):
            await client.runBluezGatttoolFallback("AA:BB", "iRig BlueBoard", asyncio.Event())
        self.assertIn(b"char-read-hnd 0x0023\n", process.stdin.values)
        self.assertTrue(process.terminated)

    def testStateRoundTrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            saveLastAddress(path, "AA:BB")
            self.assertEqual(loadLastAddress(path), "AA:BB")

    def testParsesGatttoolMidiNotification(self) -> None:
        line = "Notification handle = 0x0022 value: 80 80 b0 14 7f"
        self.assertEqual(parseGatttoolNotification(line, 0x0022), bytes.fromhex("80 80 b0 14 7f"))

    def testIgnoresOtherGatttoolOutput(self) -> None:
        self.assertIsNone(parseGatttoolNotification("Characteristic value was written successfully", 0x0022))
        self.assertIsNone(parseGatttoolNotification("Notification handle = 0x001c value: 64", 0x0022))

    def testParsesGatttoolCharacteristicAndDescriptorListings(self) -> None:
        characteristicProcess, descriptorProcess = discoveryProcesses(0x0042, 0x0043)
        characteristics = parseGatttoolCharacteristics(characteristicProcess.output.decode())
        descriptors = parseGatttoolDescriptors(descriptorProcess.output.decode())
        self.assertEqual(characteristics[0][:2], (0x0021, 0x0042))
        self.assertEqual(descriptors[0], (0x0043, "00002902-0000-1000-8000-00805f9b34fb"))

    async def testDiscoversAlternateGattHandles(self) -> None:
        characteristicProcess, descriptorProcess = discoveryProcesses(0x0042, 0x0043)
        with patch(
            "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=(characteristicProcess, descriptorProcess)),
        ):
            profile = await discoverBlueBoardGattProfile("/usr/bin/gatttool", "AA:BB")
        self.assertEqual((profile.midiValueHandle, profile.midiCccHandle, profile.source), (0x0042, 0x0043, "discovered"))

    async def testNamedTestedProfileIsUsedOnlyForKnownBlueBoard(self) -> None:
        noMidi = FakeGatttoolQueryProcess(
            "handle = 0x0002, char properties = 0x02, char value handle = 0x0003, "
            "uuid = 00002a00-0000-1000-8000-00805f9b34fb\n"
        )
        with patch(
            "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
            AsyncMock(return_value=noMidi),
        ):
            profile = await resolveBlueBoardGattProfile("/usr/bin/gatttool", "AA:BB", "IRIG BLUEBOARD")
        self.assertEqual(profile, testedBlueBoardGattProfile)
        with patch(
            "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
            AsyncMock(return_value=noMidi),
        ), self.assertRaisesRegex(RuntimeError, "unknown device"):
            await resolveBlueBoardGattProfile("/usr/bin/gatttool", "AA:BB", "Other Pedal")

    async def testNamedProfileDoesNotMaskMalformedDiscovery(self) -> None:
        malformed = FakeGatttoolQueryProcess("malformed output\n")
        with patch(
            "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
            AsyncMock(return_value=malformed),
        ), self.assertRaisesRegex(RuntimeError, "no valid characteristic"):
            await resolveBlueBoardGattProfile("/usr/bin/gatttool", "AA:BB", "iRig BlueBoard")

    async def testGattDiscoveryRejectsDuplicateOrMissingCccd(self) -> None:
        characteristicProcess, descriptorProcess = discoveryProcesses()
        duplicateCharacteristics = FakeGatttoolQueryProcess(
            characteristicProcess.output.decode() * 2
        )
        with patch(
            "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
            AsyncMock(return_value=duplicateCharacteristics),
        ), self.assertRaisesRegex(RuntimeError, "found 2"):
            await discoverBlueBoardGattProfile("/usr/bin/gatttool", "AA:BB")
        missingCccd = FakeGatttoolQueryProcess("handle = 0x0023, uuid = 00002901-0000-1000-8000-00805f9b34fb\n")
        with patch(
            "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=(characteristicProcess, missingCccd)),
        ), self.assertRaisesRegex(RuntimeError, "CCCD"):
            await discoverBlueBoardGattProfile("/usr/bin/gatttool", "AA:BB")
        duplicateCccd = FakeGatttoolQueryProcess(
            descriptorProcess.output.decode()
            + "handle = 0x0024, uuid = 00002902-0000-1000-8000-00805f9b34fb\n"
        )
        with patch(
            "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=(characteristicProcess, duplicateCccd)),
        ), self.assertRaisesRegex(RuntimeError, "found 2"):
            await discoverBlueBoardGattProfile("/usr/bin/gatttool", "AA:BB")

    async def testGatttoolFallbackRequiresInstalledTool(self) -> None:
        client = BlueBoardClient(
            lambda _event: None,
            lambda: None,
            nameSubstring="BlueBoard",
            address=None,
            pair=False,
            scanTimeout=1,
        )
        with patch("blueboard_macro_handler.client.shutil.which", return_value=None), self.assertRaisesRegex(
            RuntimeError,
            "gatttool is unavailable",
        ):
            await client.runBluezGatttoolFallback("AA:BB", "iRig BlueBoard", asyncio.Event())

    def testPersistentPairingIsRejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "pairing is not supported"):
            BlueBoardClient(
                lambda _event: None,
                lambda: None,
                nameSubstring="BlueBoard",
                address=None,
                pair=True,
                scanTimeout=1,
            )

    def testMetricsSnapshotIncludesStopReasonWhenKnown(self) -> None:
        metrics = RunMetrics(stopReason="duration-limit")
        self.assertEqual(metrics.snapshot()["stopReason"], "duration-limit")
