import asyncio
import unittest

from blueboard_macro_handler.led_feedback import LedFeedbackController, blueBoardButtonCcs
from blueboard_macro_handler.models import RunMetrics


class LedFeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.writes = []
        self.metrics = RunMetrics()
        self.controller = LedFeedbackController(self.metrics, writeInterval=0, releaseRetryDelay=3600)

        async def write(packet, response):
            self.writes.append((packet, response))

        await self.controller.bind(write)

    async def asyncTearDown(self) -> None:
        await self.controller.unbind()

    async def testBindInitializesAllButtonsOff(self) -> None:
        self.assertEqual(
            self.writes,
            [(bytes((0x80, 0x80, 0xB0, cc, 0)), False) for cc in blueBoardButtonCcs],
        )

    async def testEveryFeedbackPacketUsesBlueBoardCompatibleZeroTimestamp(self) -> None:
        self.writes.clear()
        for cc in blueBoardButtonCcs:
            self.controller.setLed(cc, True)
        await self.controller.flush()
        self.assertTrue(self.writes)
        self.assertTrue(all(packet[:2] == bytes((0x80, 0x80)) for packet, _response in self.writes))

    async def testStateChangesCoalesceAndDuplicatesAreSuppressed(self) -> None:
        self.writes.clear()
        self.assertTrue(self.controller.setLed(20, True))
        self.assertFalse(self.controller.setLed(20, True))
        self.assertTrue(self.controller.setLed(20, False))
        await self.controller.flush()
        self.assertEqual([(packet[3], packet[4]) for packet, _response in self.writes], [(20, 0)])
        self.assertEqual(self.metrics.ledFeedbackWrites, 5)

    async def testCoalescingCoversEveryButton(self) -> None:
        self.writes.clear()
        for cc in blueBoardButtonCcs:
            self.controller.setLed(cc, True)
            self.controller.setLed(cc, False)
        await self.controller.flush()
        self.assertEqual(
            [(packet[2], packet[3], packet[4]) for packet, _response in self.writes],
            [(0xB0, cc, 0) for cc in blueBoardButtonCcs],
        )

    async def testUnboundControllerDoesNotQueueWrites(self) -> None:
        await self.controller.unbind()
        self.assertFalse(self.controller.setLed(20, True))

    async def testRebindReinitializesAllButtonsOff(self) -> None:
        self.writes.clear()

        async def write(packet, response):
            self.writes.append((packet, response))

        await self.controller.bind(write)
        self.assertEqual([(packet[3], packet[4]) for packet, _response in self.writes], [(cc, 0) for cc in blueBoardButtonCcs])

    async def testWriteFailureIsCountedAndWorkerContinues(self) -> None:
        shouldFail = True

        async def write(packet, response):
            nonlocal shouldFail
            if shouldFail:
                shouldFail = False
                raise RuntimeError("test failure")
            self.writes.append((packet, response))

        await self.controller.bind(write)
        self.controller.setLed(20, True)
        await self.controller.flush()
        self.assertEqual(self.metrics.ledFeedbackFailures, 1)
        self.assertEqual(self.writes[-1][0][3:5], bytes((20, 127)))

    async def testRapidChangesCoalesceToTheLatestState(self) -> None:
        await self.controller.unbind()
        writes = []

        async def write(packet, response):
            writes.append((packet, response))

        self.controller = LedFeedbackController(self.metrics, writeInterval=0.01, releaseRetryDelay=3600)
        await self.controller.bind(write)
        writes.clear()
        self.controller.setLed(20, True)
        self.controller.setLed(20, False)
        await self.controller.flush()
        self.assertEqual([(packet[3], packet[4]) for packet, _response in writes], [(20, 0)])

    async def testReleaseIsRetriedWithoutBackgroundRefresh(self) -> None:
        await self.controller.unbind()
        writes = []

        async def write(packet, response):
            writes.append((packet, response))

        self.controller = LedFeedbackController(self.metrics, writeInterval=0, releaseRetryDelay=0.01)
        await self.controller.bind(write)
        writes.clear()
        self.controller.setLed(20, True)
        await self.controller.flush()
        self.controller.setLed(20, False)
        await self.controller.flush()
        await asyncio.sleep(0.02)
        await self.controller.flush()
        self.assertEqual([(packet[3], packet[4]) for packet, _response in writes], [(20, 127), (20, 0), (20, 0)])

    async def testPressCancelsPendingReleaseRetry(self) -> None:
        await self.controller.unbind()
        writes = []

        async def write(packet, response):
            writes.append((packet, response))

        self.controller = LedFeedbackController(self.metrics, writeInterval=0, releaseRetryDelay=0.02)
        await self.controller.bind(write)
        writes.clear()
        self.controller.setLed(20, True)
        await self.controller.flush()
        self.controller.setLed(20, False)
        await self.controller.flush()
        self.controller.setLed(20, True)
        await asyncio.sleep(0.03)
        await self.controller.flush()
        self.assertEqual([(packet[3], packet[4]) for packet, _response in writes], [(20, 127), (20, 0), (20, 127)])

    async def testIdleControllerDoesNotSendBackgroundWrites(self) -> None:
        await self.controller.unbind()
        writes = []

        async def write(packet, response):
            writes.append((packet, response))

        self.controller = LedFeedbackController(self.metrics, writeInterval=0, releaseRetryDelay=0.01)
        await self.controller.bind(write)
        writes.clear()
        await asyncio.sleep(0.02)
        await self.controller.flush()
        self.assertEqual(writes, [])

    async def testRejectsUnsupportedController(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported BlueBoard LED CC"):
            self.controller.setLed(19, True)


if __name__ == "__main__":
    unittest.main()
