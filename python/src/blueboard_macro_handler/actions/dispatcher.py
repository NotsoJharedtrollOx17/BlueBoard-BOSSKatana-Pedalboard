from __future__ import annotations

import logging
import socket
import subprocess
import sys

from ..config import ActionSpec
from ..katana.controller import KatanaController
from .base import KeyboardBackend

logger = logging.getLogger("blueboard.actions")


class ActionDispatcher:
    def __init__(
        self,
        execute: bool = False,
        keyboard: KeyboardBackend | None = None,
        katana: KatanaController | None = None,
    ) -> None:
        self.execute = execute
        self.keyboard = keyboard
        self.katana = katana

    def getKeyboard(self) -> KeyboardBackend:
        if self.keyboard is None:
            if sys.platform == "win32":
                from .windows import WindowsKeyboard
                self.keyboard = WindowsKeyboard()
            elif sys.platform.startswith("linux"):
                from .linux import LinuxKeyboard
                self.keyboard = LinuxKeyboard()
            else:
                raise RuntimeError(f"keyboard macros are unsupported on {sys.platform}")
        return self.keyboard

    def invoke(self, action: ActionSpec) -> bool:
        if action.type == "keyboard":
            details = f"keys={'+'.join(action.keys)}"
        elif action.type == "udp":
            details = f"target={action.host}:{action.port} message={action.message!r}"
        elif action.type == "launch":
            details = f"program={action.program!r} args={list(action.args)!r}"
        elif action.type == "katana":
            target = f"preset={action.preset}" if action.preset is not None else f"effect={action.effect}"
            details = f"command={action.command} {target}"
        else:
            details = f"message={action.message!r}"
        logger.info("action type=%s execute=%s %s", action.type, self.execute, details)
        if not self.execute or action.type == "log":
            if action.message:
                logger.info("action message=%s", action.message)
            return False
        if action.type == "keyboard":
            self.getKeyboard().sendCombo(action.keys)
        elif action.type == "udp":
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as datagram:
                datagram.sendto(action.message.encode("utf-8"), (action.host, action.port))
        elif action.type == "launch":
            subprocess.Popen([action.program, *action.args], shell=False)
        elif action.type == "katana":
            if self.katana is None:
                raise RuntimeError("Katana controller is not configured")
            self.katana.execute(action)
        else:
            raise ValueError(f"unsupported action type: {action.type}")
        return True

    def releaseAll(self) -> None:
        if self.keyboard is not None:
            self.keyboard.releaseAll()

    def close(self) -> None:
        try:
            if self.keyboard is not None:
                self.keyboard.close()
        finally:
            if self.katana is not None:
                self.katana.close()
