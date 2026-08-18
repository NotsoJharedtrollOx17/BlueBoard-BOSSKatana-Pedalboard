from __future__ import annotations

from collections.abc import Callable
from time import monotonic

from .models import MidiEvent, MidiMessageType


class BleMidiDecoder:
    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self.clock = clock
        self.runningStatus: int | None = None
        self.pendingStatus: int | None = None
        self.pendingData = bytearray()

    def reset(self) -> None:
        self.runningStatus = self.pendingStatus = None
        self.pendingData.clear()

    @staticmethod
    def dataLength(status: int) -> int | None:
        kind = status & 0xF0
        if 0x80 <= kind <= 0xB0 or kind == 0xE0:
            return 2
        if kind in (0xC0, 0xD0):
            return 1
        return None

    def makeEvent(self, status: int, data: bytearray) -> MidiEvent:
        kind, data2 = status & 0xF0, data[1] if len(data) == 2 else 0
        eventType = MidiMessageType.unknown
        if kind == 0xB0: eventType = MidiMessageType.controlChange
        elif kind == 0x90 and data2: eventType = MidiMessageType.noteOn
        elif kind in (0x80, 0x90): eventType = MidiMessageType.noteOff
        elif kind == 0xC0: eventType = MidiMessageType.programChange
        elif kind == 0xE0: eventType = MidiMessageType.pitchBend
        return MidiEvent(eventType, status & 0x0F, data[0], data2, self.clock())

    def decode(self, packet: bytes) -> list[MidiEvent]:
        if not packet or packet[0] & 0x80 == 0:
            return []
        events, index, needTimestamp = [], 1, True
        while index < len(packet):
            if needTimestamp:
                if packet[index] & 0x80 == 0:
                    index += 1
                    continue
                index += 1
                needTimestamp = False
                if index >= len(packet): break
            if self.pendingStatus is None:
                value = packet[index]
                if value & 0x80:
                    index += 1
                    if self.dataLength(value) is None:
                        self.runningStatus, needTimestamp = None, True
                        continue
                    self.pendingStatus = self.runningStatus = value
                elif self.runningStatus is not None:
                    self.pendingStatus = self.runningStatus
                else:
                    index += 1
                    needTimestamp = True
                    continue
            expected = self.dataLength(self.pendingStatus)
            if expected is None:
                self.pendingStatus, needTimestamp = None, True
                self.pendingData.clear()
                continue
            while index < len(packet) and len(self.pendingData) < expected:
                value = packet[index]
                if value & 0x80:
                    index += 1
                    continue
                self.pendingData.append(value)
                index += 1
            if len(self.pendingData) == expected:
                events.append(self.makeEvent(self.pendingStatus, self.pendingData))
                self.pendingStatus, needTimestamp = None, True
                self.pendingData.clear()
        return events


def encodeBleMidi(status: int, data: bytes, timestamp: int | None = None) -> bytes:
    if not 0x80 <= status <= 0xFF or any(value > 0x7F for value in data):
        raise ValueError("invalid MIDI message")
    timestamp = int(monotonic() * 1000) & 0x1FFF if timestamp is None else timestamp & 0x1FFF
    return bytes((0x80 | ((timestamp >> 7) & 0x3F), 0x80 | (timestamp & 0x7F), status, *data))
