from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
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
    loadConfig,
    officialEffectControls,
    writeConfig,
)
from .katana import KatanaController, MidoMidiTransport, createControlChange, createProgramChange, resolveOutputName
from .led_feedback import LedFeedbackController
from .logging_utils import configureLogging
from .models import RunMetrics
from .router import Router
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
    }.get(command, command)
    logger.info("================================================================================")
    logger.info("  BlueBoard + BOSS Katana Pedalboard v%s", __version__)
    logger.info("  Independent BLE-MIDI to USB-MIDI bridge for Windows and Linux")
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
        description="Cross-platform iRig BlueBoard to BOSS Katana MkII MIDI bridge",
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
    probe.add_argument("--channel", type=int, default=1, help="MIDI channel from 1 to 16")
    probe.add_argument("--program", type=int, default=0, help="preset selected before probing; MkII documents 0-8")
    probe.add_argument(
        "--effects",
        nargs="+",
        choices=tuple(officialEffectControls),
        default=tuple(officialEffectControls),
        help="one or more documented switches to probe (default: all)",
    )

    configure = commands.add_parser("configure", help="discover hardware and write a ready-to-run local profile")
    addLoggingOptions(configure)
    configure.add_argument("--config", type=Path, default=Path("blueboard-katana.json"))
    configure.add_argument("--output", help="exact or uniquely matching Katana MIDI output override")
    configure.add_argument("--name", default="BlueBoard", help="BlueBoard name substring")
    configure.add_argument("--scan-timeout", type=float, default=8.0)
    configure.add_argument("--state-file", type=Path, default=defaultStatePath())
    configure.add_argument("--force", action="store_true", help="replace an existing generated profile")

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


async def configurePedalboard(args: argparse.Namespace) -> None:
    if args.config.exists() and not args.force:
        raise ConfigError(f"{args.config} already exists; use --force to replace it")
    availableNames = MidoMidiTransport().listOutputNames()
    outputName = selectKatanaOutput(args.output, availableNames)
    print(f"Katana output : {outputName}")
    print(f"Scanning up to {args.scan_timeout:g} seconds for a BlueBoard...")
    devices = await discoverBlueBoards(args.name, args.scan_timeout)
    if not devices:
        raise RuntimeError("No BlueBoard found. Hold C while powering it on, then retry.")
    device = max(devices, key=lambda candidate: candidate.rssi if candidate.rssi is not None else -1000)
    config = katanaPedalboardConfig(outputName, args.name, args.scan_timeout)
    writeConfig(config, args.config, args.force)
    saveLastAddress(args.state_file, device.address)
    print(f"BlueBoard     : {device.name or '<unnamed>'} ({device.address})")
    print(f"Configuration : {args.config}")
    print("No MIDI commands were sent.")
    print(f"Next dry run  : blueboard-katana run --config {args.config} --debug")
    print(f"Enable actions: blueboard-katana run --config {args.config} --debug --execute-actions")


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
    if not 1 <= args.channel <= 16:
        raise ValueError("--channel must be from 1 to 16")
    if not 0 <= args.program <= 8:
        raise ValueError("--program must be from 0 to 8 for the documented Katana MkII profile")
    outputName = args.output
    if outputName is None:
        config = loadConfig(args.config)
        if config.katana is None:
            raise ConfigError(f"{args.config} does not contain a Katana configuration")
        outputName = config.katana.outputName
    effects = tuple(dict.fromkeys(args.effects))
    outputFunction("This probe selects the requested preset and tests only official CC16-CC21 switches.")
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
            createProgramChange(args.channel - 1, args.program),
            f"programChange channel={args.channel} program={args.program}",
        )
        outputFunction(f"Selected program {args.program}. Play a short phrase for each observation.")
        for effect in effects:
            controller = officialEffectControls[effect]
            choice = inputFunction(
                f"Press Enter to test {effect} (CC{controller}), s to skip, or q to finish: "
            ).strip().casefold()
            if choice == "q":
                break
            if choice == "s":
                results.append((effect, controller, "skipped", "skipped"))
                continue
            activeEffect = effect
            send(
                createControlChange(args.channel - 1, controller, 127),
                f"controlChange effect={effect} cc={controller} state=on",
            )
            observedOn = _probeObservation(f"Did {effect} turn ON?", inputFunction)
            send(
                createControlChange(args.channel - 1, controller, 0),
                f"controlChange effect={effect} cc={controller} state=off",
            )
            activeEffect = None
            observedOff = _probeObservation(f"Did {effect} turn OFF?", inputFunction)
            results.append((effect, controller, observedOn, observedOff))
    finally:
        if activeEffect is not None:
            controller = officialEffectControls[activeEffect]
            try:
                send(
                    createControlChange(args.channel - 1, controller, 0),
                    f"cleanup effect={activeEffect} cc={controller} state=off",
                )
            except Exception:
                logger.exception("probe cleanup failed for effect=%s", activeEffect)
        transport.close()

    outputFunction("\nProbe results")
    outputFunction("effect       cc   on        off")
    for effect, controller, observedOn, observedOff in results:
        outputFunction(f"{effect:<12} {controller:<4} {observedOn:<9} {observedOff}")
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
