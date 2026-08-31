from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .protocol import calculateRolandChecksum, decodeBase128

Evidence = Literal[
    "official",
    "capturedMkI",
    "communityMkI",
    "legacyKatana",
    "inferred",
    "unverifiedPlaceholder",
]
ReadAccess = Literal["none", "probe", "production"]
WriteAccess = Literal["none", "validated"]
Decoder = Literal["strictBoolean"]

__all__ = [
    "Decoder",
    "Evidence",
    "ParameterDefinition",
    "ReadAccess",
    "WriteAccess",
    "calculateRolandChecksum",
    "parameterDefinitions",
    "productionDefinitionsFor",
]

_EVIDENCE_VALUES = {
    "official",
    "capturedMkI",
    "communityMkI",
    "legacyKatana",
    "inferred",
    "unverifiedPlaceholder",
}
_READ_ACCESS_VALUES = {"none", "probe", "production"}
_WRITE_ACCESS_VALUES = {"none", "validated"}


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    address: tuple[int, int, int, int]
    dataLength: int
    model: str
    firmwareRange: str
    evidence: Evidence
    readAccess: ReadAccess
    writeAccess: WriteAccess
    decoder: Decoder
    safetyNotes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("parameter name is required")
        normalizedAddress = tuple(self.address)
        if len(normalizedAddress) != 4:
            raise ValueError("parameter address must contain exactly four seven-bit values")
        decodeBase128(normalizedAddress)
        if not isinstance(self.dataLength, int) or isinstance(self.dataLength, bool) or self.dataLength <= 0:
            raise ValueError("parameter data length must be a positive integer")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("parameter model is required")
        if not isinstance(self.firmwareRange, str) or not self.firmwareRange.strip():
            raise ValueError("parameter firmware range is required")
        if self.evidence not in _EVIDENCE_VALUES:
            raise ValueError(f"unsupported parameter evidence: {self.evidence!r}")
        if self.readAccess not in _READ_ACCESS_VALUES:
            raise ValueError(f"unsupported parameter read access: {self.readAccess!r}")
        if self.writeAccess not in _WRITE_ACCESS_VALUES:
            raise ValueError(f"unsupported parameter write access: {self.writeAccess!r}")
        if self.decoder != "strictBoolean":
            raise ValueError(f"unsupported parameter decoder: {self.decoder!r}")
        if not isinstance(self.safetyNotes, str):
            raise TypeError("parameter safety notes must be text")
        if self.readAccess == "production" and self.evidence not in {"official", "capturedMkI"}:
            raise ValueError("production reads require official or captured Mk I evidence")
        if self.writeAccess == "validated" and self.evidence not in {"official", "capturedMkI"}:
            raise ValueError("validated writes require official or captured Mk I evidence")
        object.__setattr__(
            self,
            "address",
            (normalizedAddress[0], normalizedAddress[1], normalizedAddress[2], normalizedAddress[3]),
        )

    @property
    def mayProbe(self) -> bool:
        return self.readAccess in {"probe", "production"}

    @property
    def mayReadInProduction(self) -> bool:
        return self.readAccess == "production"

    @property
    def mayWrite(self) -> bool:
        return self.writeAccess == "validated"

    def decodeValue(self, data: tuple[int, ...]) -> bool:
        normalized = tuple(data)
        if len(normalized) != self.dataLength:
            raise ValueError(f"{self.name} requires exactly {self.dataLength} data byte(s)")
        decodeBase128(normalized)
        if self.decoder == "strictBoolean":
            if normalized == (0x00,):
                return False
            if normalized == (0x01,):
                return True
            raise ValueError(f"{self.name} received an unknown strict-boolean value: {normalized!r}")
        raise ValueError(f"unsupported parameter decoder: {self.decoder!r}")


_PROBE_ONLY_NOTE = (
    "Community Mk I read candidate; requires target-firmware capture and reproduction before production use."
)

parameterDefinitions: dict[str, ParameterDefinition] = {
    "effects.boost.enabled": ParameterDefinition(
        "effects.boost.enabled",
        (0x60, 0x00, 0x00, 0x30),
        1,
        "katana100",
        "unknown",
        "communityMkI",
        "probe",
        "none",
        "strictBoolean",
        _PROBE_ONLY_NOTE,
    ),
    "effects.mod.enabled": ParameterDefinition(
        "effects.mod.enabled",
        (0x60, 0x00, 0x01, 0x40),
        1,
        "katana100",
        "unknown",
        "communityMkI",
        "probe",
        "none",
        "strictBoolean",
        _PROBE_ONLY_NOTE,
    ),
    "effects.fx.enabled": ParameterDefinition(
        "effects.fx.enabled",
        (0x60, 0x00, 0x03, 0x4C),
        1,
        "katana100",
        "unknown",
        "communityMkI",
        "probe",
        "none",
        "strictBoolean",
        _PROBE_ONLY_NOTE,
    ),
    "effects.delay.enabled": ParameterDefinition(
        "effects.delay.enabled",
        (0x60, 0x00, 0x05, 0x60),
        1,
        "katana100",
        "unknown",
        "communityMkI",
        "probe",
        "none",
        "strictBoolean",
        _PROBE_ONLY_NOTE,
    ),
    "effects.reverb.enabled": ParameterDefinition(
        "effects.reverb.enabled",
        (0x60, 0x00, 0x06, 0x10),
        1,
        "katana100",
        "unknown",
        "communityMkI",
        "probe",
        "none",
        "strictBoolean",
        _PROBE_ONLY_NOTE,
    ),
    "effects.effectLoop.enabled": ParameterDefinition(
        "effects.effectLoop.enabled",
        (0x60, 0x00, 0x06, 0x55),
        1,
        "katana100",
        "unknown",
        "legacyKatana",
        "probe",
        "none",
        "strictBoolean",
        "Single-source Mk I read candidate; requires independent target-firmware reproduction before production use.",
    ),
}


def productionDefinitionsFor(model: str, firmware: str) -> tuple[ParameterDefinition, ...]:
    return tuple(
        definition
        for definition in parameterDefinitions.values()
        if definition.model == model
        and definition.firmwareRange == firmware
        and definition.mayReadInProduction
    )
