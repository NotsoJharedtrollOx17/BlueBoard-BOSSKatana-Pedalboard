from __future__ import annotations

import logging
from time import monotonic
from typing import Protocol

from .actions import ActionDispatcher
from .config import AppConfig, Binding
from .models import MidiEvent, MidiMessageType, RunMetrics

logger = logging.getLogger("blueboard.router")

buttonNames = {20: "A", 21: "B", 22: "C", 23: "D"}


class LedFeedback(Protocol):
    def setLed(self, cc: int, isOn: bool, *, force: bool = False) -> bool: ...


def actionDescription(action) -> str:
    if action is None:
        return "unmapped"
    if action.type == "log":
        return f"log:{action.message}" if action.message else "log"
    if action.type == "katana":
        target = action.effect if action.effect else action.preset
        return f"katana:{action.command}:{target}"
    return action.type


class Router:
    def __init__(
        self,
        config: AppConfig,
        actions: ActionDispatcher,
        metrics: RunMetrics | None = None,
        ledFeedback: LedFeedback | None = None,
    ) -> None:
        self.config, self.actions = config, actions
        self.metrics = metrics or RunMetrics()
        self.ledFeedback = ledFeedback
        self.buttonState: dict[tuple[int, int], bool] = {}
        self.lastActionAt: dict[Binding, float] = {}

    def handleEvent(self, event: MidiEvent) -> None:
        self.metrics.events += 1
        button = buttonNames.get(event.data1)
        if event.messageType is not MidiMessageType.controlChange:
            logger.debug(
                "bleMidi event type=%s channel=%d data1=%d data2=%d",
                event.messageType.value,
                event.channel + 1,
                event.data1,
                event.data2,
            )
            return
        key, pressed = (event.channel, event.data1), event.data2 >= 64
        previous = self.buttonState.get(key, False)
        self.buttonState[key] = pressed
        if previous == pressed:
            return
        edge, now = ("press" if pressed else "release"), monotonic()
        if self.ledFeedback is not None and event.channel == 0 and button is not None:
            self.ledFeedback.setLed(event.data1, pressed)
        matchingBindings = [
            binding
            for binding in self.config.bindings
            if binding.cc == event.data1 and binding.channel - 1 == event.channel and binding.edge == edge
        ]
        if matchingBindings:
            actionText = ", ".join(actionDescription(binding.action) for binding in matchingBindings)
        else:
            actionText = "unmapped"
        logger.info(
            "button=%s edge=%s source=ble-midi channel=%d cc=%d value=%d action=%s",
            button or "?",
            edge,
            event.channel + 1,
            event.data1,
            event.data2,
            actionText,
        )
        for binding in self.config.bindings:
            if binding.cc != event.data1 or binding.channel - 1 != event.channel or binding.edge != edge:
                continue
            if binding.action is None:
                continue
            lastAt = self.lastActionAt.get(binding, float("-inf"))
            if (now - lastAt) * 1000 < binding.cooldownMs:
                logger.warning("button=%s action=%s suppressed=cooldown", button or "?", actionDescription(binding.action))
                continue
            self.lastActionAt[binding] = now
            try:
                if self.actions.invoke(binding.action):
                    self.metrics.actions += 1
            except Exception:
                self.metrics.actionFailures += 1
                logger.exception("button=%s action=%s result=failed", button or "?", actionDescription(binding.action))

    def releaseAll(self) -> None:
        active = [key for key, pressed in self.buttonState.items() if pressed]
        self.buttonState.clear()
        if active:
            logger.warning("cleared active buttons after disconnect: %s", active)
