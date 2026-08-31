from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from time import monotonic
from typing import Literal

from ..config import ActionSpec, KatanaConfig
from ..models import RunMetrics
from .commands import MidiCommand, createControlChange, createProgramChange
from .session import KatanaSysExSession, SysExObservation
from .transport import MidiTransport

logger = logging.getLogger("blueboard.katana")

StateSource = Literal["queried", "predicted", "unknown", "stale"]

effectParameterNames = (
    "effects.boost.enabled",
    "effects.mod.enabled",
    "effects.fx.enabled",
    "effects.delay.enabled",
    "effects.reverb.enabled",
    "effects.effectLoop.enabled",
)

groupParameterNames = {
    "booster": ("effects.boost.enabled", "effects.mod.enabled"),
    "delay": ("effects.delay.enabled", "effects.fx.enabled"),
    "reverb": ("effects.reverb.enabled",),
    "effectLoop": ("effects.effectLoop.enabled",),
}


@dataclass(frozen=True)
class EffectStateValue:
    value: bool | None
    source: StateSource
    observedAt: float | None
    epoch: int
    error: str | None = None


@dataclass(frozen=True)
class AmpStateSnapshot:
    epoch: int
    publishedAt: float
    effects: dict[str, EffectStateValue]


def unknownSnapshot(epoch: int, error: str | None = None) -> AmpStateSnapshot:
    return AmpStateSnapshot(
        epoch,
        monotonic(),
        {
            name: EffectStateValue(None, "unknown", None, epoch, error)
            for name in effectParameterNames
        },
    )


def deriveGroupState(snapshot: AmpStateSnapshot, effect: str) -> bool | None:
    names = groupParameterNames.get(effect)
    if names is None:
        return None
    values = tuple(
        snapshot.effects[name].value
        if snapshot.effects[name].source in {"queried", "predicted"}
        else None
        for name in names
    )
    if any(value is True for value in values):
        return True
    if all(value is False for value in values):
        return False
    return None


