from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from queue import Empty, Queue
from time import monotonic, sleep
from typing import Literal

from .. import __version__
from ..models import RunMetrics
from .commands import MidiCommand, createSysExData, createSysExRead
from .parameters import parameterDefinitions, productionDefinitionsFor
from .protocol import SYSEX_END, SYSEX_START, KatanaSysExFrame, decodeBase128, parseKatanaSysEx
from .transport import MidiTransport, ReceivedMidiMessage

ProbeTarget = Literal["current-selection", "effect-states", "panel-snapshot"]

CURRENT_SELECTION_ADDRESS = (0x00, 0x01, 0x00, 0x00)
PANEL_SNAPSHOT_ADDRESS = (0x00, 0x00, 0x04, 0x00)
PANEL_SNAPSHOT_SIZE = 0x2A
EDITOR_MODE_ADDRESS = (0x7F, 0x00, 0x00, 0x01)


def formatMidiBytes(data: tuple[int, ...]) -> str:
    return " ".join(f"{value:02X}" for value in data)


@dataclass(frozen=True)
class SysExTrafficRecord:
    direction: Literal["sent", "received"]
    purpose: str
    data: tuple[int, ...]
    elapsedMs: float
    valid: bool | None = None
    error: str | None = None
    frame: KatanaSysExFrame | None = None


@dataclass(frozen=True)
class SysExObservation:
    name: str
    address: tuple[int, int, int, int]
    rawData: tuple[int, ...] | None
    decoded: str | bool | None
    latencyMs: float | None
    attempts: int
    error: str | None = None


@dataclass
class SysExProbeReport:
    target: ProbeTarget
    model: str
    deviceId: int
    inputName: str
    outputName: str
    connectionEpoch: int
    metrics: RunMetrics
    traffic: list[SysExTrafficRecord] = field(default_factory=list)
    observations: list[SysExObservation] = field(default_factory=list)

    @property
    def failures(self) -> tuple[SysExObservation, ...]:
        return tuple(observation for observation in self.observations if observation.error is not None)

    @property
    def success(self) -> bool:
        return bool(self.observations) and not self.failures

    def asFixture(self) -> dict[str, object]:
        traffic = []
        for record in self.traffic:
            item: dict[str, object] = {
                "direction": record.direction,
                "purpose": record.purpose,
                "bytes": formatMidiBytes(record.data),
                "elapsedMs": round(record.elapsedMs, 3),
            }
            if record.valid is not None:
                item["valid"] = record.valid
            if record.error is not None:
                item["error"] = record.error
            if record.frame is not None:
                item["frame"] = {
                    "deviceId": record.frame.deviceId,
                    "command": record.frame.command,
                    "address": formatMidiBytes(record.frame.address),
                    "data": formatMidiBytes(record.frame.data),
                    "checksum": f"{record.frame.checksum:02X}",
                }
            traffic.append(item)
        return {
            "schemaVersion": 1,
            "projectVersion": __version__,
            "model": self.model,
            "deviceId": self.deviceId,
            "inputName": self.inputName,
            "outputName": self.outputName,
            "readTarget": self.target,
            "connectionEpoch": self.connectionEpoch,
            "success": self.success,
            "traffic": traffic,
            "observations": [
                {
                    "name": observation.name,
                    "address": formatMidiBytes(observation.address),
                    "data": None if observation.rawData is None else formatMidiBytes(observation.rawData),
                    "decoded": observation.decoded,
                    "latencyMs": observation.latencyMs,
                    "attempts": observation.attempts,
                    "error": observation.error,
                }
                for observation in self.observations
            ],
        }


