from __future__ import annotations

import logging

from ..config import ActionSpec
from ..katana.controller import KatanaController

logger = logging.getLogger("blueboard.actions")


class ActionDispatcher:
    def __init__(
        self,
        execute: bool = False,
        katana: KatanaController | None = None,
    ) -> None:
        self.execute = execute
        self.katana = katana

    def invoke(self, action: ActionSpec) -> bool:
        if action.type == "katana":
            target = f"preset={action.preset}" if action.preset is not None else f"effect={action.effect}"
            details = f"command={action.command} {target}"
        elif action.type == "log":
            details = f"message={action.message!r}"
        else:
            raise ValueError(f"unsupported action type: {action.type}")
        logger.info("action type=%s execute=%s %s", action.type, self.execute, details)
        if not self.execute or action.type == "log":
            if action.message:
                logger.info("action message=%s", action.message)
            return False
        if self.katana is None:
            raise RuntimeError("Katana controller is not configured")
        self.katana.execute(action)
        return True

    def close(self) -> None:
        if self.katana is not None:
            self.katana.close()
