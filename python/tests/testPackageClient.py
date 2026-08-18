import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from blueboard_macro_handler.client import BlueBoardClient, DiscoveredDevice, parseGatttoolNotification
from blueboard_macro_handler.models import RunMetrics
from blueboard_macro_handler.state import loadLastAddress, saveLastAddress


class FakeServices:
    def get_service(self, _uuid): return object()
    def get_characteristic(self, _uuid): return type("Characteristic", (), {"properties": ["write"]})()


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
    async def write_gatt_char(self, *_args, **_kwargs): pass


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
        await asyncio.gather(*(client.writePacket(bytes((value,))) for value in range(4)))
        self.assertEqual(maxActive, 1)

    async def testWritePacketUsesActiveGatttoolSession(self) -> None:
        client = BlueBoardClient(lambda _: None, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1)
        writer = FakeGatttoolStdin()
        client.gatttoolStdin = writer
        await client.writePacket(bytes.fromhex("80 80 b0 14 7f"), response=False)
        self.assertEqual(writer.values, [b"char-write-cmd 0x0022 8080b0147f\n"])

    async def testInteractiveGatttoolSubscribesAndBindsFeedback(self) -> None:
        stopEvent, feedback = asyncio.Event(), FakeLedFeedback()
        lines = [
            b"Connection successful\n",
            b"Characteristic value was written successfully\n",
            b"Notification handle = 0x0022 value: 80 80 b0 14 7f\n",
        ]
        process = FakeGatttoolProcess(lines)

        def receive(_event): stopEvent.set()

        client = BlueBoardClient(receive, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1, ledFeedback=feedback)
        with patch("blueboard_macro_handler.client.shutil.which", side_effect=lambda name: "/usr/bin/gatttool" if name == "gatttool" else None), patch("blueboard_macro_handler.client.asyncio.create_subprocess_exec", AsyncMock(return_value=process)):
            await client.runBluezGatttoolFallback("AA:BB", stopEvent)
        self.assertEqual(process.stdin.values[:2], [b"connect\n", b"char-write-req 0x0023 0100\n"])
        self.assertEqual((feedback.bound, feedback.unbound), (1, 1))
        self.assertTrue(process.terminated)

    async def testGatttoolKeepsValidatedNoninteractivePathWithoutFeedback(self) -> None:
        stopEvent = asyncio.Event()
        process = FakeGatttoolProcess([
            b"Characteristic value was written successfully\n",
            b"Notification handle = 0x0022 value: 80 80 b0 14 7f\n",
        ])

        def receive(_event): stopEvent.set()

        client = BlueBoardClient(receive, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1)
        createProcess = AsyncMock(return_value=process)
        with patch("blueboard_macro_handler.client.shutil.which", side_effect=lambda name: "/usr/bin/gatttool" if name == "gatttool" else None), patch("blueboard_macro_handler.client.asyncio.create_subprocess_exec", createProcess):
            await client.runBluezGatttoolFallback("AA:BB", stopEvent)
        command = createProcess.await_args.args
        self.assertIn("--listen", command)
        self.assertIsNone(createProcess.await_args.kwargs["stdin"])
        self.assertEqual(process.stdin.values, [])

    async def testInteractiveGatttoolDetectsSilentDisconnect(self) -> None:
        feedback = FakeLedFeedback()
        process = FakeGatttoolProcess([])
        process.stdout = HealthCheckGatttoolStdout()
        client = BlueBoardClient(lambda _event: None, lambda: None, nameSubstring="BlueBoard", address=None, pair=False, scanTimeout=1, ledFeedback=feedback)
        with (
            patch(
                "blueboard_macro_handler.client.shutil.which",
                side_effect=lambda name: "/usr/bin/gatttool" if name == "gatttool" else None,
            ),
            patch("blueboard_macro_handler.client.gatttoolHealthCheckSeconds", 0.001),
            patch(
                "blueboard_macro_handler.client.asyncio.create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            self.assertRaisesRegex(RuntimeError, "connection was lost"),
        ):
            await client.runBluezGatttoolFallback("AA:BB", asyncio.Event())
        self.assertIn(b"char-read-hnd 0x0023\n", process.stdin.values)
        self.assertTrue(process.terminated)

    def testStateRoundTrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            saveLastAddress(path, "AA:BB")
            self.assertEqual(loadLastAddress(path), "AA:BB")

    def testParsesGatttoolMidiNotification(self) -> None:
        line = "Notification handle = 0x0022 value: 80 80 b0 14 7f"
        self.assertEqual(parseGatttoolNotification(line), bytes.fromhex("80 80 b0 14 7f"))

    def testIgnoresOtherGatttoolOutput(self) -> None:
        self.assertIsNone(parseGatttoolNotification("Characteristic value was written successfully"))
        self.assertIsNone(parseGatttoolNotification("Notification handle = 0x001c value: 64"))
