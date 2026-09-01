from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PedalboardLayout:
    name: str
    displayName: str
    firstPreset: int
    secondPreset: int


@dataclass(frozen=True)
class KatanaModelProfile:
    model: str
    displayName: str
    defaultFirmware: str
    defaultLayout: str
    effectControls: dict[str, int]
    effectLabels: dict[str, str]
    layouts: dict[str, PedalboardLayout]


@dataclass(frozen=True)
class ActionSpec:
    type: str
    message: str = ""
    command: str = ""
    preset: int | None = None
    effect: str = ""
    enabled: bool | None = None


pedalboardLayouts = {
    "panel-first": PedalboardLayout("panel-first", "Panel and A:CH2", 4, 1),
    "channels-1-2": PedalboardLayout("channels-1-2", "A:CH1 and A:CH2", 0, 1),
}
katanaProfiles = {
    "katana100": KatanaModelProfile(
        model="katana100",
        displayName="Original BOSS KATANA-100 (MkI)",
        defaultFirmware="unknown",
        defaultLayout="panel-first",
        effectControls={"booster": 16, "delay": 17, "reverb": 18, "effectLoop": 19},
        effectLabels={
            "booster": "Booster/Mod",
            "delay": "Delay/FX",
            "reverb": "Reverb",
            "effectLoop": "Send/Return",
        },
        layouts=dict(pedalboardLayouts),
    ),
    "katana100MkII": KatanaModelProfile(
        model="katana100MkII",
        displayName="BOSS KATANA-100 MkII",
        defaultFirmware="unknown",
        defaultLayout="channels-1-2",
        effectControls={"booster": 16, "mod": 17, "fx": 18, "delay": 19, "reverb": 20, "effectLoop": 21},
        effectLabels={
            "booster": "Booster",
            "mod": "Mod",
            "fx": "FX",
            "delay": "Delay",
            "reverb": "Reverb",
            "effectLoop": "Effect Loop",
        },
        layouts=dict(pedalboardLayouts),
    ),
}
effectControlsByModel = {model: profile.effectControls for model, profile in katanaProfiles.items()}
originalKatana100EffectControls = katanaProfiles["katana100"].effectControls
officialEffectControls = katanaProfiles["katana100MkII"].effectControls
supportedEffects = frozenset(effect for profile in katanaProfiles.values() for effect in profile.effectControls)
supportedKatanaCommands = frozenset({"selectPreset", "setEffectState", "toggleEffect"})


def katanaProfile(model: str) -> KatanaModelProfile:
    try:
        return katanaProfiles[model]
    except KeyError as error:
        accepted = ", ".join(sorted(katanaProfiles))
        raise ConfigError(f"Katana model must be one of: {accepted}") from error


def pedalboardLayout(profile: KatanaModelProfile, layout: str | None = None) -> PedalboardLayout:
    requested = layout or profile.defaultLayout
    try:
        return profile.layouts[requested]
    except KeyError as error:
        accepted = ", ".join(sorted(profile.layouts))
        raise ConfigError(f"layout for {profile.model} must be one of: {accepted}") from error


@dataclass(frozen=True)
class StateSyncConfig:
    enabled: bool = False
    requestTimeoutMs: int = 750
    requestRetries: int = 1


@dataclass(frozen=True)
class KatanaConfig:
    outputName: str
    midiChannel: int = 1
    model: str = "katana100MkII"
    firmware: str = "2.00"
    effectControls: dict[str, int] = field(default_factory=lambda: dict(officialEffectControls))
    presetStates: dict[int, dict[str, bool]] = field(default_factory=dict)
    inputName: str | None = None
    deviceId: int = 0
    stateSync: StateSyncConfig = field(default_factory=StateSyncConfig)


@dataclass(frozen=True)
class Binding:
    cc: int
    edge: str
    action: ActionSpec | None
    channel: int = 1
    cooldownMs: int = 0


@dataclass(frozen=True)
class AppConfig:
    bindings: tuple[Binding, ...]
    name: str = "BlueBoard"
    scanTimeout: float = 20.0
    pair: bool = False
    katana: KatanaConfig | None = None


removedLegacyActions = frozenset({"ctrlShiftR", "altTab"})
removedActionTypes = frozenset({"keyboard", "udp", "launch"})


