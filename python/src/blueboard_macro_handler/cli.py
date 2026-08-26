from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from . import __version__
from .actions import ActionDispatcher
from .ble_midi import BleMidiDecoder
from .client import BlueBoardClient, discoverBlueBoards
from .config import (
    ConfigError,
    configAsDict,
    katanaPedalboardConfig,
    katanaProfile,
    katanaProfiles,
    loadConfig,
    pedalboardLayout,
    supportedEffects,
    writeConfig,
)
from .katana import KatanaController, MidoMidiTransport, createControlChange, createProgramChange, resolveOutputName
from .led_feedback import LedFeedbackController
from .logging_utils import configureLogging
from .models import RunMetrics
from .router import Router, actionDescription, buttonNames
from .state import defaultStatePath, loadLastAddress, saveLastAddress

logger = logging.getLogger("blueboard.cli")

authorName = "Abraham Jhared Flores Azcona"


def logWelcome(command: str) -> None:
    mode = "offline BLE-MIDI packet replay (blueboard-katana replay)" if command == "replay" else {
        "scan": "BlueBoard discovery scan (blueboard-katana scan)",
        "run": "live BlueBoard/Katana bridge mode (blueboard-katana run)",
        "validate": "configuration validation (blueboard-katana validate)",
        "init-config": "configuration initialization (blueboard-katana init-config)",
        "midi-outputs": "read-only MIDI output discovery (blueboard-katana midi-outputs)",
        "katana-test": "explicit standard-MIDI amplifier test (blueboard-katana katana-test)",
        "probe-effects": "interactive documented-effect switch probe (blueboard-katana probe-effects)",
        "configure": "read-only hardware discovery and local profile setup (blueboard-katana configure)",
        "doctor": "read-only installation and hardware readiness checks (blueboard-katana doctor)",
    }.get(command, command)
    logger.info("================================================================================")
    logger.info("  BlueBoard + BOSS Katana Pedalboard v%s", __version__)
    logger.info("  Windows-first BLE-MIDI to USB-MIDI bridge; Linux path is experimental")
    logger.info("--------------------------------------------------------------------------------")
    logger.info("  Developer : %s", authorName)
    logger.info("  License   : MIT License (Copyright 2026 %s)", authorName)
    logger.info("  Mode      : %s", mode)
    logger.info("  Purpose   : Route BlueBoard buttons to safe, configurable Katana MIDI actions")
    logger.info("--------------------------------------------------------------------------------")
    logger.info("  Independent project; not affiliated with or endorsed by IK Multimedia, BOSS, or Roland")
    logger.info("================================================================================")


def defaultConfigPath() -> Path:
    return Path(str(files("blueboard_macro_handler").joinpath("default_config.json")))


