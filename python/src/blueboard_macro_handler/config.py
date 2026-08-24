from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ActionSpec:
    type: str
    keys: tuple[str, ...] = ()
    message: str = ""
    host: str = "127.0.0.1"
    port: int = 0
    program: str = ""
    args: tuple[str, ...] = ()
    command: str = ""
    preset: int | None = None
    effect: str = ""
    enabled: bool | None = None


supportedEffects = frozenset({"booster", "mod", "fx", "delay", "reverb", "effectLoop"})
supportedKatanaCommands = frozenset({"selectPreset", "setEffectState", "toggleEffect"})
officialEffectControls = {
    "booster": 16,
    "mod": 17,
    "fx": 18,
    "delay": 19,
    "reverb": 20,
    "effectLoop": 21,
}
originalKatana100EffectControls = {
    "booster": 16,
    "delay": 17,
    "reverb": 18,
    "effectLoop": 19,
}
effectControlsByModel = {
    "katana100": originalKatana100EffectControls,
    "katana100MkII": officialEffectControls,
}


@dataclass(frozen=True)
class KatanaConfig:
    outputName: str
    midiChannel: int = 1
    model: str = "katana100MkII"
    firmware: str = "2.00"
    effectControls: dict[str, int] = field(default_factory=lambda: dict(officialEffectControls))
    presetStates: dict[int, dict[str, bool]] = field(default_factory=dict)


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
    scanTimeout: float = 8.0
    pair: bool = False
    katana: KatanaConfig | None = None


legacyActions = {
    "ctrlShiftR": ActionSpec("keyboard", keys=("CTRL", "SHIFT", "R")),
    "altTab": ActionSpec("keyboard", keys=("ALT", "TAB")),
}


def _requireObject(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{context} must be a JSON object")
    return value


def parseAction(value: Any, context: str) -> ActionSpec | None:
    if value is None:
        return None
    if isinstance(value, str):
        return legacyActions.get(value, ActionSpec("log", message=value))
    raw = _requireObject(value, context)
    actionType = raw.get("type")
    if actionType not in {"keyboard", "log", "udp", "launch", "katana"}:
        raise ConfigError(f"{context}.type must be keyboard, log, udp, launch, or katana")
    if actionType == "keyboard":
        keys = raw.get("keys")
        if not isinstance(keys, list) or not keys or not all(isinstance(key, str) for key in keys):
            raise ConfigError(f"{context}.keys must be a non-empty string array")
        return ActionSpec(actionType, keys=tuple(key.upper() for key in keys))
    if actionType == "udp":
        host, port = raw.get("host", "127.0.0.1"), raw.get("port")
        if not isinstance(host, str) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ConfigError(f"{context} requires a host and port from 1 to 65535")
        return ActionSpec(actionType, message=str(raw.get("message", "")), host=host, port=port)
    if actionType == "launch":
        program, args = raw.get("program"), raw.get("args", [])
        if not isinstance(program, str) or not program or not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ConfigError(f"{context} requires program and an optional string args array")
        return ActionSpec(actionType, program=program, args=tuple(args))
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
    if not isinstance(outputName, str) or not outputName.strip():
        raise ConfigError("katana.outputName must be a non-empty string")
    if not isinstance(midiChannel, int) or isinstance(midiChannel, bool) or not 1 <= midiChannel <= 16:
        raise ConfigError("katana.midiChannel must be from 1 to 16")
    if model not in effectControlsByModel:
        accepted = ", ".join(sorted(effectControlsByModel))
        raise ConfigError(f"katana.model must be one of: {accepted}")
    if not isinstance(firmware, str) or not firmware.strip():
        raise ConfigError("katana.firmware must be a non-empty string")

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
    return KatanaConfig(outputName.strip(), midiChannel, model, firmware.strip(), effectControls, presetStates)


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
    name, timeout, pair = device.get("name", "BlueBoard"), device.get("scanTimeout", 8.0), device.get("pair", False)
    if not isinstance(name, str) or not isinstance(timeout, (int, float)) or timeout <= 0 or not isinstance(pair, bool):
        raise ConfigError("device name, scanTimeout, or pair is invalid")
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
        if action.type == "keyboard":
            return {"type": action.type, "keys": list(action.keys)}
        if action.type == "udp":
            return {"type": action.type, "host": action.host, "port": action.port, "message": action.message}
        if action.type == "launch":
            return {"type": action.type, "program": action.program, "args": list(action.args)}
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
    return result


def katanaPedalboardConfig(outputName: str, deviceName: str = "BlueBoard", scanTimeout: float = 8.0) -> AppConfig:
    """Build the safe, documented A-D starter profile for a detected Katana output."""
    katana = KatanaConfig(
        outputName=outputName,
        presetStates={
            0: {"booster": False, "delay": False},
            1: {"booster": False, "delay": False},
        },
    )
    bindings = (
        Binding(20, "press", ActionSpec("katana", command="selectPreset", preset=0), cooldownMs=250),
        Binding(21, "press", ActionSpec("katana", command="selectPreset", preset=1), cooldownMs=250),
        Binding(22, "press", ActionSpec("katana", command="toggleEffect", effect="booster"), cooldownMs=250),
        Binding(23, "press", ActionSpec("katana", command="toggleEffect", effect="delay"), cooldownMs=250),
    )
    return AppConfig(bindings, name=deviceName, scanTimeout=scanTimeout, pair=False, katana=katana)


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
