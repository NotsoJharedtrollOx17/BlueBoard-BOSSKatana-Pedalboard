from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MidiCommand:
    data: tuple[int, ...]


def _requireRange(name: str, value: int, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be from {minimum} to {maximum}")


def createProgramChange(midiChannel: int, preset: int) -> MidiCommand:
    """Create a standard MIDI Program Change using zero-based wire values."""
    _requireRange("MIDI channel", midiChannel, 0, 15)
    _requireRange("preset", preset, 0, 127)
    return MidiCommand((0xC0 | midiChannel, preset))


def createControlChange(midiChannel: int, controller: int, value: int) -> MidiCommand:
    """Create a standard MIDI Control Change using zero-based channel numbering."""
    _requireRange("MIDI channel", midiChannel, 0, 15)
    _requireRange("controller", controller, 0, 127)
    _requireRange("value", value, 0, 127)
    return MidiCommand((0xB0 | midiChannel, controller, value))
