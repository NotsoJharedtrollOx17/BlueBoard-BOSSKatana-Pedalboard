from __future__ import annotations

from dataclasses import dataclass

from .protocol import (
    DT1_COMMAND,
    KATANA_MKI_MODEL_ID,
    ROLAND_MANUFACTURER_ID,
    RQ1_COMMAND,
    SYSEX_END,
    SYSEX_START,
    calculateRolandChecksum,
    decodeBase128,
    encodeBase128,
)


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


def _normalizeAddress(address: tuple[int, ...]) -> tuple[int, int, int, int]:
    normalized = tuple(address)
    if len(normalized) != 4:
        raise ValueError("SysEx address must contain exactly four seven-bit values")
    decodeBase128(normalized)
    return normalized[0], normalized[1], normalized[2], normalized[3]


def createSysExRead(deviceId: int, address: tuple[int, ...], size: int) -> MidiCommand:
    """Create a complete-wire Mk I Katana RQ1 read request."""
    _requireRange("SysEx device ID", deviceId, 0, 0x7F)
    normalizedAddress = _normalizeAddress(address)
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError("SysEx read size must be a positive integer")
    encodedSize = encodeBase128(size)
    checksum = calculateRolandChecksum(normalizedAddress + encodedSize)
    return MidiCommand(
        (
            SYSEX_START,
            ROLAND_MANUFACTURER_ID,
            deviceId,
            *KATANA_MKI_MODEL_ID,
            RQ1_COMMAND,
            *normalizedAddress,
            *encodedSize,
            checksum,
            SYSEX_END,
        )
    )


def createSysExData(deviceId: int, address: tuple[int, ...], data: tuple[int, ...]) -> MidiCommand:
    """Create a low-level complete-wire Mk I Katana DT1 data message."""
    _requireRange("SysEx device ID", deviceId, 0, 0x7F)
    normalizedAddress = _normalizeAddress(address)
    normalizedData = tuple(data)
    if not normalizedData:
        raise ValueError("SysEx data must contain at least one seven-bit value")
    checksum = calculateRolandChecksum(normalizedAddress + normalizedData)
    return MidiCommand(
        (
            SYSEX_START,
            ROLAND_MANUFACTURER_ID,
            deviceId,
            *KATANA_MKI_MODEL_ID,
            DT1_COMMAND,
            *normalizedAddress,
            *normalizedData,
            checksum,
            SYSEX_END,
        )
    )
