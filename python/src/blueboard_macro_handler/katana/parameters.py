from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Evidence = Literal[
    "official",
    "capturedMkII",
    "communityMkII",
    "legacyKatana",
    "inferred",
    "unverifiedPlaceholder",
]


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    address: tuple[int, int, int, int]
    dataLength: int
    minimum: int
    maximum: int
    model: str
    firmware: str
    evidence: Evidence

    def __post_init__(self) -> None:
        if not self.name or len(self.address) != 4:
            raise ValueError("parameter name and four-byte address are required")
        if any(not isinstance(value, int) or not 0 <= value <= 0x7F for value in self.address):
            raise ValueError("parameter addresses must contain four seven-bit values")
        if self.dataLength <= 0 or self.minimum > self.maximum:
            raise ValueError("parameter length or range is invalid")

    @property
    def mayWrite(self) -> bool:
        return self.evidence in {"official", "capturedMkII"}


def calculateRolandChecksum(values: tuple[int, ...]) -> int:
    if any(not isinstance(value, int) or not 0 <= value <= 0x7F for value in values):
        raise ValueError("Roland SysEx checksum values must be seven-bit")
    return (128 - (sum(values) & 0x7F)) & 0x7F


# SysEx addresses intentionally remain empty until they are captured and
# reproduced on the target KATANA-100 MkII firmware.
parameterDefinitions: dict[str, ParameterDefinition] = {}
