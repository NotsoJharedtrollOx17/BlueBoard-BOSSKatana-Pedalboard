from __future__ import annotations

import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Protocol

from .commands import MidiCommand

logger = logging.getLogger("blueboard.katana.transport")
alsaPortCoordinatesPattern = re.compile(r"\s+\d+:\d+$")


@dataclass(frozen=True)
class ReceivedMidiMessage:
    """A Mido-independent copy of one incoming MIDI message."""

    messageType: str
    data: tuple[int, ...]
    receivedAt: float = field(default_factory=monotonic)


MidiInputCallback = Callable[[ReceivedMidiMessage], None]


class MidiTransport(Protocol):
    def listInputNames(self) -> tuple[str, ...]: ...
    def listOutputNames(self) -> tuple[str, ...]: ...
    def openInput(self, inputName: str, callback: MidiInputCallback) -> None: ...
    def open(self, outputName: str) -> None: ...
    def send(self, command: MidiCommand) -> None: ...
    def close(self) -> None: ...


def _resolvePortName(kind: str, requestedName: str, availableNames: tuple[str, ...]) -> str:
    requested = requestedName.strip()
    if not requested:
        raise ValueError(f"Katana MIDI {kind} name cannot be empty")
    if requested in availableNames:
        return requested
    exactIgnoringCase = [name for name in availableNames if name.casefold() == requested.casefold()]
    if len(exactIgnoringCase) == 1:
        return exactIgnoringCase[0]
    matches = [name for name in availableNames if requested.casefold() in name.casefold()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        available = ", ".join(repr(name) for name in availableNames) or "none"
        raise RuntimeError(f"MIDI {kind} {requestedName!r} was not found; available {kind}s: {available}")
    raise RuntimeError(f"MIDI {kind} {requestedName!r} is ambiguous: {', '.join(repr(name) for name in matches)}")


def resolveInputName(requestedName: str, availableNames: tuple[str, ...]) -> str:
    return _resolvePortName("input", requestedName, availableNames)


def resolveOutputName(requestedName: str, availableNames: tuple[str, ...]) -> str:
    return _resolvePortName("output", requestedName, availableNames)


def deriveStablePortSelector(selectedName: str, availableNames: tuple[str, ...]) -> str:
    """Return the shortest conservative selector that still identifies selectedName."""
    selected = _resolvePortName("port", selectedName, availableNames)
    candidates = [selected]
    withoutCoordinates = alsaPortCoordinatesPattern.sub("", selected).strip()
    if withoutCoordinates and withoutCoordinates != selected:
        candidates.append(withoutCoordinates)
    for candidate in tuple(candidates):
        if ":" not in candidate:
            continue
        withoutClient = candidate.split(":", 1)[1].strip()
        if withoutClient:
            candidates.append(withoutClient)
    safe: list[str] = []
    for candidate in dict.fromkeys(candidates):
        try:
            if _resolvePortName("port", candidate, availableNames) == selected:
                safe.append(candidate)
        except (RuntimeError, ValueError):
            continue
    return min(safe, key=lambda candidate: (len(candidate), candidates.index(candidate))) if safe else selected


def _portOpenError(kind: str, resolvedName: str, error: Exception) -> RuntimeError:
    guidance = ""
    if sys.platform.startswith("linux"):
        guidance = (
            "; close Tone Studio, DAWs, MIDI monitors, or stale pedalboard processes, "
            "then verify ALSA sequencer permissions"
        )
    return RuntimeError(f"could not open Katana MIDI {kind} {resolvedName!r}: {error}{guidance}")


class MidoMidiTransport:
    def __init__(self, midoModule: Any | None = None) -> None:
        self.midoModule = midoModule
        self.inputPort: Any | None = None
        self.outputPort: Any | None = None
        self.inputName: str | None = None
        self.outputName: str | None = None

    def getMido(self) -> Any:
        if self.midoModule is None:
            try:
                import mido
            except ImportError as error:
                raise RuntimeError(
                    "Katana MIDI support is not installed; run pip install -e .[katana]"
                ) from error
            self.midoModule = mido
        return self.midoModule

    def listOutputNames(self) -> tuple[str, ...]:
        return tuple(self.getMido().get_output_names())

    def listInputNames(self) -> tuple[str, ...]:
        return tuple(self.getMido().get_input_names())

    def openInput(self, inputName: str, callback: MidiInputCallback) -> None:
        if self.inputPort is not None:
            self.inputPort.close()
            self.inputPort = None
            self.inputName = None
        resolvedName = resolveInputName(inputName, self.listInputNames())

        def receive(message: Any) -> None:
            messageType = str(message.type)
            if messageType == "sysex":
                data = tuple(message.data)
            else:
                data = tuple(message.bytes())
            callback(ReceivedMidiMessage(messageType, data))

        try:
            self.inputPort = self.getMido().open_input(resolvedName, callback=receive)
        except Exception as error:
            raise _portOpenError("input", resolvedName, error) from error
        self.inputName = resolvedName
        logger.info("katana MIDI input selector=%r resolved=%r", inputName, resolvedName)

    def open(self, outputName: str) -> None:
        if self.outputPort is not None:
            self.outputPort.close()
            self.outputPort = None
            self.outputName = None
        resolvedName = resolveOutputName(outputName, self.listOutputNames())
        try:
            self.outputPort = self.getMido().open_output(resolvedName)
        except Exception as error:
            raise _portOpenError("output", resolvedName, error) from error
        self.outputName = resolvedName
        logger.info("katana MIDI output selector=%r resolved=%r", outputName, resolvedName)

    def send(self, command: MidiCommand) -> None:
        if self.outputPort is None:
            raise RuntimeError("Katana MIDI output is not open")
        message = self.getMido().Message.from_bytes(command.data)
        self.outputPort.send(message)

    def close(self) -> None:
        firstError: Exception | None = None
        if self.outputPort is not None:
            try:
                self.outputPort.close()
            except Exception as error:  # noqa: BLE001 - still attempt to close the input port
                firstError = error
            finally:
                self.outputPort = None
        if self.inputPort is not None:
            try:
                self.inputPort.close()
            except Exception as error:  # noqa: BLE001 - report only after both close attempts
                if firstError is None:
                    firstError = error
            finally:
                self.inputPort = None
        self.inputName = None
        self.outputName = None
        if firstError is not None:
            raise firstError
