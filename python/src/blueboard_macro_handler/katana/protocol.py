from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SysExCommand = Literal["rq1", "dt1"]
SevenBitQuad = tuple[int, int, int, int]

ROLAND_MANUFACTURER_ID = 0x41
KATANA_MKI_MODEL_ID = (0x00, 0x00, 0x00, 0x33)
RQ1_COMMAND = 0x11
DT1_COMMAND = 0x12
SYSEX_START = 0xF0
SYSEX_END = 0xF7


def _requireInteger(name: str, value: int, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")


def _normalizeSevenBitValues(name: str, values: tuple[int, ...]) -> tuple[int, ...]:
    normalized = tuple(values)
    if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0x7F for value in normalized):
        raise ValueError(f"{name} must contain only seven-bit integer values")
    return normalized


def _normalizeQuad(name: str, values: tuple[int, ...]) -> SevenBitQuad:
    normalized = _normalizeSevenBitValues(name, values)
    if len(normalized) != 4:
        raise ValueError(f"{name} must contain exactly four seven-bit values")
    return normalized[0], normalized[1], normalized[2], normalized[3]


def encodeBase128(value: int, width: int = 4) -> tuple[int, ...]:
    """Encode a non-negative scalar as fixed-width base-128 bytes."""
    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise ValueError("base-128 width must be a positive integer")
    maximum = (1 << (7 * width)) - 1
    _requireInteger("base-128 value", value, 0, maximum)
    return tuple((value >> (7 * shift)) & 0x7F for shift in range(width - 1, -1, -1))


def decodeBase128(values: tuple[int, ...]) -> int:
    """Decode one or more seven-bit bytes as a base-128 scalar."""
    normalized = _normalizeSevenBitValues("base-128 values", values)
    if not normalized:
        raise ValueError("base-128 values cannot be empty")
    result = 0
    for value in normalized:
        result = (result << 7) | value
    return result


def incrementAddress(address: tuple[int, ...], amount: int) -> SevenBitQuad:
    """Increment a four-byte Roland address using base-128 carry rules."""
    normalizedAddress = _normalizeQuad("address", address)
    _requireInteger("address increment", amount, 0, 0x0FFFFFFF)
    incremented = decodeBase128(normalizedAddress) + amount
    if incremented > 0x0FFFFFFF:
        raise ValueError("incremented address exceeds four base-128 bytes")
    encoded = encodeBase128(incremented)
    return encoded[0], encoded[1], encoded[2], encoded[3]


def calculateRolandChecksum(values: tuple[int, ...]) -> int:
    """Calculate the Roland checksum for address plus size or data bytes."""
    normalized = _normalizeSevenBitValues("Roland SysEx checksum values", values)
    return (0x80 - (sum(normalized) & 0x7F)) & 0x7F


def verifyRolandChecksum(values: tuple[int, ...], checksum: int) -> bool:
    """Validate a checksum after rejecting non-seven-bit operands."""
    normalized = _normalizeSevenBitValues("Roland SysEx checksum values", values)
    _requireInteger("Roland SysEx checksum", checksum, 0, 0x7F)
    return (sum(normalized) + checksum) & 0x7F == 0


@dataclass(frozen=True)
class KatanaSysExFrame:
    deviceId: int
    command: SysExCommand
    address: SevenBitQuad
    size: SevenBitQuad | None
    data: tuple[int, ...]
    checksum: int

    def __post_init__(self) -> None:
        _requireInteger("SysEx device ID", self.deviceId, 0, 0x7F)
        normalizedAddress = _normalizeQuad("SysEx address", self.address)
        normalizedData = _normalizeSevenBitValues("SysEx data", self.data)
        _requireInteger("SysEx checksum", self.checksum, 0, 0x7F)
        object.__setattr__(self, "address", normalizedAddress)
        object.__setattr__(self, "data", normalizedData)

        if self.command == "rq1":
            if self.size is None:
                raise ValueError("RQ1 frames require a four-byte size")
            normalizedSize = _normalizeQuad("RQ1 size", self.size)
            if decodeBase128(normalizedSize) == 0:
                raise ValueError("RQ1 size must be greater than zero")
            if normalizedData:
                raise ValueError("RQ1 frames cannot contain DT1 data")
            object.__setattr__(self, "size", normalizedSize)
            checksumValues = normalizedAddress + normalizedSize
        elif self.command == "dt1":
            if self.size is not None:
                raise ValueError("DT1 frames cannot contain an RQ1 size")
            if not normalizedData:
                raise ValueError("DT1 frames require at least one data byte")
            checksumValues = normalizedAddress + normalizedData
        else:
            raise ValueError(f"unsupported Katana SysEx command: {self.command!r}")
        if not verifyRolandChecksum(checksumValues, self.checksum):
            raise ValueError("invalid Roland SysEx checksum")


def parseKatanaSysEx(data: tuple[int, ...], *, includesFraming: bool) -> KatanaSysExFrame:
    """Parse and validate a Mk I Katana RQ1 or DT1 message."""
    if not isinstance(includesFraming, bool):
        raise TypeError("includesFraming must be a boolean")
    raw = tuple(data)

    if includesFraming:
        if len(raw) < 2 or raw[0] != SYSEX_START or raw[-1] != SYSEX_END:
            raise ValueError("full-wire SysEx data must start with F0 and end with F7")
        payload = raw[1:-1]
    else:
        if (raw and raw[0] == SYSEX_START) or (raw and raw[-1] == SYSEX_END):
            raise ValueError("Mido SysEx payload must exclude F0 and F7 framing")
        payload = raw

    payload = _normalizeSevenBitValues("SysEx payload", payload)
    if len(payload) < 13:
        raise ValueError("Katana SysEx payload is truncated")
    if payload[0] != ROLAND_MANUFACTURER_ID:
        raise ValueError("unsupported SysEx manufacturer")

    deviceId = payload[1]
    modelId = payload[2:6]
    if modelId != KATANA_MKI_MODEL_ID:
        raise ValueError("unsupported Katana SysEx model ID")

    commandByte = payload[6]
    address = _normalizeQuad("SysEx address", payload[7:11])
    body = payload[11:-1]
    checksum = payload[-1]
    if not verifyRolandChecksum(address + body, checksum):
        raise ValueError("invalid Roland SysEx checksum")

    if commandByte == RQ1_COMMAND:
        if len(body) != 4:
            raise ValueError("RQ1 frames require exactly four size bytes")
        size = _normalizeQuad("RQ1 size", body)
        return KatanaSysExFrame(deviceId, "rq1", address, size, (), checksum)
    if commandByte == DT1_COMMAND:
        if not body:
            raise ValueError("DT1 frames require at least one data byte")
        return KatanaSysExFrame(deviceId, "dt1", address, None, body, checksum)
    raise ValueError(f"unsupported Katana SysEx command byte: 0x{commandByte:02X}")
