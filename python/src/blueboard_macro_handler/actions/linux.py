from __future__ import annotations


class LinuxKeyboard:
    def __init__(self) -> None:
        try:
            from evdev import UInput, ecodes
            from evdev.uinput import UInputError
        except ImportError as error:
            raise RuntimeError("Linux keyboard macros require: pip install 'blueboard-macro-handler[linux]'") from error
        self.ecodes = ecodes
        self.keyMap = self._buildKeyMap(ecodes)
        try:
            self.device = UInput({ecodes.EV_KEY: sorted(set(self.keyMap.values()))}, name="BlueBoard Macro Handler")
        except (OSError, UInputError) as error:
            raise RuntimeError("Linux keyboard macros require a usable /dev/uinput; run setupBlueBoard.sh and join the input group") from error
        self.activeKeys: list[int] = []

    @staticmethod
    def _buildKeyMap(ecodes) -> dict[str, int]:
        result = {
            "CTRL": ecodes.KEY_LEFTCTRL, "CONTROL": ecodes.KEY_LEFTCTRL,
            "SHIFT": ecodes.KEY_LEFTSHIFT, "ALT": ecodes.KEY_LEFTALT,
            "WIN": ecodes.KEY_LEFTMETA, "LWIN": ecodes.KEY_LEFTMETA,
            "RWIN": ecodes.KEY_RIGHTMETA, "TAB": ecodes.KEY_TAB,
            "ENTER": ecodes.KEY_ENTER, "ESC": ecodes.KEY_ESC,
            "SPACE": ecodes.KEY_SPACE, "BACKSPACE": ecodes.KEY_BACKSPACE,
            "LEFT": ecodes.KEY_LEFT, "RIGHT": ecodes.KEY_RIGHT,
            "UP": ecodes.KEY_UP, "DOWN": ecodes.KEY_DOWN,
            "HOME": ecodes.KEY_HOME, "END": ecodes.KEY_END,
            "PAGEUP": ecodes.KEY_PAGEUP, "PAGEDOWN": ecodes.KEY_PAGEDOWN,
            "INSERT": ecodes.KEY_INSERT, "DELETE": ecodes.KEY_DELETE,
        }
        result.update({letter: getattr(ecodes, f"KEY_{letter}") for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"})
        result.update({str(number): getattr(ecodes, f"KEY_{number}") for number in range(10)})
        result.update({f"F{index}": getattr(ecodes, f"KEY_F{index}") for index in range(1, 25)})
        return result

    def sendCombo(self, keys: tuple[str, ...]) -> None:
        try:
            codes = [self.keyMap[key.upper()] for key in keys]
        except KeyError as error:
            raise ValueError(f"unsupported Linux key: {error.args[0]}") from error
        for code in codes:
            self.device.write(self.ecodes.EV_KEY, code, 1)
        for code in reversed(codes):
            self.device.write(self.ecodes.EV_KEY, code, 0)
        self.device.syn()

    def releaseAll(self) -> None:
        for code in reversed(self.activeKeys):
            self.device.write(self.ecodes.EV_KEY, code, 0)
        if self.activeKeys:
            self.device.syn()
        self.activeKeys.clear()

    def close(self) -> None:
        self.releaseAll()
        self.device.close()
