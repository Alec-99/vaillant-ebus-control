"""Safe launcher for the pinned ebusd executable.

No adapter is touched by default. Even with enable_bus=true, ebusd receives
--readonly: **no bus transmissions or active heating commands**.
"""
from __future__ import annotations
import logging
import os
import time
from vaillant_control.settings import load_settings
from vaillant_control.supervisor import mqtt_broker


def build_args(settings, broker):
    if not settings.enable_bus:
        return None
    args = ["/usr/local/bin/ebusd", "--foreground", "--readonly", "--updatecheck=off",
            f"--device={settings.network_device}", f"--pollinterval={settings.poll_interval}",
            "--mqtttopic=ebusd", "--mqttjson"]
    # Strict --readonly is incompatible with --scanconfig in ebusd 26.1.
    # Validation in Settings disallows scanconfig; never add it to these args.
    if broker:
        args += [f"--mqtthost={broker.host}", f"--mqttport={broker.port}"]
        if broker.username:
            args.append(f"--mqttuser={broker.username}")
        if broker.password:
            args.append(f"--mqttpass={broker.password}")
    return args


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    if not settings.enable_bus:
        logging.warning("Bus connection DISABLED: enable_bus=false. No adapter access.")
        while True:
            time.sleep(60)
    try:
        broker = mqtt_broker()
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        logging.error("MQTT discovery unavailable: %s", type(exc).__name__)
        broker = None
    args = build_args(settings, broker)
    # Credentials are command arguments; NEVER log args or child environment.
    logging.warning("Starting ebusd in STRICT --readonly monitor mode")
    os.execv(args[0], args)


if __name__ == "__main__":
    main()
