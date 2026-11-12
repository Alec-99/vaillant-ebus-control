"""MQTT-first, **simulation-only** Vaillant thermostat service.

No code path in this file emits eBUS SetMode or changes the physical pump.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
import time

from vaillant_control.algorithm import Curve, Thermostat
from vaillant_control.settings import load_settings
from vaillant_control.mqtt_api import topic, parse_setpoint, parse_mode, parse_room_or_outdoor, discovery
from vaillant_control.storage import load as load_intent, save as save_intent
from vaillant_control.supervisor import mqtt_broker
from vaillant_control.ebusd_client import request as read_diagnostic
from vaillant_control.telemetry import capture, legacy_values

LOG = logging.getLogger("vaillant-control")


class ControllerService:
    def __init__(self, settings, storage: Path):
        self.settings = settings
        self.storage = storage
        self.mode, self.target = load_intent(storage, settings.room_target)
        self.room = None
        self.outdoor = None
        self.lock = threading.Lock()
        self.thermostat = Thermostat(Curve(slope=settings.curve_slope, kp=settings.room_kp,
                                           ki=settings.room_ki, min_flow=settings.flow_min,
                                           max_flow=settings.flow_max))
        self.mqtt = None

    def handle(self, path: str, payload: str, *, retained: bool = False) -> bool:
        """Accept typed commands/sensor readings; reject retained commands."""
        try:
            with self.lock:
                if path == topic("control/climate/temperature/set"):
                    if retained:
                        return False
                    self.target = parse_setpoint(payload)
                    save_intent(self.storage, self.mode, self.target)
                elif path == topic("control/climate/mode/set"):
                    if retained:
                        return False
                    self.mode = parse_mode(payload)
                    save_intent(self.storage, self.mode, self.target)
                elif path == topic("input/room"):
                    new = parse_room_or_outdoor(payload, "room")
                    if not new.valid(datetime.now(timezone.utc)):
                        return False
                    self.room = new
                elif path == topic("input/outdoor"):
                    new = parse_room_or_outdoor(payload, "outdoor")
                    if not new.valid(datetime.now(timezone.utc)):
                        return False
                    self.outdoor = new
                else:
                    return False
            return True
        except (ValueError, OSError) as exc:
            LOG.warning("MQTT input rejected on %s: %s", path, type(exc).__name__)
            return False

    def publish_snapshot(self):
        with self.lock:
            now = datetime.now(timezone.utc)
            decision = self.thermostat.evaluate(mode=self.mode, target=self.target,
                                                room=self.room, outdoor=self.outdoor, now=now)
            states = {"climate/temperature": str(self.target), "climate/mode": self.mode,
                      # Actual boiler HVAC action is unknown; don't advertise simulation as real heat.
                      "climate/action": "off", "heatcurve/desired_flow_c": "" if decision.requested_flow_c is None else str(decision.requested_flow_c),
                      "runtime": json.dumps({"controller": "monitor", "write_enabled": False,
                                             "ebusd_bus_enabled": self.settings.enable_bus,
                                             "simulated_demand": decision.demand,
                                             "reason": decision.reason,
                                             "simulated_flow_c": decision.requested_flow_c,
                                             "pump_control": "native-only", "timestamp": now.isoformat()})}
            # Clearing retained temperature states prevents stale sensor data
            # from remaining an apparently valid Home Assistant measurement.
            states["climate/current_temperature"] = (
                str(self.room.value_c) if self.room is not None and self.room.valid(now) else ""
            )
            states["weather/outdoor"] = (
                str(self.outdoor.value_c) if self.outdoor is not None and self.outdoor.valid(now) else ""
            )
        for key, val in states.items():
            self.mqtt.publish(topic("state/" + key), val, qos=1, retain=True)
        # Batch 2: publish a complete typed snapshot, including explicit
        # unavailable/disabled entries. The observation time of the underlying
        # eBUS telegram is UNKNOWN; a successful cached read is not "live".
        # Never call the TCP diagnostic reader when enable_bus=false.
        telemetry = capture(bus_enabled=self.settings.enable_bus, reader=read_diagnostic, now=now)
        self.mqtt.publish(topic("state/boiler/telemetry"),
                          json.dumps(telemetry, allow_nan=False), qos=1, retain=True)
        # Keep the existing, unretained compatibility topic for old consumers;
        # it is NOT a stream with verified physical measurement timestamps.
        self.mqtt.publish(topic("state/boiler/diagnostics"),
                          json.dumps(legacy_values(telemetry)), qos=0, retain=False)


def main():
    import paho.mqtt.client as mqtt
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    service = ControllerService(settings, Path("/data/intent.json"))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="vaillant-ebus-control", protocol=mqtt.MQTTv311)
    service.mqtt = client
    broker = mqtt_broker()
    if broker.username:
        client.username_pw_set(broker.username, broker.password)
    if broker.ssl:
        client.tls_set()
    client.will_set(topic("availability"), "offline", qos=1, retain=True)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.max_queued_messages_set(100)

    def announce_discovery(client):
        client.publish("homeassistant/climate/vaillant_ebus_virtual/config",
                       json.dumps(discovery()), qos=1, retain=True)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOG.error("MQTT connection denied: %s", reason_code)
            return
        for suffix in ("control/climate/temperature/set", "control/climate/mode/set", "input/room", "input/outdoor"):
            client.subscribe(topic(suffix), qos=1)
        client.subscribe("homeassistant/status", qos=1)
        # Discovery and current accepted state are republished on reconnect.
        announce_discovery(client)
        client.publish(topic("availability"), "online", qos=1, retain=True)
        service.publish_snapshot()

    def on_message(client, userdata, msg):
        if msg.topic == "homeassistant/status":
            if msg.payload == b"online":
                announce_discovery(client)
            return
        if service.handle(msg.topic, msg.payload.decode("utf-8", errors="replace"), retained=msg.retain):
            service.publish_snapshot()

    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        LOG.warning("MQTT disconnected: %s", reason_code)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.connect_async(broker.host, broker.port, keepalive=60)
    client.loop_start()
    LOG.warning("MONITOR-ONLY controller running: no boiler writes implemented")
    try:
        while True:
            time.sleep(settings.poll_interval)
            service.publish_snapshot()
    finally:
        client.publish(topic("availability"), "offline", qos=1, retain=True).wait_for_publish(timeout=2)
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