def addLoggingOptions(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--json-logs", action="store_true")
    parser.add_argument("--log-file")


def addRuntimeOptions(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=defaultConfigPath())
    addLoggingOptions(parser)


def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blueboard-katana",
        description="iRig BlueBoard to BOSS Katana MIDI bridge",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="scan for a BlueBoard")
    addRuntimeOptions(scan)
    scan.add_argument("--name")
    scan.add_argument("--scan-timeout", type=float)

    run = commands.add_parser("run", help="connect, decode, and route macros")
    addRuntimeOptions(run)
    run.add_argument("--name")
    run.add_argument("--address")
    run.add_argument("--scan-timeout", type=float)
    run.add_argument("--pair", action=argparse.BooleanOptionalAction, default=None)
    mode = run.add_mutually_exclusive_group()
    mode.add_argument(
        "--execute-actions",
        action="store_true",
        help="enable Katana, keyboard, UDP, and launch actions",
    )
    mode.add_argument("--dry-run", action="store_true", help="route and log without side effects (default)")
    run.add_argument(
        "--led-feedback",
        action="store_true",
        help="mirror A-D button state on the BlueBoard backlights",
    )
    run.add_argument(
        "--reset-leds",
        action="store_true",
        help="send one paced A-D-off sequence, then disconnect (requires --led-feedback)",
    )
    run.add_argument("--state-file", type=Path, default=defaultStatePath())

    replay = commands.add_parser("replay", help="replay recorded BLE-MIDI packet fixtures")
    addRuntimeOptions(replay)
    replay.add_argument("file", type=Path)
    replay.add_argument("--execute-actions", action="store_true")

    validate = commands.add_parser("validate", help="validate and normalize a configuration")
    addRuntimeOptions(validate)

    midiOutputs = commands.add_parser("midi-outputs", help="list available MIDI output ports without sending")
    addLoggingOptions(midiOutputs)

    katanaTest = commands.add_parser("katana-test", help="send one explicit standard MIDI test message")
    addLoggingOptions(katanaTest)
    katanaTest.add_argument("--output", required=True, help="exact or uniquely matching MIDI output name")
    katanaTest.add_argument("--channel", type=int, default=1, help="MIDI channel from 1 to 16")
    testMessage = katanaTest.add_mutually_exclusive_group(required=True)
    testMessage.add_argument("--program", type=int, help="zero-based Program Change value (MkII documents 0-8)")
    testMessage.add_argument("--control", type=int, help="Control Change number")
    katanaTest.add_argument("--value", type=int, help="Control Change value; required with --control")

    probe = commands.add_parser("probe-effects", help="interactively test the documented Katana effect switches")
    addLoggingOptions(probe)
    probeTarget = probe.add_mutually_exclusive_group(required=True)
    probeTarget.add_argument("--output", help="exact or uniquely matching Katana MIDI output name")
    probeTarget.add_argument("--config", type=Path, help="configuration containing the Katana output name")
    probe.add_argument("--model", choices=tuple(katanaProfiles), help="required with --output")
    probe.add_argument("--channel", type=int, help="MIDI channel from 1 to 16; defaults to the profile")
    probe.add_argument("--program", type=int, help="preset selected before probing; defaults to the first binding")
    probe.add_argument(
        "--effects",
        nargs="+",
        choices=tuple(sorted(supportedEffects)),
        help="one or more configured switches to probe (default: all for the profile)",
    )

    configure = commands.add_parser("configure", help="discover hardware and write a ready-to-run local profile")
    addLoggingOptions(configure)
    configure.add_argument("--config", type=Path, default=Path("blueboard-katana.json"))
    configure.add_argument("--output", help="exact or uniquely matching Katana MIDI output override")
    configure.add_argument("--model", choices=tuple(katanaProfiles))
    configure.add_argument("--layout", choices=("panel-first", "channels-1-2"))
    configure.add_argument("--midi-channel", type=int)
    configure.add_argument("--firmware")
    configure.add_argument("--name", default="BlueBoard", help="BlueBoard name substring")
    configure.add_argument("--address", help="exact BlueBoard address when more than one is discoverable")
    configure.add_argument("--scan-timeout", type=float, default=8.0)
    configure.add_argument("--state-file", type=Path, default=defaultStatePath())
    configure.add_argument("--non-interactive", action="store_true")
    configure.add_argument(
        "--accept-profile-state-defaults",
        action="store_true",
        help="accept the generated assumption that mapped effects initially start off",
    )
    configure.add_argument("--force", action="store_true", help="replace an existing generated profile")

    doctor = commands.add_parser("doctor", help="check installation and connected-device readiness without sending")
    addLoggingOptions(doctor)
    doctor.add_argument("--config", type=Path, required=True)
    doctor.add_argument("--scan-timeout", type=float)
    doctor.add_argument("--state-file", type=Path, default=defaultStatePath())

    initialize = commands.add_parser("init-config", help="write an editable default configuration")
    initialize.add_argument("path", type=Path, nargs="?", default=Path("blueboard.json"))
    initialize.add_argument("--force", action="store_true")
    return parser


def listMidiOutputs() -> None:
    names = MidoMidiTransport().listOutputNames()
    if not names:
        print("No MIDI outputs found.")
        return
    for name in names:
        print(name)


