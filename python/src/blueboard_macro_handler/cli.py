from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
from importlib.resources import files
from pathlib import Path

from . import __version__
from . import onboarding as onboardingWorkflows
from .actions import ActionDispatcher
from .ble_midi import BleMidiDecoder
from .client import BlueBoardClient, discoverBlueBoards
from .config import (
    ConfigError,
    configAsDict,
    katanaProfile,
    katanaProfiles,
    loadConfig,
    supportedEffects,
)
from .katana import (
    KatanaController,
    KatanaSysExProbe,
    MidoMidiTransport,
    SysExProbeReport,
    createControlChange,
    createProgramChange,
    formatMidiBytes,
)
from .led_feedback import LedFeedbackController
from .logging_utils import configureLogging
from .models import RunMetrics
from .onboarding import configurationSummaryLines, presetLabel
from .router import Router
from .state import defaultStatePath, loadLastAddress

logger = logging.getLogger("blueboard.cli")

authorName = "Abraham Jhared Flores Azcona"


def logWelcome(command: str) -> None:
    mode = "offline BLE-MIDI packet replay (blueboard-katana replay)" if command == "replay" else {
        "scan": "BlueBoard discovery scan (blueboard-katana scan)",
        "run": "live BlueBoard/Katana bridge mode (blueboard-katana run)",
        "validate": "configuration validation (blueboard-katana validate)",
        "init-config": "configuration initialization (blueboard-katana init-config)",
        "midi-outputs": "read-only MIDI output discovery (blueboard-katana midi-outputs)",
        "midi-inputs": "read-only MIDI input discovery (blueboard-katana midi-inputs)",
        "sysex-probe": "bounded read-only Katana SysEx diagnostic (blueboard-katana sysex-probe)",
        "katana-test": "explicit standard-MIDI amplifier test (blueboard-katana katana-test)",
        "probe-effects": "interactive documented-effect switch probe (blueboard-katana probe-effects)",
        "configure": "read-only hardware discovery and local profile setup (blueboard-katana configure)",
        "doctor": "read-only installation and hardware readiness checks (blueboard-katana doctor)",
        "onboard": "unified read-only Windows hardware onboarding (blueboard-katana onboard)",
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


def addConfigurationOptions(parser: argparse.ArgumentParser) -> None:
    addLoggingOptions(parser)
    parser.add_argument("--config", type=Path, default=Path("blueboard-katana.json"))
    parser.add_argument("--input", help="exact or uniquely matching Katana MIDI input override")
    parser.add_argument("--output", help="exact or uniquely matching Katana MIDI output override")
    parser.add_argument("--model", choices=tuple(katanaProfiles))
    parser.add_argument("--layout", choices=("panel-first", "channels-1-2"))
    parser.add_argument("--midi-channel", type=int)
    parser.add_argument("--firmware")
    parser.add_argument("--name", default="BlueBoard", help="BlueBoard name substring")
    parser.add_argument("--address", help="exact BlueBoard address when more than one is discoverable")
    parser.add_argument("--scan-timeout", type=float, default=20.0)
    parser.add_argument("--state-file", type=Path, default=defaultStatePath())
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument(
        "--accept-profile-state-defaults",
        action="store_true",
        help="accept the generated assumption that mapped effects initially start off",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing generated profile")


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
    run.add_argument(
        "--duration-seconds",
        type=float,
        help="stop a run session cleanly after this positive duration; actions remain opt-in",
    )
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

    midiInputs = commands.add_parser("midi-inputs", help="list available MIDI input ports without opening")
    addLoggingOptions(midiInputs)

    sysexProbe = commands.add_parser("sysex-probe", help="run a bounded predefined read-only Katana SysEx probe")
    addLoggingOptions(sysexProbe)
    sysexProbe.add_argument("--model", choices=("katana100",), required=True)
    sysexProbe.add_argument("--input", required=True, help="exact or uniquely matching Katana MIDI input name")
    sysexProbe.add_argument("--output", required=True, help="exact or uniquely matching Katana MIDI output name")
    sysexProbe.add_argument(
        "--read",
        choices=("current-selection", "effect-states", "panel-snapshot"),
        required=True,
        help="predefined read-only diagnostic target",
    )
    sysexProbe.add_argument("--device-id", type=int, default=0, help="Roland SysEx device ID from 0 to 127")
    sysexProbe.add_argument("--timeout-ms", type=int, default=750, help="positive timeout for each request attempt")
    sysexProbe.add_argument("--retries", type=int, default=1, help="bounded retry count after a timeout")
    sysexProbe.add_argument(
        "--editor-settle-ms",
        type=int,
        default=75,
        help="delay after the temporary editor handshake for current-selection",
    )
    sysexProbe.add_argument("--save-fixture", type=Path, help="save sanitized traffic JSON after a second confirmation")

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
    addConfigurationOptions(configure)

    onboard = commands.add_parser("onboard", help="discover, configure, and verify hardware in one safe workflow")
    addConfigurationOptions(onboard)
    onboard.add_argument(
        "--verify-existing",
        action="store_true",
        help="freshly check the saved configuration without prompting or writing",
    )

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


def listMidiInputs() -> None:
    names = MidoMidiTransport().listInputNames()
    if not names:
        print("No MIDI inputs found.")
        return
    for name in names:
        print(name)


def _printSysExReport(report: SysExProbeReport, outputFunction=print) -> None:
    outputFunction(
        f"Resolved ports: input={report.inputName!r} output={report.outputName!r} "
        f"connectionEpoch={report.connectionEpoch}"
    )
    outputFunction("\nSysEx traffic (complete wire bytes)")
    for record in report.traffic:
        status = ""
        if record.valid is not None:
            status = " valid" if record.valid else f" invalid={record.error}"
        outputFunction(
            f"{record.direction.upper():<8} {record.elapsedMs:>9.3f} ms "
            f"{record.purpose}{status} bytes={formatMidiBytes(record.data)}"
        )
        if record.frame is not None:
            outputFunction(
                f"         command={record.frame.command} deviceId={record.frame.deviceId} "
                f"address={formatMidiBytes(record.frame.address)} data={formatMidiBytes(record.frame.data)} "
                f"checksum={record.frame.checksum:02X}"
            )
    outputFunction("\nValidated observations")
    for observation in report.observations:
        raw = "<no reply>" if observation.rawData is None else formatMidiBytes(observation.rawData)
        latency = "n/a" if observation.latencyMs is None else f"{observation.latencyMs:.3f} ms"
        outcome = f"ERROR: {observation.error}" if observation.error else repr(observation.decoded)
        outputFunction(
            f"{observation.name}: address={formatMidiBytes(observation.address)} data={raw} "
            f"decoded={outcome} attempts={observation.attempts} latency={latency}"
        )


def runSysExProbe(args: argparse.Namespace, inputFunction=input, outputFunction=print) -> SysExProbeReport | None:
    if args.model != "katana100":
        raise ConfigError("SysEx probes support only the original KATANA-100 model (katana100)")
    outputFunction("READ-ONLY SYSEX HARDWARE PROBE")
    outputFunction("Close BOSS Tone Studio and any other MIDI application before continuing.")
    outputFunction("Set the amplifier output volume to a safe level and back up important Tone Settings.")
    outputFunction("Only predefined RQ1 reads are sent; current-selection also uses a temporary editor-mode handshake.")
    if inputFunction("Type READ to open the selected MIDI ports and continue: ").strip() != "READ":
        outputFunction("SysEx probe cancelled; no MIDI ports were opened and no messages were sent.")
        return None

    metrics = RunMetrics()
    probe = KatanaSysExProbe(
        MidoMidiTransport(),
        deviceId=args.device_id,
        timeoutMs=args.timeout_ms,
        retries=args.retries,
        editorSettleMs=args.editor_settle_ms,
        metrics=metrics,
    )
    report = None
    primaryError: BaseException | None = None
    try:
        probe.open(args.input, args.output, target=args.read, model=args.model)
        report = probe.probe()
    except BaseException as error:
        primaryError = error
        if probe.report is not None:
            _printSysExReport(probe.report, outputFunction)
        raise
    finally:
        try:
            probe.close()
        except Exception:
            if primaryError is None:
                raise
            logger.exception("Katana SysEx probe port cleanup failed after an earlier error")
    _printSysExReport(report, outputFunction)

    if args.save_fixture is not None:
        if args.save_fixture.exists():
            raise ConfigError(f"{args.save_fixture} already exists; choose a new fixture path")
        if inputFunction(f"Type SAVE to write sanitized capture {args.save_fixture}: ").strip() == "SAVE":
            args.save_fixture.parent.mkdir(parents=True, exist_ok=True)
            args.save_fixture.write_text(json.dumps(report.asFixture(), indent=2) + "\n", encoding="utf-8")
            outputFunction(f"Saved sanitized SysEx fixture: {args.save_fixture}")
        else:
            outputFunction("Fixture save cancelled; probe results remain only in the console/log.")
    return report


def selectKatanaOutput(requestedName: str | None, availableNames: tuple[str, ...]) -> str:
    return onboardingWorkflows.selectKatanaOutput(requestedName, availableNames)


async def configurePedalboard(
    args: argparse.Namespace,
    inputFunction=input,
    outputFunction=print,
    *,
    interactive: bool | None = None,
) -> None:
    await onboardingWorkflows.configurePedalboard(
        args,
        inputFunction,
        outputFunction,
        interactive=interactive,
        midiTransportFactory=MidoMidiTransport,
        discoverFunction=discoverBlueBoards,
    )


async def doctorPedalboard(args: argparse.Namespace, outputFunction=print) -> None:
    await onboardingWorkflows.doctorPedalboard(
        args,
        outputFunction,
        midiTransportFactory=MidoMidiTransport,
        discoverFunction=discoverBlueBoards,
    )


async def onboardPedalboard(
    args: argparse.Namespace,
    inputFunction=input,
    outputFunction=print,
    *,
    interactive: bool | None = None,
) -> None:
    await onboardingWorkflows.onboardPedalboard(
        args,
        inputFunction,
        outputFunction,
        interactive=interactive,
        midiTransportFactory=MidoMidiTransport,
        discoverFunction=discoverBlueBoards,
    )


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
        outputFunction(f"Selected {presetLabel(program)} (Program Change {program}).")
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
    if args.command == "onboard":
        await onboardPedalboard(args)
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
            if config.katana.stateSync.enabled and args.execute_actions:
                logger.info("Katana state synchronization requested for active runtime startup and recovery")
            else:
                logger.warning(
                    "Katana effect state is predicted; panel, knob, GA-FC, or Tone Studio changes can make it stale"
                )
                if config.katana.model == "katana100" and not config.katana.stateSync.enabled:
                    logger.warning(
                        "Legacy Mk I profile: add inputName and stateSync settings or rerun onboarding to enable v0.7.0 state bootstrap"
                    )

    metrics = RunMetrics()
    args.metrics = metrics
    katana = None
    if args.execute_actions and config.katana is not None:
        katana = KatanaController(config.katana, MidoMidiTransport(), metrics)
        if args.command == "run" and config.katana.stateSync.enabled:
            try:
                await asyncio.wrap_future(katana.start())
            except Exception as error:  # noqa: BLE001 - active run deliberately degrades to standard MIDI.
                logger.warning("Katana startup synchronization unavailable; continuing safely: %s", error)
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
        durationTask = None
        stopEvent = asyncio.Event()
        if args.duration_seconds is not None:
            if args.duration_seconds <= 0:
                raise ValueError("--duration-seconds must be positive")

            async def stopAfterDuration() -> None:
                await asyncio.sleep(args.duration_seconds)
                metrics.stopReason = "duration-limit"
                logger.info("session stop_reason=duration-limit duration_seconds=%g", args.duration_seconds)
                stopEvent.set()

            durationTask = asyncio.create_task(stopAfterDuration(), name="session-duration")
        try:
            await client.run(stopEvent)
        finally:
            if durationTask is not None:
                durationTask.cancel()
                await asyncio.gather(durationTask, return_exceptions=True)
        if metrics.stopReason is None:
            metrics.stopReason = "stopped"
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
    exitCode = 0
    try:
        if args.command == "midi-outputs":
            listMidiOutputs()
            metrics = None
        elif args.command == "midi-inputs":
            listMidiInputs()
            metrics = None
        elif args.command == "sysex-probe":
            report = runSysExProbe(args)
            metrics = None if report is None else report.metrics
            if report is not None and not report.success:
                logger.error("SysEx probe completed without a validated observation for every requested value")
                exitCode = 2
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
            metrics.stopReason = "interrupted"
            logger.info("summary=%s", json.dumps(metrics.snapshot(), separators=(",", ":")))
        return 130
    except (ConfigError, ValueError, RuntimeError) as error:
        logger.error("%s", error)
        return 2
    if metrics is not None:
        logger.info("summary=%s", json.dumps(metrics.snapshot(), separators=(",", ":")))
    return exitCode


if __name__ == "__main__":
    raise SystemExit(main())
