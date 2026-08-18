from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes
from typing import ClassVar

INPUT_KEYBOARD, KEYEVENTF_KEYUP = 1, 0x0002
ULONG_PTR = ctypes.c_size_t


class KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class InputUnion(ctypes.Union):
    _fields_: ClassVar = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]


namedKeys = {
    "BACKSPACE": 0x08, "TAB": 0x09, "ENTER": 0x0D, "SHIFT": 0x10,
    "CTRL": 0x11, "CONTROL": 0x11, "ALT": 0x12, "ESC": 0x1B,
    "SPACE": 0x20, "PAGEUP": 0x21, "PAGEDOWN": 0x22, "END": 0x23,
    "HOME": 0x24, "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27,
    "DOWN": 0x28, "INSERT": 0x2D, "DELETE": 0x2E,
    "WIN": 0x5B, "LWIN": 0x5B, "RWIN": 0x5C,
}
namedKeys.update({f"F{index}": 0x6F + index for index in range(1, 25)})


def keyCode(name: str) -> int:
    normalized = name.upper()
    if normalized in namedKeys:
        return namedKeys[normalized]
    if len(normalized) == 1 and normalized.isascii() and normalized.isalnum():
        return ord(normalized)
    raise ValueError(f"unsupported Windows key: {name}")


def getSendInput() -> Callable | None:
    if not hasattr(ctypes, "WinDLL"):
        return None
    sendInput = ctypes.WinDLL("user32", use_last_error=True).SendInput
    sendInput.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
    sendInput.restype = wintypes.UINT
    return sendInput


class WindowsKeyboard:
    def __init__(self, sendInput: Callable | None = None) -> None:
        self.sendInput = sendInput if sendInput is not None else getSendInput()
        self.activeKeys: list[int] = []

    @staticmethod
    def buildInputs(keys: tuple[str, ...]):
        codes = [keyCode(key) for key in keys]
        inputs = (Input * (len(codes) * 2))()
        for index, code in enumerate(codes):
            inputs[index].type, inputs[index].ki.wVk = INPUT_KEYBOARD, code
        for index, code in enumerate(reversed(codes), len(codes)):
            inputs[index].type, inputs[index].ki.wVk, inputs[index].ki.dwFlags = INPUT_KEYBOARD, code, KEYEVENTF_KEYUP
        return inputs

    def _send(self, inputs) -> None:
        if self.sendInput is None:
            raise RuntimeError("Windows SendInput is unavailable")
        if hasattr(ctypes, "set_last_error"):
            ctypes.set_last_error(0)
        sent = self.sendInput(len(inputs), inputs, ctypes.sizeof(Input))
        if sent != len(inputs):
            lastError = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else 0
            raise OSError(lastError, f"SendInput sent {sent} of {len(inputs)} events")

    def sendCombo(self, keys: tuple[str, ...]) -> None:
        self._send(self.buildInputs(keys))

    def releaseAll(self) -> None:
        if not self.activeKeys:
            return
        inputs = (Input * len(self.activeKeys))()
        for index, code in enumerate(reversed(self.activeKeys)):
            inputs[index].type, inputs[index].ki.wVk, inputs[index].ki.dwFlags = INPUT_KEYBOARD, code, KEYEVENTF_KEYUP
        self._send(inputs)
        self.activeKeys.clear()

    def close(self) -> None:
        self.releaseAll()