def selectKatanaOutput(requestedName: str | None, availableNames: tuple[str, ...]) -> str:
    if requestedName:
        return resolveOutputName(requestedName, availableNames)
    katanaNames = tuple(name for name in availableNames if "katana" in name.casefold())
    mainNames = tuple(
        name for name in katanaNames
        if "ctrl" not in name.casefold() and "daw" not in name.casefold()
    )
    if len(mainNames) == 1:
        return mainNames[0]
    if len(katanaNames) == 1:
        return katanaNames[0]
    if not katanaNames:
        raise RuntimeError("No Katana MIDI output found. Connect and power on the amp, then retry.")
    names = ", ".join(repr(name) for name in katanaNames)
    raise RuntimeError(f"Katana MIDI output is ambiguous: {names}. Retry with --output and the main port name.")


def _katanaOutputCandidates(availableNames: tuple[str, ...]) -> tuple[str, ...]:
    katanaNames = tuple(name for name in availableNames if "katana" in name.casefold())
    mainNames = tuple(
        name for name in katanaNames
        if "ctrl" not in name.casefold() and "daw" not in name.casefold()
    )
    return mainNames or katanaNames


def _promptChoice(prompt: str, choices, inputFunction, outputFunction, defaultIndex: int = 0):
    outputFunction(prompt)
    for index, (_value, label) in enumerate(choices, start=1):
        suffix = " (default)" if index - 1 == defaultIndex else ""
        outputFunction(f"  {index}. {label}{suffix}")
    while True:
        answer = inputFunction(f"Choose 1-{len(choices)} [{defaultIndex + 1}]: ").strip()
        if not answer:
            return choices[defaultIndex][0]
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1][0]
        outputFunction("Enter one of the listed numbers.")


def _promptText(prompt: str, default: str, inputFunction) -> str:
    answer = inputFunction(f"{prompt} [{default}]: ").strip()
    return answer or default


def _confirm(prompt: str, inputFunction, outputFunction, *, default: bool = False) -> bool:
    marker = "Y/n" if default else "y/N"
    while True:
        answer = inputFunction(f"{prompt} [{marker}]: ").strip().casefold()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        outputFunction("Enter y or n.")


def _presetLabel(preset: int) -> str:
    labels = {
        0: "A:CH1",
        1: "A:CH2",
        2: "A:CH3",
        3: "A:CH4",
        4: "Panel",
        5: "B:CH1",
        6: "B:CH2",
        7: "B:CH3",
        8: "B:CH4",
    }
    return labels.get(preset, f"Program {preset}")


def configurationSummaryLines(config) -> tuple[str, ...]:
    if config.katana is None:
        return ("Katana: not configured",)
    profile = katanaProfile(config.katana.model)
    lines = (
        f"Model   : {profile.displayName} ({profile.model})",
        f"Output  : {config.katana.outputName}",
        f"Channel : {config.katana.midiChannel}",
        f"Firmware: {config.katana.firmware}",
    )
    bindings: list[str] = []
    for binding in config.bindings:
        button = buttonNames.get(binding.cc, f"CC{binding.cc}")
        action = binding.action
        if action is not None and action.type == "katana" and action.command == "selectPreset":
            description = f"{_presetLabel(action.preset)} (Program Change {action.preset})"
        elif action is not None and action.type == "katana" and action.effect:
            label = profile.effectLabels.get(action.effect, action.effect)
            controller = config.katana.effectControls.get(action.effect)
            description = f"toggle {label} (CC{controller})"
        else:
            description = actionDescription(action)
        bindings.append(f"Button {button}: {description}")
    return (*lines, *bindings)


def _selectOutputForConfigure(args, availableNames, interactive, inputFunction, outputFunction) -> str:
    try:
        return selectKatanaOutput(args.output, availableNames)
    except RuntimeError:
        candidates = _katanaOutputCandidates(availableNames)
        if args.output or not interactive or len(candidates) < 2:
            raise
        return _promptChoice(
            "More than one Katana MIDI output could be the main port:",
            tuple((name, name) for name in candidates),
            inputFunction,
            outputFunction,
        )


