from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .ble_midi import encodeBleMidi
from .models import RunMetrics

logger = logging.getLogger("blueboard.ledFeedback")

blueBoardButtonCcs = (20, 21, 22, 23)
PacketWriter = Callable[[bytes, bool], Awaitable[None]]


class LedFeedbackController:
    def __init__(
        self,
        metrics: RunMetrics | None = None,
        queueSize: int = 1024,
        writeInterval: float = 0.125,
        releaseRetryDelay: float = 0.2,
    ) -> None:
        if queueSize < len(blueBoardButtonCcs):
            raise ValueError(f"LED feedback queue must hold at least {len(blueBoardButtonCcs)} requests")
        if writeInterval < 0:
            raise ValueError("LED feedback write interval cannot be negative")
        if releaseRetryDelay <= 0:
            raise ValueError("LED feedback release retry delay must be positive")
        self.metrics = metrics or RunMetrics()
        self.queue: asyncio.Queue[int] = asyncio.Queue(maxsize=queueSize)
        self.queueSize, self.writeInterval, self.releaseRetryDelay = queueSize, writeInterval, releaseRetryDelay
        self.writer: PacketWriter | None = None
        self.worker: asyncio.Task | None = None
        self.releaseRetries: dict[int, asyncio.Task] = {}
        self.requestedState: dict[int, bool] = {cc: False for cc in blueBoardButtonCcs}
        self.queuedCcs: set[int] = set()
        self.writeResponse = False

    async def bind(self, writer: PacketWriter, *, response: bool = False) -> None:
        await self.unbind()
        self.writer = writer
        self.writeResponse = response
        self.worker = asyncio.create_task(self.consume(), name="blueboard-led-feedback")
        self.clearAll()
        await self.flush()
        logger.info(
            "LED feedback enabled; initialized buttons A-D off writeResponse=%s",
            "yes" if self.writeResponse else "no",
        )

    async def unbind(self) -> None:
        workers = [worker for worker in (self.worker, *self.releaseRetries.values()) if worker is not None]
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self.worker = None
        self.releaseRetries.clear()
        self.writer = None
        self.writeResponse = False
        self.requestedState = {cc: False for cc in blueBoardButtonCcs}
        self.queuedCcs.clear()
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()

    def setLed(self, cc: int, isOn: bool, *, force: bool = False) -> bool:
        if cc not in blueBoardButtonCcs:
            raise ValueError(f"unsupported BlueBoard LED CC: {cc}")
        if self.writer is None:
            return False
        if not force and self.requestedState.get(cc) == isOn:
            return False
        self.cancelReleaseRetry(cc)
        self.requestedState[cc] = isOn
        queued = self.queueCc(cc)
        if not isOn:
            self.scheduleReleaseRetry(cc)
        return queued

    def clearAll(self) -> None:
        if self.writer is None:
            return
        for cc in blueBoardButtonCcs:
            self.requestedState[cc] = False
            self.queueCc(cc)

    def cancelReleaseRetry(self, cc: int) -> None:
        retry = self.releaseRetries.pop(cc, None)
        if retry is not None:
            retry.cancel()

    def scheduleReleaseRetry(self, cc: int) -> None:
        async def retryRelease() -> None:
            try:
                await asyncio.sleep(self.releaseRetryDelay)
                if self.writer is not None and not self.requestedState[cc]:
                    logger.debug("button=%s cc=%d retrying LED=off", chr(ord("A") + cc - 20), cc)
                    self.queueCc(cc)
            finally:
                if self.releaseRetries.get(cc) is asyncio.current_task():
                    self.releaseRetries.pop(cc, None)

        self.releaseRetries[cc] = asyncio.create_task(retryRelease(), name=f"blueboard-led-release-{cc}")

    def queueCc(self, cc: int) -> bool:
        if cc in self.queuedCcs:
            return True
        try:
            self.queue.put_nowait(cc)
        except asyncio.QueueFull:
            self.metrics.ledFeedbackDrops += 1
            logger.error("LED feedback queue full; button CC%d state update dropped", cc)
            return False
        self.queuedCcs.add(cc)
        return True

    async def flush(self) -> None:
        await self.queue.join()

    async def consume(self) -> None:
        while True:
            cc = await self.queue.get()
            self.queuedCcs.discard(cc)
            try:
                if self.writer is None:
                    continue
                isOn = self.requestedState[cc]
                packet = encodeBleMidi(0xB0, bytes((cc, 127 if isOn else 0)), timestamp=0)
                await self.writer(packet, self.writeResponse)
                self.metrics.ledFeedbackWrites += 1
                logger.debug(
                    "packet=%s button=%s cc=%d LED=%s",
                    packet.hex(" "),
                    chr(ord("A") + cc - 20),
                    cc,
                    "on" if isOn else "off",
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                self.metrics.ledFeedbackFailures += 1
                logger.exception("button CC%d LED feedback write failed", cc)
                self.queueCc(cc)
            finally:
                self.queue.task_done()
            if self.writeInterval:
                await asyncio.sleep(self.writeInterval)
