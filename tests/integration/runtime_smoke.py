#!/usr/bin/env python3
"""End-to-end runtime smoke test: real s6 image + broker + mocked Supervisor.

Requires Docker (Linux host networking), paho-mqtt 2.1 and the built image.
No HA system access, no eBUS adapter, no boiler writes, no fork modifications.
CI runs this script ONLY after Docker has built the combined app image.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import uuid

import paho.mqtt.client as mqtt


PREFIX = "vaillant_ebus/v1"
DISCOVERY = "homeassistant/climate/vaillant_ebus_virtual/config"


def run(*args: str, timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=check)


def await_tcp(port: int, *, timeout: float = 25) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise AssertionError(f"Service port {port} not listening after {timeout}s")


class Inbox:
    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []
        self.condition = threading.Condition()

    def add(self, topic: str, payload: str) -> None:
        with self.condition:
            self.items.append((topic, payload))
            self.condition.notify_all()

    def size(self) -> int:
        with self.condition:
            return len(self.items)

    def wait(self, topic: str, predicate=lambda text: True, *, since: int = 0,
             timeout: float = 35.0) -> str:
        end = time.monotonic() + timeout
        with self.condition:
            while True:
                for key, content in self.items[since:]:
                    if key == topic and predicate(content):
                        return content
                remain = end - time.monotonic()
                if remain <= 0:
                    seen = self.items[-12:]
                    raise AssertionError(f"Expected {topic} predicate after index {since}; last messages={seen}")
                self.condition.wait(min(remain, 1.0))


class MockSupervisor(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/services/mqtt":
            self.send_error(404)
            return
        if self.headers.get("Authorization") != "Bearer ci-test-token":
            self.send_error(403)
            return
        body = json.dumps({"result": "ok", "data": {
            "host": "127.0.0.1", "port": 1883, "ssl": False,
            "username": "", "password": ""
        }}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass


def start_mock_supervisor() -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockSupervisor)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return server, worker


def publish(client: mqtt.Client, suffix: str, value: str, *, retain: bool = False) -> None:
    result = client.publish(PREFIX + "/" + suffix, value, qos=1, retain=retain)
    result.wait_for_publish(timeout=8)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise AssertionError(f"MQTT publish failed for {suffix}: {result.rc}")


def fresh_sensor(value: float) -> str:
    return json.dumps({"value_c": value,
                       "observed_at": datetime.now(timezone.utc).isoformat(),
                       "source": "sensor.ci_test", "quality": "ok"})


def start_docker(name: str, *args: str) -> None:
    run("docker", "run", "-d", "--name", name, *args, timeout=45)


def exercise(image: str) -> None:
    unique = uuid.uuid4().hex[:10]
    broker_name = "vaillant-ci-broker-" + unique
    app_name = "vaillant-ci-app-" + unique
    with tempfile.TemporaryDirectory(prefix="vaillant-runtime-") as root:
        work = Path(root)
        options = work / "data"
        options.mkdir()
        (options / "options.json").write_text(json.dumps({
            "enable_bus": False, "poll_interval": 10, "room_target": 20.0
        }), encoding="utf8")
        conf = work / "mosquitto.conf"
        conf.write_text("listener 1883 127.0.0.1\nallow_anonymous true\npersistence false\nlog_dest stdout\n", encoding="utf8")
        server, thread = start_mock_supervisor()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id="vaillant-ci-probe-" + unique,
                             protocol=mqtt.MQTTv311)
        inbox = Inbox()

        def on_connect(mclient, _userdata, _flags, reason_code, _properties):
            if reason_code.is_failure:
                raise AssertionError("probe MQTT connection rejected")
            mclient.subscribe([(PREFIX + "/#", 1), (DISCOVERY, 1)])

        def on_message(_mclient, _userdata, message):
            inbox.add(message.topic, message.payload.decode("utf8", errors="replace"))

        client.on_connect = on_connect
        client.on_message = on_message
        client.reconnect_delay_set(min_delay=1, max_delay=3)
        try:
            start_docker(
                broker_name, "--network", "host", "-v",
                f"{conf}:/mosquitto/config/mosquitto.conf:ro",
                "eclipse-mosquitto:2"
            )
            await_tcp(1883)
            client.connect("127.0.0.1", 1883, keepalive=10)
            client.loop_start()
            start_docker(
                app_name, "--network", "host",
                "-v", f"{options}:/data",
                "-e", f"SUPERVISOR_URL=http://127.0.0.1:{server.server_port}",
                "-e", "SUPERVISOR_TOKEN=ci-test-token",
                image
            )
            discovered = json.loads(inbox.wait(DISCOVERY))
            assert discovered["name"].endswith("(simulation)")
            assert discovered["availability_topic"] == PREFIX + "/availability"
            inbox.wait(PREFIX + "/availability", lambda x: x == "online")
            initial = json.loads(inbox.wait(PREFIX + "/state/runtime"))
            assert initial["controller"] == "monitor"
            assert initial["write_enabled"] is False
            assert initial["ebusd_bus_enabled"] is False
            assert initial["simulated_demand"] is False
            top = run("docker", "top", app_name).stdout
            assert "run_ebusd.py" in top and "/opt/vaillant/main.py" in top, top
            assert "/opt/vaillant/web_server.py" in top, top
            # The HTTP server runs in this disposable host-network test, but
            # refuses direct access (only actual HA Supervisor ingress may pass).
            await_tcp(8099)
            from urllib.request import urlopen
            from urllib.error import HTTPError
            try:
                urlopen("http://127.0.0.1:8099/api/v1/status", timeout=3)
                raise AssertionError("Direct non-Ingress request must be forbidden")
            except HTTPError as error:
                assert error.code == 403

            # MQTT command and timestamps -> simulation, never boiler command.
            publish(client, "control/climate/mode/set", "heat")
            publish(client, "control/climate/temperature/set", "21.5")
            publish(client, "input/room", fresh_sensor(18.2))
            publish(client, "input/outdoor", fresh_sensor(6.0))
            runtime = json.loads(inbox.wait(PREFIX + "/state/runtime",
                lambda x: json.loads(x).get("simulated_demand") is True))
            assert runtime["write_enabled"] is False
            flow = float(inbox.wait(PREFIX + "/state/heatcurve/desired_flow_c",
                                    lambda x: x != ""))
            assert 30 <= flow <= 65
            assert inbox.wait(PREFIX + "/state/climate/action", lambda x: x == "off") == "off"
            inbox.wait(PREFIX + "/state/climate/temperature", lambda x: x == "21.5")

            # An old sensor reading must not replace the valid current reading.
            publish(client, "input/room", json.dumps({
                "value_c": 5, "observed_at": "2020-01-01T00:00:00Z", "source": "sensor.ci"
            }))
            # Preserve state across app restart, reject a broker-retained command.
            run("docker", "stop", "-t", "2", app_name, timeout=20)
            publish(client, "control/climate/mode/set", "off", retain=True)
            before_restart = inbox.size()
            run("docker", "start", app_name)
            inbox.wait(PREFIX + "/availability", lambda x: x == "online", since=before_restart)
            inbox.wait(PREFIX + "/state/climate/mode", lambda x: x == "heat", since=before_restart)
            inbox.wait(PREFIX + "/state/climate/temperature", lambda x: x == "21.5", since=before_restart)
            # MQTT retained mode=off should be ignored on re-subscription.
            # Input readings are deliberately NOT persisted; following a restart
            # the controller must NOT reuse a previously valid room/outdoor sensor.
            stale = json.loads(inbox.wait(PREFIX + "/state/runtime",
                lambda x: json.loads(x).get("reason") == "sensor-missing-or-stale",
                since=before_restart))
            assert stale["simulated_demand"] is False and stale["write_enabled"] is False
            publish(client, "input/room", fresh_sensor(18.2))
            publish(client, "input/outdoor", fresh_sensor(6.0))
            assert json.loads(inbox.wait(PREFIX + "/state/runtime",
                lambda x: json.loads(x).get("simulated_demand") is True,
                since=before_restart))["write_enabled"] is False

            # Reannounce MQTT discovery when Home Assistant Core comes back.
            before_birth = inbox.size()
            result = client.publish("homeassistant/status", "online", qos=1, retain=False)
            result.wait_for_publish(timeout=8)
            inbox.wait(DISCOVERY, since=before_birth)

            # Live broker outage/restart -> app reconnects and republishes discovery.
            before_broker = inbox.size()
            run("docker", "restart", "-t", "1", broker_name, timeout=35)
            await_tcp(1883)
            renewed = json.loads(inbox.wait(DISCOVERY, since=before_broker, timeout=60))
            assert renewed["name"].endswith("(simulation)")
            inbox.wait(PREFIX + "/availability", lambda x: x == "online",
                       since=before_broker, timeout=60)

            # Fault injection: kill only the Python controller (NOT the container
            # and NOT ebusd). s6 must supervise it back into service.
            controller_command = r"""