def _selectBlueBoard(args, devices, interactive, inputFunction, outputFunction):
    if args.address:
        matches = [device for device in devices if device.address.casefold() == args.address.casefold()]
        if len(matches) != 1:
            raise RuntimeError(f"BlueBoard address {args.address!r} was not found during discovery")
        return matches[0]
    if len(devices) == 1:
        return devices[0]
    if not interactive:
        raise RuntimeError("Multiple BlueBoards found; retry with --address in non-interactive mode")
    choices = tuple(
        (
            device,
            f"{device.name or '<unnamed>'} ({device.address}, RSSI={device.rssi})",
        )
        for device in devices
    )
    return _promptChoice("More than one BlueBoard was found:", choices, inputFunction, outputFunction)


def _backupConfig(path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    backup = path.with_name(f"{path.stem}.backup-{timestamp}.local.json")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.stem}.backup-{timestamp}-{counter}.local.json")
        counter += 1
    try:
        shutil.copy2(path, backup)
    except OSError as error:
        raise ConfigError(f"cannot back up {path}: {error}") from error
    return backup


async def configurePedalboard(
    args: argparse.Namespace,
    inputFunction=input,
    outputFunction=print,
    *,
    interactive: bool | None = None,
) -> None:
    if interactive is None:
        interactive = not args.non_interactive and sys.stdin.isatty() and sys.stdout.isatty()
    if not interactive and not args.non_interactive:
        raise ConfigError("configuration input is not interactive; retry with --non-interactive and explicit options")
    replacing = args.config.exists()
    if replacing and not args.force:
        if not interactive:
            raise ConfigError(f"{args.config} already exists; use --force to replace it")
        try:
            existing = loadConfig(args.config)
            outputFunction("Existing configuration:")
            for line in configurationSummaryLines(existing):
                outputFunction(f"  {line}")
        except ConfigError as error:
            outputFunction(f"Existing configuration cannot be loaded: {error}")
        if not _confirm("Replace this configuration?", inputFunction, outputFunction):
            outputFunction("Configuration cancelled; the existing file was not changed.")
            return

    availableNames = MidoMidiTransport().listOutputNames()
    outputName = _selectOutputForConfigure(args, availableNames, interactive, inputFunction, outputFunction)

    model = args.model
    if model is None:
        if not interactive:
            raise ConfigError("--model is required in non-interactive mode because MIDI ports do not identify generation")
        model = _promptChoice(
            "Select the amplifier generation:",
            tuple((name, profile.displayName) for name, profile in katanaProfiles.items()),
            inputFunction,
            outputFunction,
        )
    profile = katanaProfile(model)
    layoutName = args.layout
    if layoutName is None and interactive:
        choices = tuple((name, layout.displayName) for name, layout in profile.layouts.items())
        defaultIndex = tuple(profile.layouts).index(profile.defaultLayout)
        layoutName = _promptChoice("Select the starter button layout:", choices, inputFunction, outputFunction, defaultIndex)
    selectedLayout = pedalboardLayout(profile, layoutName)

    midiChannel = args.midi_channel
    if midiChannel is None and interactive:
        rawChannel = _promptText("MIDI receive channel", "1", inputFunction)
        try:
            midiChannel = int(rawChannel)
        except ValueError as error:
            raise ConfigError("MIDI receive channel must be a number from 1 to 16") from error
    midiChannel = 1 if midiChannel is None else midiChannel
    if not 1 <= midiChannel <= 16:
        raise ConfigError("--midi-channel must be from 1 to 16")
    firmware = args.firmware
    if firmware is None and interactive:
        firmware = _promptText("Firmware version for the evidence record", profile.defaultFirmware, inputFunction)
    firmware = firmware or profile.defaultFirmware

    if args.scan_timeout <= 0:
        raise ConfigError("--scan-timeout must be positive")
    outputFunction(f"Katana output : {outputName}")
    outputFunction(f"Scanning up to {args.scan_timeout:g} seconds for a BlueBoard...")
    devices = await discoverBlueBoards(args.name, args.scan_timeout)
    if not devices:
        raise RuntimeError("No BlueBoard found. Hold C while powering it on, then retry.")
    device = _selectBlueBoard(args, devices, interactive, inputFunction, outputFunction)
    config = katanaPedalboardConfig(
        outputName,
        args.name,
        args.scan_timeout,
        model=profile.model,
        layout=selectedLayout.name,
        midiChannel=midiChannel,
        firmware=firmware,
    )

    outputFunction("\nProposed configuration:")
    for line in configurationSummaryLines(config):
        outputFunction(f"  {line}")
    boosterLabel = profile.effectLabels["booster"]
    delayLabel = profile.effectLabels["delay"]
    outputFunction(f"  Predicted state assumes {boosterLabel} and {delayLabel} start OFF for both selected sounds.")
    outputFunction("  Panel, knob, GA-FC, or Tone Studio changes can make that prediction stale.")
    if not args.accept_profile_state_defaults:
        if not interactive:
            raise ConfigError("--accept-profile-state-defaults is required in non-interactive mode")
        if not _confirm("Are those starting-state assumptions correct?", inputFunction, outputFunction):
            outputFunction("Configuration cancelled; make the states match or edit presetStates manually.")
            return
    if interactive and not _confirm("Write this configuration?", inputFunction, outputFunction):
        outputFunction("Configuration cancelled; no files were changed.")
        return

    backup = _backupConfig(args.config) if replacing else None
    writeConfig(config, args.config, force=replacing)
    saveLastAddress(args.state_file, device.address)
    outputFunction(f"BlueBoard     : {device.name or '<unnamed>'} ({device.address})")
    outputFunction(f"Configuration : {args.config}")
    if backup is not None:
        outputFunction(f"Backup        : {backup}")
    outputFunction("No MIDI commands were sent.")
    outputFunction(f"Readiness check: blueboard-katana doctor --config {args.config}")
    outputFunction(f"Next dry run  : blueboard-katana run --config {args.config} --debug")
    outputFunction(f"Enable actions: blueboard-katana run --config {args.config} --debug --execute-actions")
    if sys.platform == "win32":
        outputFunction("PowerShell helpers: .\\diagnosePedalboard.ps1, then .\\runPedalboard.ps1 --debug")


