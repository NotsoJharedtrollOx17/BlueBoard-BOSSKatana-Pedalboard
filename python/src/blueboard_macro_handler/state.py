from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def defaultStatePath() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "blueboard-macro-handler" / "state.json"


def loadLastAddress(path: Path) -> str | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("lastAddress")
        return value if isinstance(value, str) else None
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def saveLastAddress(path: Path, address: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"lastAddress": address}, indent=2), encoding="utf-8")
    temporary.replace(path)