import os, signal
needle = "/opt/vaillant/" + "main.py"
matches = []
for entry in os.scandir("/proc"):
    if not entry.name.isdecimal():
        continue
    try:
        with open(f"/proc/{entry.name}/cmdline", "rb") as stream:
            command = stream.read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        continue
    if needle in command and "python" in command:
        matches.append(int(entry.name))
if len(matches) != 1:
    raise SystemExit(f"Expected one controller, found {matches}")
os.kill(matches[0], signal.SIGKILL)
"""
            before_crash = inbox.size()
            run("docker", "exec", app_name, "/usr/bin/python3", "-c",
                controller_command, timeout=15)
            inbox.wait(PREFIX + "/availability", lambda x: x == "online",
                       since=before_crash, timeout=40)
            # On restart stored intent is restored, but sensor readings must
            # be provided again before demand is computed (fail-closed).
            inbox.wait(PREFIX + "/state/runtime",
                lambda x: json.loads(x).get("reason") == "sensor-missing-or-stale",
                since=before_crash, timeout=40)
            assert "run_ebusd.py" in run("docker", "top", app_name).stdout

            print("PASS: three s6 services, Ingress-only HTTP, MQTT discovery, simulated heat, retained command rejection,")
            print("      state persistence, broker restart, controller crash recovery, monitor-only")
        except Exception:
            # Print recent container output on failure before removing containers.
            # The mock broker has no real credentials; the add-on never logs its
            # Supervisor token or MQTT password.
            for name in (app_name, broker_name):
                diagnostic = run("docker", "logs", "--tail", "100", name,
                                 check=False, timeout=20)
                print(f"DIAGNOSTICS for {name}:\n{diagnostic.stdout}\n{diagnostic.stderr}",
                      flush=True)
            raise
        finally:
            try:
                client.disconnect()
                client.loop_stop()
            except Exception:
                pass
            for name in (app_name, broker_name):
                run("docker", "rm", "-f", name, check=False, timeout=20)
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="vaillant-ebus-control:ci")
    args = parser.parse_args()
    exercise(args.image)
