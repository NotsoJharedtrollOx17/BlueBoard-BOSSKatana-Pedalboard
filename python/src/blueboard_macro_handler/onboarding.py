from __future__ import annotations

import asyncio
import shutil
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .client import DiscoveredDevice, discoverBlueBoards
from .config import (
    AppConfig,
    ConfigError,
    katanaPedalboardConfig,
    katanaProfile,
    katanaProfiles,
    loadConfig,
    pedalboardLayout,
    writeConfig,
)
from .katana import MidoMidiTransport, resolveInputName, resolveOutputName
from .katana.parameters import productionDefinitionsFor
from .router import actionDescription, buttonNames
from .state import loadLastAddress, saveLastAddress

MidiTransportFactory = Callable[[], MidoMidiTransport]
BlueBoardDiscovery = Callable[[str, float], Awaitable[list[DiscoveredDevice]]]


@dataclass(frozen=True)
class DiscoverySnapshot:
    pythonVersion: str
    pythonSupported: bool
    outputNames: tuple[str, ...] = ()
    devices: tuple[DiscoveredDevice, ...] = ()
    midiError: str | None = None
    blueBoardError: str | None = None
    configExists: bool = False
    existingConfig: AppConfig | None = None
    existingConfigError: str | None = None
    inputNames: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadinessCheck:
    status: str
    area: str
    message: str


@dataclass(frozen=True)
class ReadinessReport:
    checks: tuple[ReadinessCheck, ...]

    @property
    def failures(self) -> tuple[ReadinessCheck, ...]:
        return tuple(check for check in self.checks if check.status == "FAIL")

    @property
    def warnings(self) -> tuple[ReadinessCheck, ...]:
        return tuple(check for check in self.checks if check.status == "WARN")

    @property
    def ready(self) -> bool:
        return not self.failures


def _inspectExistingConfig(path: Path | None) -> tuple[bool, AppConfig | None, str | None]:
    if path is None or not path.exists():
        return False, None, None
    try:
        return True, loadConfig(path), None
    except ConfigError as error:
        return True, None, str(error)


async def collectDiscoverySnapshot(
    name: str,
    timeout: float,
    *,
    configPath: Path | None = None,
    previous: DiscoverySnapshot | None = None,
    refreshMidi: bool = True,
    refreshBlueBoard: bool = True,
    midiTransportFactory: MidiTransportFactory = MidoMidiTransport,
    discoverFunction: BlueBoardDiscovery = discoverBlueBoards,
) -> DiscoverySnapshot:
    """Collect independent readiness inputs concurrently without opening MIDI ports."""

    async def listMidiPorts() -> tuple[tuple[str, ...], tuple[str, ...]]:
        def collect() -> tuple[tuple[str, ...], tuple[str, ...]]:
            transport = midiTransportFactory()
            inputNames = tuple(transport.listInputNames()) if hasattr(transport, "listInputNames") else ()
            return inputNames, tuple(transport.listOutputNames())

        return await asyncio.to_thread(collect)

    async def scanBlueBoard() -> tuple[DiscoveredDevice, ...]:
        return tuple(await discoverFunction(name, timeout))

    midiAwaitable = (
        listMidiPorts()
        if previous is None or refreshMidi
        else _constant((previous.inputNames, previous.outputNames))
    )
    blueBoardAwaitable = (
        scanBlueBoard() if previous is None or refreshBlueBoard else _constant(previous.devices)
    )
    configAwaitable = (
        asyncio.to_thread(_inspectExistingConfig, configPath)
        if previous is None
        else _constant((previous.configExists, previous.existingConfig, previous.existingConfigError))
    )
    midiResult, blueBoardResult, configResult = await asyncio.gather(
        midiAwaitable,
        blueBoardAwaitable,
        configAwaitable,
        return_exceptions=True,
    )

    if isinstance(midiResult, BaseException):
        inputNames = ()
        outputNames = ()
        midiError = str(midiResult)
    else:
        inputNames, outputNames = midiResult
        midiError = None if previous is None or refreshMidi else previous.midiError
    if isinstance(blueBoardResult, BaseException):
        devices = ()
        blueBoardError = str(blueBoardResult)
    else:
        devices = blueBoardResult
        blueBoardError = None if previous is None or refreshBlueBoard else previous.blueBoardError
    if isinstance(configResult, BaseException):
        configExists, existingConfig = False, None
        existingConfigError = str(configResult)
    else:
        configExists, existingConfig, existingConfigError = configResult

    version = sys.version_info[:2]
    return DiscoverySnapshot(
        pythonVersion=sys.version.split()[0],
        pythonSupported=(3, 10) <= version < (3, 13),
        outputNames=outputNames,
        devices=devices,
        midiError=midiError,
        blueBoardError=blueBoardError,
        configExists=configExists,
        existingConfig=existingConfig,
        existingConfigError=existingConfigError,
        inputNames=inputNames,
    )