class KatanaSysExSession:
    """One bounded, serialized Katana SysEx reader.

    Incoming Mido callback work is limited to copying and enqueueing messages;
    parsing and matching happen on the owning caller/worker thread. Diagnostic
    probes and the runtime state bootstrap share this request matcher.
    """

    def __init__(
        self,
        transport: MidiTransport,
        *,
        deviceId: int = 0,
        timeoutMs: int = 750,
        retries: int = 1,
        editorSettleMs: int = 75,
        metrics: RunMetrics | None = None,
        clock: Callable[[], float] = monotonic,
        sleepFunction: Callable[[float], None] = sleep,
    ) -> None:
        if not isinstance(deviceId, int) or isinstance(deviceId, bool) or not 0 <= deviceId <= 0x7F:
            raise ValueError("SysEx device ID must be an integer from 0 to 127")
        if not isinstance(timeoutMs, int) or isinstance(timeoutMs, bool) or timeoutMs <= 0:
            raise ValueError("SysEx timeout must be a positive integer number of milliseconds")
        if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
            raise ValueError("SysEx retries must be a non-negative integer")
        if not isinstance(editorSettleMs, int) or isinstance(editorSettleMs, bool) or editorSettleMs < 0:
            raise ValueError("editor settle time must be a non-negative integer number of milliseconds")
        self.transport = transport
        self.deviceId = deviceId
        self.timeoutSeconds = timeoutMs / 1000
        self.retries = retries
        self.editorSettleSeconds = editorSettleMs / 1000
        self.metrics = metrics or RunMetrics()
        self.clock = clock
        self.sleepFunction = sleepFunction
        self.incoming: Queue[ReceivedMidiMessage] = Queue()
        self.connectionEpoch = 0
        self.startedAt = self.clock()
        self.report: SysExProbeReport | None = None

    def _enqueue(self, message: ReceivedMidiMessage) -> None:
        self.incoming.put(message)

    def open(self, inputName: str, outputName: str, *, target: ProbeTarget, model: str = "katana100") -> None:
        try:
            # The input must be listening before a request can trigger an immediate reply.
            self.transport.openInput(inputName, self._enqueue)
            self.transport.open(outputName)
        except Exception:
            self.transport.close()
            raise
        self.connectionEpoch += 1
        self.startedAt = self.clock()
        while True:
            try:
                self.incoming.get_nowait()
            except Empty:
                break
        resolvedInput = getattr(self.transport, "inputName", None) or inputName
        resolvedOutput = getattr(self.transport, "outputName", None) or outputName
        self.report = SysExProbeReport(
            target,
            model,
            self.deviceId,
            resolvedInput,
            resolvedOutput,
            self.connectionEpoch,
            self.metrics,
        )

    def close(self) -> None:
        self.transport.close()

    def _elapsedMs(self, timestamp: float | None = None) -> float:
        return round(((self.clock() if timestamp is None else timestamp) - self.startedAt) * 1000, 3)

    def _send(self, command: MidiCommand, purpose: str, *, request: bool = False) -> float:
        if self.report is None:
            raise RuntimeError("Katana SysEx probe ports are not open")
        sentAt = self.clock()
        try:
            self.transport.send(command)
        except Exception as error:
            self.metrics.katanaCommandFailures += 1
            self.report.traffic.append(
                SysExTrafficRecord(
                    "sent",
                    purpose,
                    command.data,
                    self._elapsedMs(sentAt),
                    valid=False,
                    error=str(error),
                )
            )
            raise
        self.metrics.katanaCommands += 1
        if request:
            self.metrics.katanaSysExRequests += 1
        self.report.traffic.append(
            SysExTrafficRecord("sent", purpose, command.data, self._elapsedMs(sentAt), valid=True)
        )
        return sentAt

    def _parseIncoming(self, message: ReceivedMidiMessage) -> tuple[KatanaSysExFrame | None, tuple[int, ...]]:
        if self.report is None:
            raise RuntimeError("Katana SysEx probe ports are not open")
        self.metrics.katanaInputMessages += 1
        if message.messageType != "sysex":
            raw = message.data
            self.report.traffic.append(
                SysExTrafficRecord(
                    "received",
                    "unrelated-midi",
                    raw,
                    self._elapsedMs(message.receivedAt),
                    valid=False,
                    error=f"non-SysEx message type {message.messageType}",
                )
            )
            return None, raw
        raw = (SYSEX_START, *message.data, SYSEX_END)
        try:
            frame = parseKatanaSysEx(message.data, includesFraming=False)
        except (TypeError, ValueError) as error:
            if "checksum" in str(error).casefold():
                self.metrics.katanaSysExChecksumFailures += 1
            self.report.traffic.append(
                SysExTrafficRecord(
                    "received",
                    "invalid-sysex",
                    raw,
                    self._elapsedMs(message.receivedAt),
                    valid=False,
                    error=str(error),
                )
            )
            return None, raw
        self.metrics.katanaSysExReplies += 1
        self.report.traffic.append(
            SysExTrafficRecord(
                "received",
                "parsed-sysex",
                raw,
                self._elapsedMs(message.receivedAt),
                valid=True,
                frame=frame,
            )
        )
        return frame, raw

    def _nextFrame(self, deadline: float) -> tuple[KatanaSysExFrame, tuple[int, ...], float] | None:
        while True:
            remaining = deadline - self.clock()
            if remaining <= 0:
                return None
            try:
                message = self.incoming.get(timeout=remaining)
            except Empty:
                return None
            frame, raw = self._parseIncoming(message)
            if frame is not None:
                return frame, raw, message.receivedAt

    def _markLastReplyUnexpected(self, error: str) -> None:
        if self.report is None or not self.report.traffic:
            return
        record = self.report.traffic[-1]
        if record.direction == "received":
            self.report.traffic[-1] = replace(record, purpose="unexpected-reply", valid=False, error=error)

    def _queryExact(
        self,
        name: str,
        address: tuple[int, int, int, int],
        dataLength: int,
        decoder: Callable[[tuple[int, ...]], str | bool],
    ) -> SysExObservation:
        request = createSysExRead(self.deviceId, address, dataLength)
        for attempt in range(1, self.retries + 2):
            sentAt = self._send(request, f"rq1:{name}:attempt-{attempt}", request=True)
            deadline = sentAt + self.timeoutSeconds
            while True:
                incoming = self._nextFrame(deadline)
                if incoming is None:
                    break
                frame, _raw, receivedAt = incoming
                if frame.command != "dt1" or frame.deviceId != self.deviceId or frame.address != address:
                    self.metrics.katanaSysExUnexpectedReplies += 1
                    self._markLastReplyUnexpected(
                        f"expected DT1 deviceId={self.deviceId} address={formatMidiBytes(address)}"
                    )
                    continue
                latencyMs = round((receivedAt - sentAt) * 1000, 3)
                if len(frame.data) != dataLength:
                    return SysExObservation(
                        name,
                        address,
                        frame.data,
                        None,
                        latencyMs,
                        attempt,
                        f"unexpected data length {len(frame.data)}; expected {dataLength}",
                    )
                try:
                    decoded = decoder(frame.data)
                except ValueError as error:
                    return SysExObservation(name, address, frame.data, None, latencyMs, attempt, str(error))
                return SysExObservation(name, address, frame.data, decoded, latencyMs, attempt)
            self.metrics.katanaSysExTimeouts += 1
            if attempt <= self.retries:
                self.metrics.katanaSysExRetries += 1
        return SysExObservation(
            name,
            address,
            None,
            None,
            None,
            self.retries + 1,
            f"request sent, no matching reply within {self.timeoutSeconds * 1000:g} ms",
        )

    @staticmethod
    def _decodeSelection(data: tuple[int, ...]) -> str:
        selections = {
            (0x00, 0x00): "Panel",
            (0x00, 0x01): "CH1",
            (0x00, 0x02): "CH2",
            (0x00, 0x03): "CH3",
            (0x00, 0x04): "CH4",
        }
        if data not in selections:
            raise ValueError(f"unknown current-selection value: {formatMidiBytes(data)}")
        return selections[data]

    def _queryCurrentSelection(self) -> None:
        if self.report is None:
            raise RuntimeError("Katana SysEx probe ports are not open")
        attemptedEnter = False
        primaryError: BaseException | None = None
        try:
            attemptedEnter = True
            self._send(createSysExData(self.deviceId, EDITOR_MODE_ADDRESS, (0x01,)), "editor-mode-enter")
            self.sleepFunction(self.editorSettleSeconds)
            self.report.observations.append(
                self._queryExact("current-selection", CURRENT_SELECTION_ADDRESS, 2, self._decodeSelection)
            )
        except BaseException as error:
            primaryError = error
            raise
        finally:
            if attemptedEnter:
                try:
                    self._send(createSysExData(self.deviceId, EDITOR_MODE_ADDRESS, (0x00,)), "editor-mode-exit")
                except Exception:
                    if primaryError is None:
                        raise

    def _queryEffectStates(self) -> None:
        if self.report is None:
            raise RuntimeError("Katana SysEx probe ports are not open")
        for definition in parameterDefinitions.values():
            if definition.model != self.report.model or not definition.mayProbe:
                continue
            self.report.observations.append(
                self._queryExact(
                    definition.name,
                    definition.address,
                    definition.dataLength,
                    definition.decodeValue,
                )
            )

    def readProductionEffectStates(self, *, firmware: str) -> tuple[SysExObservation, ...]:
        """Read every production-approved effect flag for the active model/firmware."""
        if self.report is None:
            raise RuntimeError("Katana SysEx session ports are not open")
        definitions = productionDefinitionsFor(self.report.model, firmware)
        if not definitions:
            raise RuntimeError(
                f"no production-approved SysEx effect definitions for "
                f"model={self.report.model} firmware={firmware!r}"
            )
        observations = tuple(
            self._queryExact(
                definition.name,
                definition.address,
                definition.dataLength,
                definition.decodeValue,
            )
            for definition in definitions
        )
        self.report.observations.extend(observations)
        return observations

    def _queryPanelSnapshot(self) -> None:
        if self.report is None:
            raise RuntimeError("Katana SysEx probe ports are not open")
        request = createSysExRead(self.deviceId, PANEL_SNAPSHOT_ADDRESS, PANEL_SNAPSHOT_SIZE)
        start = decodeBase128(PANEL_SNAPSHOT_ADDRESS)
        end = start + PANEL_SNAPSHOT_SIZE
        for attempt in range(1, self.retries + 2):
            sentAt = self._send(request, f"rq1:panel-snapshot:attempt-{attempt}", request=True)
            deadline = sentAt + self.timeoutSeconds
            matched = 0
            while True:
                incoming = self._nextFrame(deadline)
                if incoming is None:
                    break
                frame, _raw, receivedAt = incoming
                addressValue = decodeBase128(frame.address)
                if frame.command != "dt1" or frame.deviceId != self.deviceId or not start <= addressValue < end:
                    self.metrics.katanaSysExUnexpectedReplies += 1
                    self._markLastReplyUnexpected(
                        f"expected DT1 deviceId={self.deviceId} inside panel-snapshot address span"
                    )
                    continue
                matched += 1
                self.report.observations.append(
                    SysExObservation(
                        f"panel-snapshot@{formatMidiBytes(frame.address)}",
                        frame.address,
                        frame.data,
                        formatMidiBytes(frame.data),
                        round((receivedAt - sentAt) * 1000, 3),
                        attempt,
                    )
                )
            if matched:
                return
            self.metrics.katanaSysExTimeouts += 1
            if attempt <= self.retries:
                self.metrics.katanaSysExRetries += 1
        self.report.observations.append(
            SysExObservation(
                "panel-snapshot",
                PANEL_SNAPSHOT_ADDRESS,
                None,
                None,
                None,
                self.retries + 1,
                f"request sent, no matching reply within {self.timeoutSeconds * 1000:g} ms",
            )
        )

    def probe(self) -> SysExProbeReport:
        if self.report is None:
            raise RuntimeError("Katana SysEx probe ports are not open")
        if self.report.target == "current-selection":
            self._queryCurrentSelection()
        elif self.report.target == "effect-states":
            self._queryEffectStates()
        elif self.report.target == "panel-snapshot":
            self._queryPanelSnapshot()
        else:
            raise ValueError(f"unsupported SysEx probe target: {self.report.target!r}")
        return self.report


class KatanaSysExProbe(KatanaSysExSession):
    """Backward-compatible name for the bounded diagnostic CLI session."""