def _requireObject(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{context} must be a JSON object")
    return value


def parseAction(value: Any, context: str) -> ActionSpec | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value in removedLegacyActions:
            raise ConfigError(
                f"{context} uses removed macro action {value!r}; "
                "v1.0.0 supports only Katana, log, or null actions"
            )
        return ActionSpec("log", message=value)
    raw = _requireObject(value, context)
    actionType = raw.get("type")
    if actionType in removedActionTypes:
        raise ConfigError(
            f"{context}.type {actionType!r} was removed from the Katana pedalboard; "
                "v1.0.0 supports only Katana, log, or null actions"
        )
    if actionType not in {"log", "katana"}:
        raise ConfigError(f"{context}.type must be log or katana")
    if actionType == "katana":
        command = raw.get("command")
        if command not in supportedKatanaCommands:
            accepted = ", ".join(sorted(supportedKatanaCommands))
            raise ConfigError(f"{context}.command must be one of: {accepted}")
        if command == "selectPreset":
            preset = raw.get("preset")
            if not isinstance(preset, int) or isinstance(preset, bool) or not 0 <= preset <= 127:
                raise ConfigError(f"{context}.preset must be from 0 to 127")
            return ActionSpec(actionType, command=command, preset=preset)
        effect = raw.get("effect")
        if effect not in supportedEffects:
            raise ConfigError(f"{context}.effect must be a supported Katana effect")
        if command == "setEffectState":
            enabled = raw.get("enabled")
            if not isinstance(enabled, bool):
                raise ConfigError(f"{context}.enabled must be true or false")
            return ActionSpec(actionType, command=command, effect=effect, enabled=enabled)
        return ActionSpec(actionType, command=command, effect=effect)
    return ActionSpec(actionType, message=str(raw.get("message", "")))


def parseKatana(value: Any) -> KatanaConfig | None:
    if value is None:
        return None
    raw = _requireObject(value, "katana")
    outputName = raw.get("outputName")
    midiChannel = raw.get("midiChannel", 1)
    model = raw.get("model", "katana100MkII")
    firmware = raw.get("firmware", "2.00")
    inputName = raw.get("inputName")
    deviceId = raw.get("deviceId", 0)
    if not isinstance(outputName, str) or not outputName.strip():
        raise ConfigError("katana.outputName must be a non-empty string")
    if not isinstance(midiChannel, int) or isinstance(midiChannel, bool) or not 1 <= midiChannel <= 16:
        raise ConfigError("katana.midiChannel must be from 1 to 16")
    if model not in effectControlsByModel:
        accepted = ", ".join(sorted(effectControlsByModel))
        raise ConfigError(f"katana.model must be one of: {accepted}")
    if not isinstance(firmware, str) or not firmware.strip():
        raise ConfigError("katana.firmware must be a non-empty string")
    if inputName is not None and (not isinstance(inputName, str) or not inputName.strip()):
        raise ConfigError("katana.inputName must be a non-empty string when provided")
    if not isinstance(deviceId, int) or isinstance(deviceId, bool) or not 0 <= deviceId <= 127:
        raise ConfigError("katana.deviceId must be from 0 to 127")

    rawStateSync = _requireObject(raw.get("stateSync", {}), "katana.stateSync")
    stateSyncEnabled = rawStateSync.get("enabled", False)
    requestTimeoutMs = rawStateSync.get("requestTimeoutMs", 750)
    requestRetries = rawStateSync.get("requestRetries", 1)
    if not isinstance(stateSyncEnabled, bool):
        raise ConfigError("katana.stateSync.enabled must be true or false")
    if (
        not isinstance(requestTimeoutMs, int)
        or isinstance(requestTimeoutMs, bool)
        or requestTimeoutMs <= 0
    ):
        raise ConfigError("katana.stateSync.requestTimeoutMs must be a positive integer")
    if not isinstance(requestRetries, int) or isinstance(requestRetries, bool) or requestRetries < 0:
        raise ConfigError("katana.stateSync.requestRetries must be a non-negative integer")
    if stateSyncEnabled and model != "katana100":
        raise ConfigError("Katana runtime state synchronization supports only model katana100")
    if stateSyncEnabled and inputName is None:
        raise ConfigError("katana.inputName is required when katana.stateSync.enabled is true")
    stateSync = StateSyncConfig(stateSyncEnabled, requestTimeoutMs, requestRetries)

    rawControls = _requireObject(raw.get("effectControls", effectControlsByModel[model]), "katana.effectControls")
    effectControls: dict[str, int] = {}
    for effect, controller in rawControls.items():
        if effect not in supportedEffects:
            raise ConfigError(f"katana.effectControls has unsupported effect: {effect}")
        if not isinstance(controller, int) or isinstance(controller, bool) or not 0 <= controller <= 127:
            raise ConfigError(f"katana.effectControls.{effect} must be from 0 to 127")
        effectControls[effect] = controller
    if len(set(effectControls.values())) != len(effectControls):
        raise ConfigError("katana.effectControls values must be unique")

    rawPresetStates = _requireObject(raw.get("presetStates", {}), "katana.presetStates")
    presetStates: dict[int, dict[str, bool]] = {}
    for rawPreset, valueByEffect in rawPresetStates.items():
        try:
            preset = int(rawPreset)
        except (TypeError, ValueError) as error:
            raise ConfigError(f"katana.presetStates key is not a preset: {rawPreset!r}") from error
        if str(preset) != str(rawPreset) or not 0 <= preset <= 127:
            raise ConfigError(f"katana.presetStates key must be from 0 to 127: {rawPreset!r}")
        rawState = _requireObject(valueByEffect, f"katana.presetStates.{rawPreset}")
        state: dict[str, bool] = {}
        for effect, enabled in rawState.items():
            if effect not in effectControls:
                raise ConfigError(f"katana.presetStates.{rawPreset} uses an unconfigured effect: {effect}")
            if not isinstance(enabled, bool):
                raise ConfigError(f"katana.presetStates.{rawPreset}.{effect} must be true or false")
            state[effect] = enabled
        presetStates[preset] = state
    return KatanaConfig(
        outputName.strip(),
        midiChannel,
        model,
        firmware.strip(),
        effectControls,
        presetStates,
        None if inputName is None else inputName.strip(),
        deviceId,
        stateSync,
    )


def loadConfig(path: Path) -> AppConfig:
    try:
        with path.open(encoding="utf-8") as configFile:
            root = _requireObject(json.load(configFile), "configuration")
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error

    rawBindings = root.get("bindings")
    if not isinstance(rawBindings, list):
        raise ConfigError("bindings must be an array")
    bindings: list[Binding] = []
    for index, value in enumerate(rawBindings):
        raw = _requireObject(value, f"bindings[{index}]")
        cc, edge = raw.get("cc"), raw.get("edge", "press")
        channel, cooldownMs = raw.get("channel", 1), raw.get("cooldownMs", 0)
        if not isinstance(cc, int) or not 0 <= cc <= 127:
            raise ConfigError(f"bindings[{index}].cc must be from 0 to 127")
        if edge not in {"press", "release"}:
            raise ConfigError(f"bindings[{index}].edge must be press or release")
        if not isinstance(channel, int) or not 1 <= channel <= 16:
            raise ConfigError(f"bindings[{index}].channel must be from 1 to 16")
        if not isinstance(cooldownMs, int) or cooldownMs < 0:
            raise ConfigError(f"bindings[{index}].cooldownMs cannot be negative")
        bindings.append(Binding(cc, edge, parseAction(raw.get("action"), f"bindings[{index}].action"), channel, cooldownMs))

    device = _requireObject(root.get("device", {}), "device")
    name, timeout, pair = device.get("name", "BlueBoard"), device.get("scanTimeout", 20.0), device.get("pair", False)
    if not isinstance(name, str) or not isinstance(timeout, (int, float)) or timeout <= 0 or not isinstance(pair, bool):
        raise ConfigError("device name, scanTimeout, or pair is invalid")
    if pair:
        raise ConfigError("device.pair=true is unsupported; v1.0.0 never changes persistent BlueZ pairing state")
    katana = parseKatana(root.get("katana"))
    katanaActions = [binding.action for binding in bindings if binding.action and binding.action.type == "katana"]
    if katanaActions and katana is None:
        raise ConfigError("katana actions require a top-level katana configuration")
    if katana is not None:
        for action in katanaActions:
            if action.effect and action.effect not in katana.effectControls:
                raise ConfigError(f"Katana action uses an unconfigured effect: {action.effect}")
    return AppConfig(tuple(bindings), name=name, scanTimeout=float(timeout), pair=pair, katana=katana)


def configAsDict(config: AppConfig) -> dict[str, Any]:
    def actionAsDict(action: ActionSpec) -> dict[str, Any]:
        if action.type == "katana":
            value: dict[str, Any] = {"type": action.type, "command": action.command}
            if action.preset is not None:
                value["preset"] = action.preset
            if action.effect:
                value["effect"] = action.effect
            if action.enabled is not None:
                value["enabled"] = action.enabled
            return value
        return {"type": action.type, "message": action.message}

    result: dict[str, Any] = {
        "device": {"name": config.name, "scanTimeout": config.scanTimeout, "pair": config.pair},
        "bindings": [
            {
                "cc": binding.cc,
                "channel": binding.channel,
                "edge": binding.edge,
                "cooldownMs": binding.cooldownMs,
                "action": None
                if binding.action is None
                else actionAsDict(binding.action),
            }
            for binding in config.bindings
        ],
    }
    if config.katana is not None:
        result["katana"] = {
            "outputName": config.katana.outputName,
            "midiChannel": config.katana.midiChannel,
            "model": config.katana.model,
            "firmware": config.katana.firmware,
            "effectControls": dict(config.katana.effectControls),
            "presetStates": {str(preset): dict(state) for preset, state in config.katana.presetStates.items()},
        }
        if config.katana.inputName is not None:
            result["katana"]["inputName"] = config.katana.inputName
            result["katana"]["deviceId"] = config.katana.deviceId
            result["katana"]["stateSync"] = {
                "enabled": config.katana.stateSync.enabled,
                "requestTimeoutMs": config.katana.stateSync.requestTimeoutMs,
                "requestRetries": config.katana.stateSync.requestRetries,
            }
    return result


def katanaPedalboardConfig(
    outputName: str,
    deviceName: str = "BlueBoard",
    scanTimeout: float = 20.0,
    *,
    model: str = "katana100",
    layout: str | None = None,
    midiChannel: int = 1,
    firmware: str | None = None,
    inputName: str | None = None,
) -> AppConfig:
    """Build a model-correct A-D starter profile for a detected Katana output."""
    if not isinstance(outputName, str) or not outputName.strip():
        raise ConfigError("Katana output name must be a non-empty string")
    if not isinstance(deviceName, str) or not deviceName.strip():
        raise ConfigError("BlueBoard device name must be a non-empty string")
    if not isinstance(scanTimeout, (int, float)) or scanTimeout <= 0:
        raise ConfigError("scan timeout must be positive")
    if not isinstance(midiChannel, int) or isinstance(midiChannel, bool) or not 1 <= midiChannel <= 16:
        raise ConfigError("MIDI channel must be from 1 to 16")
    profile = katanaProfile(model)
    selectedLayout = pedalboardLayout(profile, layout)
    selectedFirmware = firmware or profile.defaultFirmware
    if not isinstance(selectedFirmware, str) or not selectedFirmware.strip():
        raise ConfigError("firmware must be a non-empty string")
    if inputName is not None and (not isinstance(inputName, str) or not inputName.strip()):
        raise ConfigError("Katana input name must be a non-empty string when provided")
    stateSyncEnabled = profile.model == "katana100"
    selectedInputName = (inputName or outputName).strip() if stateSyncEnabled else None
    katana = KatanaConfig(
        outputName=outputName.strip(),
        midiChannel=midiChannel,
        model=profile.model,
        firmware=selectedFirmware.strip(),
        effectControls=dict(profile.effectControls),
        presetStates={
            selectedLayout.firstPreset: {"booster": False, "delay": False},
            selectedLayout.secondPreset: {"booster": False, "delay": False},
        },
        inputName=selectedInputName,
        deviceId=0,
        stateSync=StateSyncConfig(enabled=stateSyncEnabled),
    )
    bindings = (
        Binding(
            20,
            "press",
            ActionSpec("katana", command="selectPreset", preset=selectedLayout.firstPreset),
            cooldownMs=250,
        ),
        Binding(
            21,
            "press",
            ActionSpec("katana", command="selectPreset", preset=selectedLayout.secondPreset),
            cooldownMs=250,
        ),
        Binding(22, "press", ActionSpec("katana", command="toggleEffect", effect="booster"), cooldownMs=250),
        Binding(23, "press", ActionSpec("katana", command="toggleEffect", effect="delay"), cooldownMs=250),
    )
    return AppConfig(bindings, name=deviceName.strip(), scanTimeout=float(scanTimeout), pair=False, katana=katana)


def writeConfig(config: AppConfig, path: Path, force: bool = False) -> None:
    """Atomically write a normalized configuration without replacing it accidentally."""
    if path.exists() and not force:
        raise ConfigError(f"{path} already exists; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(configAsDict(config), indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise ConfigError(f"cannot write {path}: {error}") from error