async def doctorPedalboard(args: argparse.Namespace, outputFunction=print) -> None:
    failures: list[str] = []
    warnings: list[str] = []

    version = sys.version_info[:2]
    if (3, 10) <= version < (3, 13):
        outputFunction(f"PASS Python: {sys.version.split()[0]}")
    else:
        message = f"Python {sys.version.split()[0]} is unsupported; use Python 3.10, 3.11, or 3.12"
        outputFunction(f"FAIL Python: {message}")
        failures.append(message)

    try:
        config = loadConfig(args.config)
        outputFunction(f"PASS Configuration: {args.config}")
    except ConfigError as error:
        outputFunction(f"FAIL Configuration: {error}")
        failures.append(str(error))
        config = None

    if config is not None and config.katana is None:
        message = "configuration does not contain a Katana profile"
        outputFunction(f"FAIL Katana profile: {message}")
        failures.append(message)
    elif config is not None:
        try:
            transport = MidoMidiTransport()
            availableNames = transport.listOutputNames()
            resolved = resolveOutputName(config.katana.outputName, availableNames)
            outputFunction(f"PASS MIDI output: {resolved}")
        except Exception as error:  # noqa: BLE001 - MIDI backends expose platform-specific exception types.
            outputFunction(f"FAIL MIDI output: {error}")
            failures.append(str(error))

        timeout = config.scanTimeout if args.scan_timeout is None else args.scan_timeout
        if timeout <= 0:
            message = "scan timeout must be positive"
            outputFunction(f"FAIL BlueBoard: {message}")
            failures.append(message)
            timeout = None
        if timeout is None:
            devices = None
        else:
            outputFunction(f"CHECK BlueBoard: scanning up to {timeout:g} seconds...")
            try:
                devices = await discoverBlueBoards(config.name, timeout)
            except Exception as error:  # noqa: BLE001 - BLE backends expose platform-specific exception types.
                message = f"BlueBoard discovery failed: {error}"
                outputFunction(f"FAIL BlueBoard: {message}")
                failures.append(message)
                devices = None
        if devices is not None:
            if not devices:
                message = "no matching BlueBoard found; hold C while powering it on and retry"
                outputFunction(f"FAIL BlueBoard: {message}")
                failures.append(message)
            else:
                savedAddress = loadLastAddress(args.state_file)
                matchingSaved = [device for device in devices if device.address == savedAddress]
                if savedAddress and not matchingSaved:
                    message = "saved address was not found; runtime will fall back to name/service matching"
                    outputFunction(f"WARN BlueBoard: {message}")
                    warnings.append(message)
                selected = matchingSaved[0] if matchingSaved else max(
                    devices,
                    key=lambda candidate: candidate.rssi if candidate.rssi is not None else -1000,
                )
                outputFunction(
                    f"PASS BlueBoard: {selected.name or '<unnamed>'} ({selected.address}, RSSI={selected.rssi})"
                )

    if failures:
        outputFunction(f"NOT READY: {len(failures)} required check(s) failed; no MIDI commands were sent.")
        raise RuntimeError(f"doctor found {len(failures)} readiness problem(s)")
    suffix = f" with {len(warnings)} warning(s)" if warnings else ""
    outputFunction(f"READY{suffix}: configuration and connected devices are available; no MIDI commands were sent.")


