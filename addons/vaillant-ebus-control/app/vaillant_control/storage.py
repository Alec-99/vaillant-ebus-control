"""Persist accepted HA intent, not boiler operating state."""
from __future__ import annotations
import json
from pathlib import Path


def load(path: Path, default_target: float) -> tuple[str, float]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        from .mqtt_api import parse_mode, parse_setpoint
        return parse_mode(data["mode"]), parse_setpoint(str(data["target_c"]))
    except (OSError, ValueError, KeyError, TypeError):
        return "off", default_target


def save(path: Path, mode: str, target_c: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"mode": mode, "target_c": target_c}), encoding="utf-8")
    tmp.replace(path)
