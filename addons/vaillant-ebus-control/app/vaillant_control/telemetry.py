"""Typed, read-only BAI diagnostics.

A successful ebusd cached read does NOT prove that the telegram is recent:
the reader never sends "-f", and strict --readonly may not have received
any passive update. Cache values are deliberately NOT called fresh or live.
No eBUS write/actuation interface is provided.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
import re
from typing import Callable

from .ebusd_client import safe_value

# Register names are a strict allowlist implemented in ebusd_client.
# The return mirror (second semicolon field) is NOT a temperature.
@dataclass(frozen=True)
class Field:
    name: str
    register: str
    kind: str
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None


FIELDS = (
    Field("flow_actual_c", "FlowTemp", "number", "°C", 0, 100),
    Field("return_actual_c", "ReturnTemp", "number", "°C", 0, 100),
    Field("flow_target_c", "FlowTempDesired", "number", "°C", 0, 100),
    Field("flame", "Flame", "switch"),
    Field("pump", "WP", "switch"),
    Field("boiler_state", "Statenumber", "integer", None, 0, 255),
    Field("modulation_desired_pct", "ModulationDesired", "number", "%", 0, 100),
    Field("remaining_boiler_block_min", "RemainingBoilerblocktime", "number", "min", 0, 300),
)
NAME_BY_REGISTER = {field.register: field for field in FIELDS}
NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
INTEGER = re.compile(r"^\d{1,3}$")


def decode(field: Field, raw: str) -> int | float | str:
    """Decode ONLY the first ebusd field (discard ReturnTemp.tempmirror)."""
    first = safe_value(field.register, raw)
    if first is None:
        raise ValueError("Missing, error or cutoff response")
    if field.kind == "switch":
        # Do not turn unknown alarm/status texts into False.
        normalized = first.casefold()
        if normalized in ("on", "yes", "1", "true"):
            return "on"
        if normalized in ("off", "no", "0", "false"):
            return "off"
        raise ValueError("Unknown binary state")
    if field.kind == "integer":
        if not INTEGER.fullmatch(first):
            raise ValueError("Invalid integer state")
        value = int(first)
    else:
        if not NUMBER.fullmatch(first):
            raise ValueError("Invalid numeric reading")
        value = float(first)
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Nonfinite reading")
    if field.minimum is not None and value < field.minimum:
        raise ValueError("Below validated range")
    if field.maximum is not None and value > field.maximum:
        raise ValueError("Above validated range")
    return value


def capture(*, bus_enabled: bool, reader: Callable[[str], str],
            now: datetime | None = None) -> dict:
    """Return a complete, explicit-quality snapshot; no sensor carries over.

    read_at is *the time the daemon cache was queried*, not the physical
    measurement time. The actual bus observation timestamp is unknown.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    captured = {}
    for field in FIELDS:
        state = {
            "register": field.register,
            "value": None,
            "unit": field.unit,
            "quality": "disabled" if not bus_enabled else "unavailable",
            "source": "ebusd_bai_cache",
            "observed_at": None,
            "read_at": now.isoformat(),
            "freshness_verified": False,
        }
        if bus_enabled:
            try:
                raw = reader(field.register)
                # Missing cached replies are different from invalid decoded data.
                # Neither is equivalent to a measured numeric zero.
                if raw is None or not str(raw).strip() or str(raw).strip() == "-" or str(raw).strip().startswith("ERR:"):
                    state["quality"] = "unavailable"
                else:
                    state["value"] = decode(field, raw)
                    state["quality"] = "cache_unverified"
            except (OSError, TimeoutError, ConnectionError):
                # Socket/daemon unavailable; never repeat previous cached values.
                state["quality"] = "unavailable"
            except (ValueError, TypeError, UnicodeError, AttributeError):
                state["quality"] = "invalid"
        captured[field.name] = state
    return {
        "schema_version": 1,
        "kind": "read_only_bai_cache",
        "bus_enabled": bool(bus_enabled),
        "sampled_at": now.isoformat(),
        "data_freshness_verified": False,
        "measurements": captured,
    }


def legacy_values(snapshot: dict) -> dict:
    """Compatibility-only flat diagnostic values; no freshness is claimed."""
    return {
        field.register: str(snapshot["measurements"][field.name]["value"])
        for field in FIELDS
        if snapshot["measurements"][field.name]["quality"] == "cache_unverified"
    }