def sendKatanaTest(args: argparse.Namespace) -> RunMetrics:
    if not 1 <= args.channel <= 16:
        raise ValueError("--channel must be from 1 to 16")
    if args.program is not None:
        if args.value is not None:
            raise ValueError("--value is only valid with --control")
        command = createProgramChange(args.channel - 1, args.program)
        description = f"programChange channel={args.channel} program={args.program}"
    else:
        if args.value is None:
            raise ValueError("--value is required with --control")
        command = createControlChange(args.channel - 1, args.control, args.value)
        description = f"controlChange channel={args.channel} cc={args.control} value={args.value}"
    metrics = RunMetrics()
    transport = MidoMidiTransport()
    try:
        transport.open(args.output)
        transport.send(command)
        metrics.katanaCommands += 1
        logger.info("katana output=%r test=%s bytes=%s", transport.outputName, description, command.data)
    except Exception:
        metrics.katanaCommandFailures += 1
        raise
    finally:
        transport.close()
    return metrics


def _probeObservation(prompt: str, inputFunction) -> str:
    while True:
        answer = inputFunction(f"{prompt} [y/n/u]: ").strip().casefold()
        if answer in {"y", "yes"}:
            return "yes"
        if answer in {"n", "no"}:
            return "no"
        if answer in {"u", "unknown", ""}:
            return "unknown"
        print("Enter y for yes, n for no, or u for unknown.")


