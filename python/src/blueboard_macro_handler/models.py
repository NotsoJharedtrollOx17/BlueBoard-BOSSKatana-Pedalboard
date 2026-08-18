from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic


class MidiMessageType(Enum):
    controlChange = "controlChange"
    noteOn = "noteOn"
    noteOff = "noteOff"
    programChange = "programChange"
    pitchBend = "pitchBend"
    unknown = "unknown"


@dataclass(frozen=True)
class MidiEvent:
    messageType: MidiMessageType
    channel: int
    data1: int
    data2: int
    receivedAt: float = field(default_factory=monotonic)


class ConnectionState(Enum):
    scanning = "scanning"
    connecting = "connecting"
    discovering = "discovering"
    subscribing = "subscribing"
    connected = "connected"
    backoff = "backoff"
    stopped = "stopped"


@dataclass
class RunMetrics:
    startedAt: float = field(default_factory=monotonic)
    connectedAt: float | None = None
    connectedSeconds: float = 0.0
    packets: int = 0
    events: int = 0
    actions: int = 0
    actionFailures: int = 0
    ledFeedbackWrites: int = 0
    ledFeedbackFailures: int = 0
    ledFeedbackDrops: int = 0
    reconnects: int = 0
    katanaCommands: int = 0
    katanaCommandFailures: int = 0
    katanaReconnects: int = 0

    def beginConnection(self) -> None:
        if self.connectedAt is None:
            self.connectedAt = monotonic()

    def endConnection(self) -> None:
        if self.connectedAt is not None:
            self.connectedSeconds += monotonic() - self.connectedAt
            self.connectedAt = None

    def snapshot(self) -> dict[str, int | float]:
        connectedSeconds = self.connectedSeconds
        if self.connectedAt is not None:
            connectedSeconds += monotonic() - self.connectedAt
        return {
            "runtimeSeconds": round(monotonic() - self.startedAt, 3),
            "connectedSeconds": round(connectedSeconds, 3),
            "packets": self.packets,
            "events": self.events,
            "actions": self.actions,
            "actionFailures": self.actionFailures,
            "ledFeedbackWrites": self.ledFeedbackWrites,
            "ledFeedbackFailures": self.ledFeedbackFailures,
            "ledFeedbackDrops": self.ledFeedbackDrops,
            "reconnects": self.reconnects,
            "katanaCommands": self.katanaCommands,
            "katanaCommandFailures": self.katanaCommandFailures,
            "katanaReconnects": self.katanaReconnects,
        }
