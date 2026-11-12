"""Supervisor app options and fail-closed validation."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    enable_bus: bool = False
    network_device: str = ""
    mqtt_prefix: str = "vaillant_ebus/v1"
    poll_interval: int = 30
    scanconfig: bool = False
    room_target: float = 20.0
    curve_slope: float = 1.2
    room_kp: float = 2.0
    room_ki: float = 0.0
    flow_min: float = 30.0
    flow_max: float = 65.0

    @classmethod
    def from_mapping(cls, raw: dict) -> "Settings":
        if not isinstance(raw, dict):
            raise ValueError("Options must be a JSON object")
        accepted = set(cls.__dataclass_fields__)
        values = {key: raw[key] for key in accepted if key in raw}
        s = cls(**values)
        if type(s.enable_bus) is not bool or type(s.scanconfig) is not bool:
            raise ValueError("enable_bus and scanconfig must be boolean")
        if not isinstance(s.network_device, str):
            raise ValueError("network_device must be a string")
        if s.scanconfig:
            raise ValueError("scanconfig cannot be combined with strict ebusd --readonly")
        if s.enable_bus and not s.network_device.startswith(("enh:", "ens:")):
            raise ValueError("Only explicit enhanced network adapters are supported")
        if any(ch.isspace() for ch in s.network_device) or "\x00" in s.network_device:
            raise ValueError("Invalid adapter address")
        if s.mqtt_prefix != "vaillant_ebus/v1":
            raise ValueError("MQTT namespace is fixed at vaillant_ebus/v1 in API v1")
        if type(s.poll_interval) is not int or not 10 <= s.poll_interval <= 300:
            raise ValueError("poll_interval must be 10..300 seconds")
        from math import isfinite
        for name, lo, hi in (("room_target", 5, 30), ("curve_slope", 0, 5),
                             ("room_kp", 0, 20), ("room_ki", 0, 1),
                             ("flow_min", 20, 80), ("flow_max", 20, 85)):
            val = getattr(s, name)
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not isfinite(val) or not lo <= val <= hi:
                raise ValueError(f"Invalid {name}")
        if s.flow_min >= s.flow_max:
            raise ValueError("flow_min must be smaller than flow_max")
        return s


def load_settings(path: str = "/data/options.json") -> Settings:
    p = Path(path)
    return Settings.from_mapping(json.loads(p.read_text()) if p.exists() else {})