def probeKatanaEffects(args: argparse.Namespace, inputFunction=input, outputFunction=print) -> RunMetrics:
    outputName = args.output
    config = None
    if args.config is not None:
        if args.model is not None:
            raise ConfigError("--model is only valid with --output; a configuration already declares its model")
        config = loadConfig(args.config)
        if config.katana is None:
            raise ConfigError(f"{args.config} does not contain a Katana configuration")
        outputName = config.katana.outputName
        model = config.katana.model
        controls = config.katana.effectControls
        channel = config.katana.midiChannel if args.channel is None else args.channel
    else:
        if args.model is None:
            raise ConfigError("--model is required with --output because port names do not identify generation")
        profile = katanaProfile(args.model)
        model = profile.model
        controls = profile.effectControls
        channel = 1 if args.channel is None else args.channel

    profile = katanaProfile(model)
    if not 1 <= channel <= 16:
        raise ValueError("--channel must be from 1 to 16")
    program = args.program
    if program is None and config is not None:
        for binding in config.bindings:
            action = binding.action
            if action is not None and action.type == "katana" and action.command == "selectPreset":
                program = action.preset
                break
    program = 0 if program is None else program
    if not 0 <= program <= 8:
        raise ValueError("--program must be from 0 to 8 for the supported Katana profiles")
    effects = tuple(dict.fromkeys(args.effects or tuple(controls)))
    unsupported = tuple(effect for effect in effects if effect not in controls)
    if unsupported:
        accepted = ", ".join(controls)
        raise ConfigError(
            f"effects are not configured for {profile.displayName}: {', '.join(unsupported)}; choose from: {accepted}"
        )
    outputFunction(f"Model: {profile.displayName} ({profile.model})")
    outputFunction("This probe selects the requested preset and tests only switches configured for that model.")
    outputFunction("Do not move the amplifier EFFECTS knobs during the probe.")
    if inputFunction("Type PROBE to continue: ").strip() != "PROBE":
        outputFunction("Probe cancelled; no MIDI commands were sent.")
        return RunMetrics()

    metrics = RunMetrics()
    transport = MidoMidiTransport()
    activeEffect: str | None = None
    results: list[tuple[str, int, str, str]] = []

    def send(command, description: str) -> None:
        try:
            transport.send(command)
        except Exception:
            metrics.katanaCommandFailures += 1
            raise
        metrics.katanaCommands += 1
        logger.info("katana output=%r probe=%s bytes=%s", transport.outputName, description, command.data)

    try:
        transport.open(outputName)
        send(
            createProgramChange(channel - 1, program),
            f"programChange channel={channel} program={program}",
        )
        outputFunction(f"Selected {_presetLabel(program)} (Program Change {program}).")
        outputFunction("Play a short phrase for each observation.")
        for effect in effects:
            controller = controls[effect]
            label = profile.effectLabels.get(effect, effect)
            choice = inputFunction(
                f"Press Enter to test {label} (CC{controller}), s to skip, or q to finish: "
            ).strip().casefold()
            if choice == "q":
                break
            if choice == "s":
                results.append((label, controller, "skipped", "skipped"))
                continue
            activeEffect = effect
            send(
                createControlChange(channel - 1, controller, 127),
                f"controlChange effect={effect} cc={controller} state=on",
            )
            observedOn = _probeObservation(f"Did {label} turn ON?", inputFunction)
            send(
                createControlChange(channel - 1, controller, 0),
                f"controlChange effect={effect} cc={controller} state=off",
            )
            activeEffect = None
            observedOff = _probeObservation(f"Did {label} turn OFF?", inputFunction)
            results.append((label, controller, observedOn, observedOff))
    finally:
        if activeEffect is not None:
            controller = controls[activeEffect]
            try:
                send(
                    createControlChange(channel - 1, controller, 0),
                    f"cleanup effect={activeEffect} cc={controller} state=off",
                )
            except Exception:
                logger.exception("probe cleanup failed for effect=%s", activeEffect)
        transport.close()

    outputFunction("\nProbe results")
    outputFunction("switch       cc   on        off")
    for label, controller, observedOn, observedOff in results:
        outputFunction(f"{label:<12} {controller:<4} {observedOn:<9} {observedOff}")
    return metrics


def loadReplayPackets(path: Path) -> list[bytes]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read replay file: {error}") from error
    rawPackets = value.get("packets") if isinstance(value, dict) else value
    if not isinstance(rawPackets, list) or not all(isinstance(packet, str) for packet in rawPackets):
        raise ValueError("replay JSON must be an array of hex strings or an object with packets")
    try:
        return [bytes.fromhex(packet) for packet in rawPackets]
    except ValueError as error:
        raise ValueError(f"invalid replay packet: {error}") from error


