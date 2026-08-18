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
from .config import ConfigError, configAsDict, loadConfig
from .katana import KatanaController, MidoMidiTransport, createControlChange, createProgramChange
from .led_feedback import LedFeedbackController
from .logging_utils import configureLogging
from .models import RunMetrics
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
        "katana-test": "explicit standard-MIDI amplifier test (blueboard-katana katana-test)",
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