async def _constant(value):
    return value


def selectKatanaOutput(requestedName: str | None, availableNames: tuple[str, ...]) -> str:
    if requestedName:
        return resolveOutputName(requestedName, availableNames)
    katanaNames = tuple(name for name in availableNames if "katana" in name.casefold())
    mainNames = tuple(
        name
        for name in katanaNames
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


def selectKatanaInput(requestedName: str | None, availableNames: tuple[str, ...]) -> str:
    if requestedName:
        return resolveInputName(requestedName, availableNames)
    katanaNames = tuple(name for name in availableNames if "katana" in name.casefold())
    mainNames = tuple(
        name for name in katanaNames if "ctrl" not in name.casefold() and "daw" not in name.casefold()
    )
    if len(mainNames) == 1:
        return mainNames[0]
    if len(katanaNames) == 1:
        return katanaNames[0]
    if not katanaNames:
        raise RuntimeError("No Katana MIDI input found. Connect and power on the amp, then retry.")
    names = ", ".join(repr(name) for name in katanaNames)
    raise RuntimeError(f"Katana MIDI input is ambiguous: {names}. Retry with --input and the main port name.")


def _katanaOutputCandidates(availableNames: tuple[str, ...]) -> tuple[str, ...]:
    katanaNames = tuple(name for name in availableNames if "katana" in name.casefold())
    mainNames = tuple(
        name
        for name in katanaNames
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


def presetLabel(preset: int) -> str:
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


def configurationSummaryLines(config: AppConfig) -> tuple[str, ...]:
    if config.katana is None:
        return ("Katana: not configured",)
    profile = katanaProfile(config.katana.model)
    syncStatus = "enabled" if config.katana.stateSync.enabled else "disabled (legacy prediction mode)"
    lines = (
        f"Model   : {profile.displayName} ({profile.model})",
        *((f"Input   : {config.katana.inputName}",) if config.katana.inputName else ()),
        f"Output  : {config.katana.outputName}",
        f"Channel : {config.katana.midiChannel}",
        f"Firmware: {config.katana.firmware}",
        f"Sync    : {syncStatus}",
    )
    bindings: list[str] = []
    for binding in config.bindings:
        button = buttonNames.get(binding.cc, f"CC{binding.cc}")
        action = binding.action
        if action is not None and action.type == "katana" and action.command == "selectPreset":
            description = f"{presetLabel(action.preset)} (Program Change {action.preset})"
        elif action is not None and action.type == "katana" and action.effect:
            label = profile.effectLabels.get(action.effect, action.effect)
            controller = config.katana.effectControls.get(action.effect)
            description = f"toggle {label} (CC{controller})"
        else:
            description = actionDescription(action)
        bindings.append(f"Button {button}: {description}")
    return (*lines, *bindings)


def _selectOutput(args, availableNames, interactive, inputFunction, outputFunction) -> str:
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


def _interactiveMode(args, interactive: bool | None) -> bool:
    if interactive is None:
        interactive = not args.non_interactive and sys.stdin.isatty() and sys.stdout.isatty()
    if not interactive and not args.non_interactive:
        raise ConfigError(
            "configuration input is not interactive; run from an interactive terminal, "
            "or retry with --non-interactive, --model, and --accept-profile-state-defaults"
        )
    return interactive


def _validateNonInteractiveOptions(args, interactive: bool) -> None:
    if interactive:
        return
    if args.model is None:
        raise ConfigError("--model is required in non-interactive mode because MIDI ports do not identify generation")
    if not args.accept_profile_state_defaults:
        raise ConfigError("--accept-profile-state-defaults is required in non-interactive mode")


def _confirmReplacement(
    args,
    interactive: bool,
    inputFunction,
    outputFunction,
    *,
    existingConfig: AppConfig | None = None,
    existingConfigError: str | None = None,
) -> bool:
    if not args.config.exists():
        return False
    if args.force:
        return True
    if not interactive:
        raise ConfigError(f"{args.config} already exists; use --force to replace it")
    if existingConfig is None and existingConfigError is None:
        try:
            existingConfig = loadConfig(args.config)
        except ConfigError as error:
            existingConfigError = str(error)
    if existingConfig is not None:
        outputFunction("Existing configuration:")
        for line in configurationSummaryLines(existingConfig):
            outputFunction(f"  {line}")
    elif existingConfigError:
        outputFunction(f"Existing configuration cannot be loaded: {existingConfigError}")
    if not _confirm("Replace this configuration?", inputFunction, outputFunction):
        outputFunction("Configuration cancelled; the existing file was not changed.")
        return False
    return True


def _buildDraft(args, snapshot, interactive, inputFunction, outputFunction):
    outputName = _selectOutput(args, snapshot.outputNames, interactive, inputFunction, outputFunction)
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
    inputName = None
    if profile.model == "katana100":
        requestedInput = args.input or (outputName if outputName in snapshot.inputNames else None)
        inputName = selectKatanaInput(requestedInput, snapshot.inputNames)
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

    if snapshot.blueBoardError:
        raise RuntimeError(f"BlueBoard discovery failed: {snapshot.blueBoardError}")
    if not snapshot.devices:
        raise RuntimeError("No BlueBoard found. Hold C while powering it on, then retry.")
    device = _selectBlueBoard(args, snapshot.devices, interactive, inputFunction, outputFunction)
    config = katanaPedalboardConfig(
        outputName,
        args.name,
        args.scan_timeout,
        model=profile.model,
        layout=selectedLayout.name,
        midiChannel=midiChannel,
        firmware=firmware,
        inputName=inputName,
    )
    return config, profile, device


def _printDraft(config, profile, outputFunction) -> None:
    outputFunction("\nProposed configuration:")
    for line in configurationSummaryLines(config):
        outputFunction(f"  {line}")
    boosterLabel = profile.effectLabels["booster"]
    delayLabel = profile.effectLabels["delay"]
    if config.katana is not None and config.katana.stateSync.enabled:
        outputFunction("  Active startup will request the six live Mk I effect flags after the evidence gate passes.")
    outputFunction(
        f"  After preset selection, predicted state assumes {boosterLabel} and {delayLabel} start OFF."
    )
    outputFunction("  Panel, knob, GA-FC, or Tone Studio changes can make predictions stale.")


def _confirmDraft(args, interactive, inputFunction, outputFunction) -> bool:
    if not args.accept_profile_state_defaults:
        if not interactive:
            raise ConfigError("--accept-profile-state-defaults is required in non-interactive mode")
        if not _confirm("Are those starting-state assumptions correct?", inputFunction, outputFunction):
            outputFunction("Configuration cancelled; make the states match or edit presetStates manually.")
            return False
    if interactive and not _confirm("Write this configuration?", inputFunction, outputFunction):
        outputFunction("Configuration cancelled; no files were changed.")
        return False
    return True


def _writeDraft(args, config, device, replacing, outputFunction) -> None:
    backup = _backupConfig(args.config) if replacing else None
    writeConfig(config, args.config, force=replacing)
    saveLastAddress(args.state_file, device.address)
    outputFunction(f"BlueBoard     : {device.name or '<unnamed>'} ({device.address})")
    outputFunction(f"Configuration : {args.config}")
    if backup is not None:
        outputFunction(f"Backup        : {backup}")
    outputFunction("No MIDI commands were sent.")


def _snapshotCollectionError(snapshot: DiscoverySnapshot) -> RuntimeError | None:
    if snapshot.midiError:
        return RuntimeError(f"MIDI port discovery failed: {snapshot.midiError}")
    if not snapshot.outputNames:
        return RuntimeError("No MIDI outputs found. Connect and power on the Katana, then retry.")
    if snapshot.blueBoardError:
        return RuntimeError(f"BlueBoard discovery failed: {snapshot.blueBoardError}")
    if not snapshot.devices:
        return RuntimeError("No BlueBoard found. Hold C while powering it on, then retry.")
    return None


async def configurePedalboard(
    args,
    inputFunction=input,
    outputFunction=print,
    *,
    interactive: bool | None = None,
    midiTransportFactory: MidiTransportFactory = MidoMidiTransport,
    discoverFunction: BlueBoardDiscovery = discoverBlueBoards,
) -> None:
    interactive = _interactiveMode(args, interactive)
    _validateNonInteractiveOptions(args, interactive)
    existedBefore = args.config.exists()
    replacing = _confirmReplacement(args, interactive, inputFunction, outputFunction)
    if existedBefore and not replacing:
        return
    if args.scan_timeout <= 0:
        raise ConfigError("--scan-timeout must be positive")
    outputFunction(f"Discovering Katana MIDI ports and scanning up to {args.scan_timeout:g} seconds for a BlueBoard...")
    snapshot = await collectDiscoverySnapshot(
        args.name,
        args.scan_timeout,
        midiTransportFactory=midiTransportFactory,
        discoverFunction=discoverFunction,
    )
    error = _snapshotCollectionError(snapshot)
    if error:
        raise error
    config, profile, device = _buildDraft(args, snapshot, interactive, inputFunction, outputFunction)
    _printDraft(config, profile, outputFunction)
    if not _confirmDraft(args, interactive, inputFunction, outputFunction):
        return
    _writeDraft(args, config, device, replacing, outputFunction)
    outputFunction(f"Readiness check: blueboard-katana doctor --config {args.config}")
    outputFunction(f"Next dry run  : blueboard-katana run --config {args.config} --debug")
    outputFunction(f"Enable actions: blueboard-katana run --config {args.config} --debug --execute-actions")
    if sys.platform == "win32":
        outputFunction("PowerShell helpers: .\\diagnosePedalboard.ps1, then .\\runPedalboard.ps1 --debug")


def evaluateReadiness(
    config: AppConfig,
    snapshot: DiscoverySnapshot,
    *,
    configLabel: str,
    statePath: Path,
    preferredAddress: str | None = None,
) -> ReadinessReport:
    checks: list[ReadinessCheck] = []
    if snapshot.pythonSupported:
        checks.append(ReadinessCheck("PASS", "Python", snapshot.pythonVersion))
    else:
        checks.append(ReadinessCheck(
            "FAIL",
            "Python",
            f"Python {snapshot.pythonVersion} is unsupported; use Python 3.10, 3.11, or 3.12",
        ))
    checks.append(ReadinessCheck("PASS", "Configuration", configLabel))
    if config.katana is None:
        checks.append(ReadinessCheck("FAIL", "Katana profile", "configuration does not contain a Katana profile"))
        return ReadinessReport(tuple(checks))

    if snapshot.midiError:
        checks.append(ReadinessCheck("FAIL", "MIDI ports", snapshot.midiError))
    else:
        try:
            resolved = resolveOutputName(config.katana.outputName, snapshot.outputNames)
            checks.append(ReadinessCheck("PASS", "MIDI output", resolved))
        except Exception as error:  # noqa: BLE001 - MIDI backends expose platform-specific exception types.
            checks.append(ReadinessCheck("FAIL", "MIDI output", str(error)))

    if config.katana.stateSync.enabled and not snapshot.midiError:
        try:
            if config.katana.inputName is None:
                raise RuntimeError("state synchronization is enabled without an inputName")
            resolvedInput = resolveInputName(config.katana.inputName, snapshot.inputNames)
            checks.append(ReadinessCheck("PASS", "MIDI input", resolvedInput))
        except Exception as error:  # noqa: BLE001 - MIDI backends expose platform-specific exception types.
            checks.append(ReadinessCheck("FAIL", "MIDI input", str(error)))
        productionDefinitions = productionDefinitionsFor(config.katana.model, config.katana.firmware)
        if len(productionDefinitions) != 6:
            checks.append(ReadinessCheck(
                "WARN",
                "State sync",
                f"{len(productionDefinitions)}/6 exact-firmware effect reads are production-approved; "
                "runtime will degrade safely",
            ))
    elif not config.katana.stateSync.enabled:
        checks.append(ReadinessCheck(
            "WARN",
            "State sync",
            "disabled legacy profile; effect toggles use predicted presetStates",
        ))

    if snapshot.blueBoardError:
        checks.append(ReadinessCheck("FAIL", "BlueBoard", f"discovery failed: {snapshot.blueBoardError}"))
    elif not snapshot.devices:
        checks.append(ReadinessCheck(
            "FAIL",
            "BlueBoard",
            "no matching BlueBoard found; hold C while powering it on and retry",
        ))
    else:
        savedAddress = preferredAddress or loadLastAddress(statePath)
        matchingSaved = [device for device in snapshot.devices if device.address == savedAddress]
        if savedAddress and not matchingSaved:
            checks.append(ReadinessCheck(
                "WARN",
                "BlueBoard",
                "saved address was not found; runtime will fall back to name/service matching",
            ))
        selected = matchingSaved[0] if matchingSaved else max(
            snapshot.devices,
            key=lambda candidate: candidate.rssi if candidate.rssi is not None else -1000,
        )
        checks.append(ReadinessCheck(
            "PASS",
            "BlueBoard",
            f"{selected.name or '<unnamed>'} ({selected.address}, RSSI={selected.rssi})",
        ))
    return ReadinessReport(tuple(checks))


def printReadinessReport(report: ReadinessReport, outputFunction=print) -> None:
    for check in report.checks:
        outputFunction(f"{check.status} {check.area}: {check.message}")
    if report.failures:
        outputFunction(f"NOT READY: {len(report.failures)} required check(s) failed; no MIDI commands were sent.")
        return
    suffix = f" with {len(report.warnings)} warning(s)" if report.warnings else ""
    outputFunction(f"READY{suffix}: configuration and connected devices are available; no MIDI commands were sent.")


async def doctorPedalboard(
    args,
    outputFunction=print,
    *,
    midiTransportFactory: MidiTransportFactory = MidoMidiTransport,
    discoverFunction: BlueBoardDiscovery = discoverBlueBoards,
) -> None:
    try:
        config = loadConfig(args.config)
    except ConfigError as error:
        version = sys.version_info[:2]
        status = "PASS" if (3, 10) <= version < (3, 13) else "FAIL"
        report = ReadinessReport((
            ReadinessCheck(status, "Python", sys.version.split()[0]),
            ReadinessCheck("FAIL", "Configuration", str(error)),
        ))
        printReadinessReport(report, outputFunction)
        raise RuntimeError(f"doctor found {len(report.failures)} readiness problem(s)") from error
    if config.katana is None:
        snapshot = DiscoverySnapshot(sys.version.split()[0], (3, 10) <= sys.version_info[:2] < (3, 13))
    else:
        timeout = config.scanTimeout if args.scan_timeout is None else args.scan_timeout
        if timeout <= 0:
            raise ConfigError("scan timeout must be positive")
        outputFunction(f"CHECK Hardware: enumerating MIDI and scanning up to {timeout:g} seconds for a BlueBoard...")
        snapshot = await collectDiscoverySnapshot(
            config.name,
            timeout,
            midiTransportFactory=midiTransportFactory,
            discoverFunction=discoverFunction,
        )
    report = evaluateReadiness(config, snapshot, configLabel=str(args.config), statePath=args.state_file)
    printReadinessReport(report, outputFunction)
    if report.failures:
        raise RuntimeError(f"doctor found {len(report.failures)} readiness problem(s)")


def _retryFlags(snapshot: DiscoverySnapshot, requestedOutput: str | None = None) -> tuple[bool, bool]:
    if requestedOutput and snapshot.outputNames:
        try:
            resolveOutputName(requestedOutput, snapshot.outputNames)
            hasUsableOutput = True
        except (RuntimeError, ValueError):
            hasUsableOutput = False
    else:
        hasUsableOutput = bool(_katanaOutputCandidates(snapshot.outputNames))
    retryMidi = bool(
        snapshot.midiError
        or not snapshot.outputNames
        or not snapshot.inputNames
        or not hasUsableOutput
    )
    retryBlueBoard = bool(snapshot.blueBoardError or not snapshot.devices)
    return retryMidi, retryBlueBoard


async def onboardPedalboard(
    args,
    inputFunction=input,
    outputFunction=print,
    *,
    interactive: bool | None = None,
    midiTransportFactory: MidiTransportFactory = MidoMidiTransport,
    discoverFunction: BlueBoardDiscovery = discoverBlueBoards,
) -> None:
    if args.verify_existing:
        if args.force:
            raise ConfigError("--verify-existing cannot be combined with --force")
        if not args.config.exists():
            raise ConfigError(f"{args.config} does not exist; remove --verify-existing to create it")
        outputFunction("Verifying the existing configuration without prompting or writing...")
        await doctorPedalboard(
            args,
            outputFunction,
            midiTransportFactory=midiTransportFactory,
            discoverFunction=discoverFunction,
        )
        outputFunction("Existing configuration verified; no files were changed.")
        return
    interactive = _interactiveMode(args, interactive)
    _validateNonInteractiveOptions(args, interactive)
    if args.scan_timeout <= 0:
        raise ConfigError("--scan-timeout must be positive")
    outputFunction(
        f"Discovering Katana MIDI ports and scanning up to {args.scan_timeout:g} seconds for a BlueBoard concurrently..."
    )
    snapshot = await collectDiscoverySnapshot(
        args.name,
        args.scan_timeout,
        configPath=args.config,
        midiTransportFactory=midiTransportFactory,
        discoverFunction=discoverFunction,
    )
    while True:
        retryMidi, retryBlueBoard = _retryFlags(snapshot, args.output)
        if not retryMidi and not retryBlueBoard:
            break
        messages = []
        if retryMidi:
            messages.append(snapshot.midiError or "no usable main Katana MIDI input/output pair was found")
        if retryBlueBoard:
            messages.append(snapshot.blueBoardError or "no matching BlueBoard was found")
        outputFunction("Discovery incomplete: " + "; ".join(messages))
        if not interactive or not _confirm("Retry failed hardware discovery?", inputFunction, outputFunction, default=True):
            raise RuntimeError("hardware discovery did not find both the Katana and BlueBoard")
        snapshot = await collectDiscoverySnapshot(
            args.name,
            args.scan_timeout,
            configPath=args.config,
            previous=snapshot,
            refreshMidi=retryMidi,
            refreshBlueBoard=retryBlueBoard,
            midiTransportFactory=midiTransportFactory,
            discoverFunction=discoverFunction,
        )

    existedBefore = snapshot.configExists
    replacing = _confirmReplacement(
        args,
        interactive,
        inputFunction,
        outputFunction,
        existingConfig=snapshot.existingConfig,
        existingConfigError=snapshot.existingConfigError,
    )
    if existedBefore and not replacing:
        return
    config, profile, device = _buildDraft(args, snapshot, interactive, inputFunction, outputFunction)
    _printDraft(config, profile, outputFunction)
    report = evaluateReadiness(
        config,
        snapshot,
        configLabel=f"proposed {args.config}",
        statePath=args.state_file,
        preferredAddress=device.address,
    )
    outputFunction("\nReadiness evaluation (reusing the discovery snapshot):")
    printReadinessReport(report, outputFunction)
    if report.failures:
        raise RuntimeError(f"onboarding found {len(report.failures)} readiness problem(s)")
    if not _confirmDraft(args, interactive, inputFunction, outputFunction):
        return
    _writeDraft(args, config, device, replacing, outputFunction)
    outputFunction("Onboarding complete: READY")
    outputFunction(f"Next dry run  : blueboard-katana run --config {args.config} --debug")
    outputFunction(f"Enable actions: blueboard-katana run --config {args.config} --debug --execute-actions")
    if sys.platform == "win32":
        outputFunction("PowerShell dry run: .\\runPedalboard.ps1 --debug")
        outputFunction("PowerShell active : .\\runPedalboard.ps1 --debug --execute-actions")