async def asyncCommand(args: argparse.Namespace) -> RunMetrics | None:
    if args.command == "configure":
        await configurePedalboard(args)
        return None
    if args.command == "doctor":
        await doctorPedalboard(args)
        return None
    config = loadConfig(args.config)
    if args.command == "scan":
        devices = await discoverBlueBoards(args.name or config.name, args.scan_timeout or config.scanTimeout)
        if not devices:
            print("No matching BLE device found. Hold C while powering on the BlueBoard, then retry.")
        for device in devices:
            print(f"{device.name or '<unnamed>'}\t{device.address}\tRSSI={device.rssi}")
        return None
    if args.command == "validate":
        print(json.dumps(configAsDict(config), indent=2))
        return None

    if args.command == "run":
        mode = "ENABLED" if args.execute_actions else "DRY RUN"
        logger.info("configuration mode=%s", mode)
        for line in configurationSummaryLines(config):
            logger.info("configuration %s", line)
        if config.katana is not None:
            logger.warning(
                "Katana effect state is predicted; panel, knob, GA-FC, or Tone Studio changes can make it stale"
            )

    metrics = RunMetrics()
    args.metrics = metrics
    katana = None
    if args.execute_actions and config.katana is not None:
        katana = KatanaController(config.katana, MidoMidiTransport(), metrics)
    actions = ActionDispatcher(execute=args.execute_actions, katana=katana)
    ledFeedback = LedFeedbackController(metrics) if getattr(args, "led_feedback", False) else None
    if getattr(args, "reset_leds", False) and ledFeedback is None:
        raise ValueError("--reset-leds requires --led-feedback")
    router = Router(config, actions, metrics, ledFeedback)
    try:
        if args.command == "replay":
            decoder = BleMidiDecoder()
            for packet in loadReplayPackets(args.file):
                metrics.packets += 1
                logger.debug("replay packet=%s", packet.hex(" "))
                for event in decoder.decode(packet): router.handleEvent(event)
            return metrics
        address = args.address or loadLastAddress(args.state_file)
        if address and not args.address: logger.info("using last known address=%s", address)
        client = BlueBoardClient(
            router.handleEvent,
            router.releaseAll,
            nameSubstring=args.name or config.name,
            address=address,
            pair=config.pair if args.pair is None else args.pair,
            scanTimeout=args.scan_timeout or config.scanTimeout,
            metrics=metrics,
            statePath=args.state_file,
            ledFeedback=ledFeedback,
            resetLeds=args.reset_leds,
        )
        await client.run()
        return metrics
    finally:
        router.releaseAll()
        actions.close()


def main(argv: list[str] | None = None) -> int:
    parser = buildParser()
    args = parser.parse_args(argv)
    if args.command == "init-config":
        if args.path.exists() and not args.force:
            parser.error(f"{args.path} already exists; use --force to replace it")
        args.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(defaultConfigPath(), args.path)
        print(f"Wrote {args.path}")
        return 0
    configureLogging(args.debug, args.json_logs, args.log_file)
    logWelcome(args.command)
    try:
        if args.command == "midi-outputs":
            listMidiOutputs()
            metrics = None
        elif args.command == "katana-test":
            metrics = sendKatanaTest(args)
        elif args.command == "probe-effects":
            metrics = probeKatanaEffects(args)
        else:
            metrics = asyncio.run(asyncCommand(args))
    except KeyboardInterrupt:
        logger.info("shutdown requested")
        metrics = getattr(args, "metrics", None)
        if metrics is not None:
            logger.info("summary=%s", json.dumps(metrics.snapshot(), separators=(",", ":")))
        return 130
    except (ConfigError, ValueError, RuntimeError) as error:
        logger.error("%s", error)
        return 2
    if metrics is not None:
        logger.info("summary=%s", json.dumps(metrics.snapshot(), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