class KatanaRuntime:
    """Serialized owner of live Katana MIDI reads, PC messages, and CC messages."""

    def __init__(self, config: KatanaConfig, transport: MidiTransport, metrics: RunMetrics | None = None) -> None:
        self.config = config
        self.transport = transport
        self.metrics = metrics or RunMetrics()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="katana-midi")
        self.session: KatanaSysExSession | None = None
        self.snapshot = unknownSnapshot(0)
        self.effectState: dict[str, bool] = {}
        self.currentPreset: int | None = None
        self.connectionEpoch = 0
        self.isOpen = False
        self.hasOpened = False
        self.closed = False

    def start(self) -> Future[AmpStateSnapshot]:
        if self.closed:
            raise RuntimeError("Katana runtime is closed")
        if not self.config.stateSync.enabled:
            completed: Future[AmpStateSnapshot] = Future()
            completed.set_result(self.snapshot)
            return completed
        return self.executor.submit(self._ensureOpenAndSync)

    def execute(self, action: ActionSpec) -> Future[None]:
        if self.closed:
            raise RuntimeError("Katana runtime is closed")
        future = self.executor.submit(self._execute, action)

        def reportFailure(completed: Future[None]) -> None:
            error = completed.exception()
            if error is not None:
                self.metrics.actionFailures += 1
                logger.error("Katana action failed asynchronously: %s", error)

        future.add_done_callback(reportFailure)
        return future

    # Synchronous compatibility helpers for direct library callers. The live
    # dispatcher uses execute(), which queues and returns immediately.
    def selectPreset(self, preset: int) -> None:
        self.executor.submit(self._selectPreset, preset).result()

    def setEffectState(self, effect: str, enabled: bool) -> None:
        self.executor.submit(self._setEffectState, effect, enabled).result()

    def toggleEffect(self, effect: str) -> None:
        self.executor.submit(self._toggleEffect, effect).result()

    def _openOutputOnly(self) -> AmpStateSnapshot:
        try:
            self.transport.open(self.config.outputName)
        except Exception:
            self._invalidate("Katana MIDI output open failed")
            raise
        self._markOpened()
        logger.info("katana output=%r state=open sync=disabled", self.config.outputName)
        return self.snapshot

    def _ensureOpenAndSync(self) -> AmpStateSnapshot:
        if self.isOpen:
            return self.snapshot
        if not self.config.stateSync.enabled:
            return self._openOutputOnly()
        if self.config.inputName is None:
            raise RuntimeError("Katana inputName is required for runtime state synchronization")
        session = KatanaSysExSession(
            self.transport,
            deviceId=self.config.deviceId,
            timeoutMs=self.config.stateSync.requestTimeoutMs,
            retries=self.config.stateSync.requestRetries,
            metrics=self.metrics,
        )
        try:
            session.open(
                self.config.inputName,
                self.config.outputName,
                target="effect-states",
                model=self.config.model,
            )
        except Exception:
            self._invalidate("Katana duplex MIDI open failed")
            raise
        self.session = session
        self._markOpened()
        logger.info(
            "katana input=%r output=%r state=open epoch=%d",
            self.config.inputName,
            self.config.outputName,
            self.connectionEpoch,
        )
        return self._synchronize()

    def _markOpened(self) -> None:
        self.connectionEpoch += 1
        if self.hasOpened:
            self.metrics.katanaReconnects += 1
            if self.config.stateSync.enabled:
                self.metrics.katanaInputReconnects += 1
        self.hasOpened = True
        self.isOpen = True

    def _synchronize(self) -> AmpStateSnapshot:
        if self.session is None:
            return self.snapshot
        startedAt = monotonic()
        try:
            observations = self.session.readProductionEffectStates(firmware=self.config.firmware)
        except Exception as error:  # noqa: BLE001 - degradation is intentional for runtime reads.
            self.metrics.katanaStateSyncFailures += 1
            self.snapshot = unknownSnapshot(self.connectionEpoch, str(error))
            self.effectState = {}
            logger.warning("katana state sync=failed epoch=%d error=%s", self.connectionEpoch, error)
            return self.snapshot
        snapshot = self._snapshotFromObservations(observations, startedAt)
        self.snapshot = snapshot
        self.effectState = {
            effect: value
            for effect in self.config.effectControls
            if (value := deriveGroupState(snapshot, effect)) is not None
        }
        failures = tuple(item for item in observations if item.error is not None)
        if failures or any(name not in {item.name for item in observations} for name in effectParameterNames):
            self.metrics.katanaStateSyncFailures += 1
            status = "partial"
        else:
            self.metrics.katanaStateSyncs += 1
            status = "complete"
        logger.info(
            "katana state sync=%s epoch=%d latencyMs=%.3f",
            status,
            self.connectionEpoch,
            (monotonic() - startedAt) * 1000,
        )
        return snapshot

    def _snapshotFromObservations(
        self,
        observations: tuple[SysExObservation, ...],
        observedAt: float,
    ) -> AmpStateSnapshot:
        byName = {item.name: item for item in observations}
        effects: dict[str, EffectStateValue] = {}
        for name in effectParameterNames:
            observation = byName.get(name)
            value = observation.decoded if observation is not None else None
            if not isinstance(value, bool):
                value = None
            error = "missing production observation" if observation is None else observation.error
            source: StateSource = "queried" if value is not None and error is None else "unknown"
            effects[name] = EffectStateValue(value, source, observedAt if value is not None else None, self.connectionEpoch, error)
            logger.info(
                "katana state effect=%s value=%s source=%s epoch=%d",
                name,
                "unknown" if value is None else ("on" if value else "off"),
                source,
                self.connectionEpoch,
            )
        return AmpStateSnapshot(self.connectionEpoch, monotonic(), effects)

    def _send(self, command: MidiCommand, description: str) -> None:
        self._ensureOpenAndSync()
        try:
            self.transport.send(command)
        except Exception:
            self.metrics.katanaCommandFailures += 1
            self._invalidate("Katana MIDI send failed")
            raise
        self.metrics.katanaCommands += 1
        logger.info("katana output=%r %s bytes=%s", self.config.outputName, description, command.data)

    def _execute(self, action: ActionSpec) -> None:
        if action.command == "selectPreset" and action.preset is not None:
            self._selectPreset(action.preset)
        elif action.command == "setEffectState" and action.enabled is not None:
            self._setEffectState(action.effect, action.enabled)
        elif action.command == "toggleEffect":
            self._toggleEffect(action.effect)
        else:
            raise ValueError(f"unsupported Katana command: {action.command}")

    def _selectPreset(self, preset: int) -> None:
        self._send(
            createProgramChange(self.config.midiChannel - 1, preset),
            f"message=programChange channel={self.config.midiChannel} program={preset}",
        )
        self.currentPreset = preset
        self.effectState = dict(self.config.presetStates.get(preset, {}))
        self._markSnapshotStale("program change")
        for effect, enabled in self.effectState.items():
            logger.info(
                "katana effect=%s state=%s source=predicted",
                effect,
                "on" if enabled else "off",
            )

    def _setEffectState(self, effect: str, enabled: bool) -> None:
        try:
            controller = self.config.effectControls[effect]
        except KeyError as error:
            raise ValueError(f"effect is not configured for this Katana profile: {effect}") from error
        self._send(
            createControlChange(self.config.midiChannel - 1, controller, 127 if enabled else 0),
            f"message=controlChange channel={self.config.midiChannel} cc={controller} "
            f"state={'on' if enabled else 'off'}",
        )
        self.effectState[effect] = enabled
        self._markGroupStale(effect, "control change")
        logger.info(
            "katana effect=%s state=%s source=predicted",
            effect,
            "on" if enabled else "off",
        )

    def _toggleEffect(self, effect: str) -> None:
        if self.config.stateSync.enabled:
            self._ensureOpenAndSync()
        if effect not in self.effectState:
            raise RuntimeError(f"effect state is unknown: {effect}; runtime toggle rejected")
        self._setEffectState(effect, not self.effectState[effect])

    def _markSnapshotStale(self, reason: str) -> None:
        self.metrics.katanaStateInvalidations += 1
        self.snapshot = AmpStateSnapshot(
            self.connectionEpoch,
            monotonic(),
            {
                name: replace(value, source="stale", error=reason)
                for name, value in self.snapshot.effects.items()
            },
        )

    def _markGroupStale(self, effect: str, reason: str) -> None:
        names = groupParameterNames.get(effect, ())
        if not names:
            return
        self.metrics.katanaStateInvalidations += 1
        effects = dict(self.snapshot.effects)
        for name in names:
            effects[name] = replace(effects[name], source="stale", error=reason)
        self.snapshot = AmpStateSnapshot(self.connectionEpoch, monotonic(), effects)

    def _invalidate(self, reason: str) -> None:
        wasOpen = self.isOpen
        if wasOpen or any(item.source != "unknown" for item in self.snapshot.effects.values()):
            self.metrics.katanaStateInvalidations += 1
        if wasOpen:
            self.connectionEpoch += 1
        self.isOpen = False
        self.session = None
        self.snapshot = unknownSnapshot(self.connectionEpoch, reason)
        self.effectState = {}
        try:
            self.transport.close()
        except Exception:
            logger.exception("Katana duplex MIDI close failed after invalidation")

    def _closeOnWorker(self) -> None:
        self.isOpen = False
        self.session = None
        self.transport.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        future = self.executor.submit(self._closeOnWorker)
        try:
            future.result()
        finally:
            self.executor.shutdown(wait=True, cancel_futures=True)
