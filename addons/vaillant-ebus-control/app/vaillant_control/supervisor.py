"""MQTT broker service discovery using HA Supervisor's own service API."""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Broker:
    host: str
    port: int
    username: str = ""
    password: str = ""
    ssl: bool = False


def mqtt_broker() -> Broker:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("Missing Supervisor token; no MQTT credentials")
    url = os.environ.get("SUPERVISOR_URL", "http://supervisor") + "/services/mqtt"
    req = Request(url, headers={"Authorization": f"Bearer {token}"})
    with urlopen(req, timeout=5) as response:
        data = json.load(response)
    # Supervisor REST generally wraps service info under `data`.
    info = data.get("data", data)
    if not info.get("host"):
        raise RuntimeError("MQTT service is unavailable")
    return Broker(str(info["host"]), int(info.get("port", 1883)),
                  str(info.get("username") or ""), str(info.get("password") or ""), bool(info.get("ssl", False)))
