from __future__ import annotations

import logging

from ..config import ActionSpec, KatanaConfig
from ..models import RunMetrics
from .commands import MidiCommand, createControlChange, createProgramChange
from .transport import MidiTransport

logger = logging.getLogger("blueboard.katana")


class KatanaController:
    def __init__(self, config: KatanaConfig, transport: MidiTransport, metrics: RunMetrics | None = None) -> None:
        self.config = config
        self.transport = transport
        self.metrics = metrics or RunMetrics()
        self.currentPreset: int | None = None
        self.effectState: dict[str, bool] = {}
        self.isOpen = False
        self.hasOpened = False

    def ensureOpen(self) -> None:
        if self.isOpen:
            return
        self.transport.open(self.config.outputName)
        if self.hasOpened:
            self.metrics.katanaReconnects += 1
        self.hasOpened = True
        self.isOpen = True
        logger.info("katana output=%r state=open", self.config.outputName)

    def send(self, command: MidiCommand, description: str) -> None:
        try:
            self.ensureOpen()
            self.transport.send(command)
        except Exception:
            self.metrics.katanaCommandFailures += 1
            self.isOpen = False
            try:
                self.transport.close()
            except Exception:
                logger.exception("katana output close failed after command error")
            raise
        self.metrics.katanaCommands += 1
        logger.info("katana output=%r %s bytes=%s", self.config.outputName, description, command.data)

    def selectPreset(self, preset: int) -> None:
        command = createProgramChange(self.config.midiChannel - 1, preset)
        self.send(command, f"message=programChange channel={self.config.midiChannel} program={preset}")
        self.currentPreset = preset
        self.effectState = dict(self.config.presetStates.get(preset, {}))

    def setEffectState(self, effect: str, enabled: bool) -> None:
        try:
            controller = self.config.effectControls[effect]
        except KeyError as error:
            raise ValueError(f"effect is not configured for this Katana profile: {effect}") from error
        value = 127 if enabled else 0
        command = createControlChange(self.config.midiChannel - 1, controller, value)
        state = "on" if enabled else "off"
        self.send(command, f"message=controlChange channel={self.config.midiChannel} cc={controller} state={state}")
        self.effectState[effect] = enabled
        logger.info("katana effect=%s state=%s source=predicted", effect, state)

    def toggleEffect(self, effect: str) -> None:
        if effect not in self.effectState:
            raise RuntimeError(
                f"effect state is unknown: {effect}; select a preset with presetStates first or use setEffectState"
            )
        self.setEffectState(effect, not self.effectState[effect])

    def execute(self, action: ActionSpec) -> None:
        if action.command == "selectPreset" and action.preset is not None:
            self.selectPreset(action.preset)
        elif action.command == "setEffectState" and action.enabled is not None:
            self.setEffectState(action.effect, action.enabled)
        elif action.command == "toggleEffect":
            self.toggleEffect(action.effect)
        else:
            raise ValueError(f"unsupported Katana command: {action.command}")

    def close(self) -> None:
        self.transport.close()
        self.isOpen = False
