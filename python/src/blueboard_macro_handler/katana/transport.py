from __future__ import annotations

from typing import Any, Protocol

from .commands import MidiCommand


class MidiTransport(Protocol):
    def listOutputNames(self) -> tuple[str, ...]: ...
    def open(self, outputName: str) -> None: ...
    def send(self, command: MidiCommand) -> None: ...
    def close(self) -> None: ...


def resolveOutputName(requestedName: str, availableNames: tuple[str, ...]) -> str:
    requested = requestedName.strip()
    if not requested:
        raise ValueError("Katana MIDI output name cannot be empty")
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
        raise RuntimeError(f"MIDI output {requestedName!r} was not found; available outputs: {available}")
    raise RuntimeError(f"MIDI output {requestedName!r} is ambiguous: {', '.join(repr(name) for name in matches)}")


class MidoMidiTransport:
    def __init__(self, midoModule: Any | None = None) -> None:
        self.midoModule = midoModule
        self.outputPort: Any | None = None
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

    def open(self, outputName: str) -> None:
        if self.outputPort is not None:
            self.close()
        resolvedName = resolveOutputName(outputName, self.listOutputNames())
        self.outputPort = self.getMido().open_output(resolvedName)
        self.outputName = resolvedName

    def send(self, command: MidiCommand) -> None:
        if self.outputPort is None:
            raise RuntimeError("Katana MIDI output is not open")
        message = self.getMido().Message.from_bytes(command.data)
        self.outputPort.send(message)

    def close(self) -> None:
        if self.outputPort is not None:
            self.outputPort.close()
            self.outputPort = None
        self.outputName = None
