"""Versioned MQTT climate contract, input validators and discovery payloads."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from math import isfinite
from .algorithm import Reading

PREFIX = "vaillant_ebus/v1"


def topic(suffix: str) -> str:
    return f"{PREFIX}/{suffix}"


def parse_room_or_outdoor(payload: str, kind: str) -> Reading:
    try:
        msg = json.loads(payload)
        if msg.get("quality", "ok") != "ok":
            raise ValueError("Sensor quality must be ok")
        value = msg["value_c"]
        stamp = msg["observed_at"]
        source = msg["source"]
        if not isinstance(source, str) or not 1 <= len(source) <= 128:
            raise ValueError("Invalid sensor source")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError("Invalid value_c")
        low, high = ((-20, 60) if kind == "room" else (-50, 60))
        if not low <= value <= high:
            raise ValueError("Out-of-range reading")
        if not isinstance(stamp, str):
            raise ValueError("Invalid timestamp")
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        return Reading(float(value), parsed.astimezone(timezone.utc), source)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise ValueError("Invalid sensor payload") from exc


def parse_setpoint(payload: str) -> float:
    try:
        value = float(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("Temperature setpoint must be numeric") from exc
    if not isfinite(value) or not 5 <= value <= 30:
        raise ValueError("Temperature setpoint must be 5..30°C")
    return round(value, 1)


def parse_mode(payload: str) -> str:
    if payload not in {"heat", "off"}:
        raise ValueError("Mode must be heat or off")
    return payload


def discovery(prefix: str = PREFIX) -> dict:
    return {
        "name": "Vaillant Virtual Thermostat (simulation)",
        "unique_id": "vaillant_ebus_virtual_climate",
        "device": {"identifiers": ["vaillant_ebus_virtual"], "name": "Vaillant eBUS Controller", "manufacturer": "Community", "model": "Monitor-only prototype"},
        "modes": ["off", "heat"],
        "min_temp": 5, "max_temp": 30, "temp_step": 0.5, "temperature_unit": "C",
        "optimistic": False,
        "mode_command_topic": f"{prefix}/control/climate/mode/set",
        "mode_state_topic": f"{prefix}/state/climate/mode",
        "temperature_command_topic": f"{prefix}/control/climate/temperature/set",
        "temperature_state_topic": f"{prefix}/state/climate/temperature",
        "current_temperature_topic": f"{prefix}/state/climate/current_temperature",
        "action_topic": f"{prefix}/state/climate/action",
        "availability_topic": f"{prefix}/availability",
        "payload_available": "online", "payload_not_available": "offline",
    }
