"""Read-only HA Ingress WebUI bridge.

Security boundary:
* Home Assistant authenticates Ingress and forwards from Supervisor 172.30.32.2.
* Only that peer is accepted in production; no port is published on the host.
* MQTT credentials stay server-side; only allowlisted state/BAI topics are exposed.
* No MQTT publish, shell, subprocess, scan, SetMode or eBUS write endpoint.
* Cached BAI data is explicitly NOT treated as a fresh physical measurement.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit

from vaillant_control.ebusd_client import ALLOWED, request as read_cached
from vaillant_control.settings import load_settings
from vaillant_control.supervisor import mqtt_broker
from vaillant_control.telemetry import NAME_BY_REGISTER, decode

LOG = logging.getLogger("vaillant-webui")
WEB_ROOT = Path(__file__).resolve().parent / "webui"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/curve_simulator.js": ("curve_simulator.js", "text/javascript; charset=utf-8"),
    "/mqtt_viewer.js": ("mqtt_viewer.js", "text/javascript; charset=utf-8"),
    "/live_adapter.js": ("live_adapter.js", "text/javascript; charset=utf-8"),
}
INGRESS_PEERS = frozenset({"172.30.32.2"})
MAX_MESSAGES = 200
MAX_EVENTS = 80
MAX_PAYLOAD = 8192
PREFIX = "vaillant_ebus/v1/"
STATE_SUFFIXES = frozenset({
    "availability", "state/runtime", "state/boiler/telemetry",
    "state/boiler/diagnostics", "state/climate/temperature",
    "state/climate/mode", "state/climate/current_temperature",
    "state/climate/action", "state/weather/outdoor",
    "state/heatcurve/desired_flow_c",
})


def allowed_topic(path: str) -> bool:
    if not isinstance(path, str):
        return False
    if path.startswith(PREFIX):
        return path[len(PREFIX):] in STATE_SUFFIXES
    if path.startswith("ebusd/bai/"):
        return path[len("ebusd/bai/"):] in ALLOWED
    return False


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReadOnlyState:
    def __init__(self, bus_enabled: bool = False):
        self.bus_enabled = bus_enabled
        self.connected = False
        self.condition = threading.Condition()
        self.messages = deque(maxlen=MAX_MESSAGES)
        self.events = deque(maxlen=MAX_EVENTS)
        self.sequence = 0
        self.runtime = None
        self.telemetry = None
        self.availability = "unknown"
        self.last_message_at = None

    def set_connected(self, connected: bool):
        with self.condition:
            self.connected = bool(connected)
            self.condition.notify_all()

    def ingest(self, path: str, payload: bytes, qos: int = 0, retained: bool = False):
        if not allowed_topic(path):
            return False
        # Never decode or store arbitrary household MQTT payloads.
        text = payload[:MAX_PAYLOAD].decode("utf-8", errors="replace")
        stamp = timestamp()  # received timestamp; NOT source bus observation time
        with self.condition:
            self.sequence += 1
            self.messages.append({
                "id": self.sequence, "topic": path, "payload": text,
                "qos": int(qos), "retained": bool(retained), "timestamp": stamp,
                "truncated": len(payload) > MAX_PAYLOAD,
            })
            self.last_message_at = stamp
            suffix = path[len(PREFIX):] if path.startswith(PREFIX) else ""
            if suffix == "availability":
                self.availability = text if text in ("online", "offline") else "unknown"
            if suffix in ("state/runtime", "state/boiler/telemetry"):
                try:
                    data = json.loads(text) if len(payload) <= MAX_PAYLOAD else None
                except (ValueError, TypeError):
                    data = None
                if not isinstance(data, dict):
                    data = None
                if suffix == "state/runtime":
                    self.runtime = data
                else:
                    self.telemetry = data
            self.events.append({
                "id": self.sequence, "timestamp": stamp,
                "type": "mqtt-received", "topic": path,
                "description": "Read-only status ontvangen",
            })
            self.condition.notify_all()
        return True

    def snapshot(self, after: int = 0) -> dict:
        with self.condition:
            return {
                "connected": self.connected,
                "source": "mqtt-read-only",
                "last_received_at": self.last_message_at,
                "latest_id": self.sequence,
                "messages": [dict(msg) for msg in self.messages if msg["id"] > after],
            }

    def status(self) -> dict:
        with self.condition:
            return {
                "mode": "monitor-only", "write_enabled": False,
                "mqtt_connected": self.connected,
                "boiler_bus_enabled": self.bus_enabled,
                "boiler_measurement_freshness_verified": False,
                "controller_availability": self.availability,
                "last_received_at": self.last_message_at,
                "runtime": self.runtime,
                "telemetry": self.telemetry,
            }

    def recent_events(self) -> dict:
        with self.condition:
            return {"events": list(self.events), "source": "mqtt-read-only"}


def terminal_command(command: str, state: ReadOnlyState, reader=read_cached) -> dict:
    """Exact allowlist. The only wire-facing command reads the passive ebusd cache."""
    if not isinstance(command, str) or len(command) > 80:
        raise ValueError("Ongeldig commando")
    cmd = command.strip()
    if cmd == "help":
        return {
            "command": cmd, "kind": "help",
            "output": "Toegestaan: help, info, state, read -c bai REGISTER. Alleen vooraf toegestane BAI-cacheregisters. Geen shell, writes, scans of -f.",
        }
    if cmd == "info":
        snap = state.status()
        return {
            "command": cmd, "kind": "status",
            "output": "WebUI bridge: monitor-only; MQTT: " +
                      ("verbonden" if snap["mqtt_connected"] else "niet verbonden") +
                      "; eBUS-cache: " + ("ingeschakeld" if state.bus_enabled else "uitgeschakeld") +
                      ". Geen brander- of pompcommando's.",
        }
    if cmd == "state":
        snap = state.status()
        return {
            "command": cmd, "kind": "status",
            "output": "Controller availability: " + snap["controller_availability"] +
                      "; werkelijke ketelactie niet bevestigd; telemetrieversheid onbekend.",
        }
    parts = cmd.split(" ")
    if len(parts) != 4 or parts[:3] != ["read", "-c", "bai"] or parts[3] not in ALLOWED:
        raise ValueError("Commando geweigerd: uitsluitend read -c bai [toegestaan register]")
    if not state.bus_enabled:
        return {"command": cmd, "kind": "unavailable",
                "output": "eBUS uitgeschakeld. Geen cache-uitlezing uitgevoerd."}
    field = NAME_BY_REGISTER[parts[3]]
    try:
        raw = reader(parts[3])
        value = decode(field, raw)
    except (OSError, ValueError, TypeError, UnicodeError, TimeoutError):
        return {"command": cmd, "kind": "unavailable",
                "output": "Geen geldige cachewaarde beschikbaar; geen eBUS-telegram verstuurd."}
    return {
        "command": cmd, "kind": "cache_unverified",
        "output": str(value) + (" " + field.unit if field.unit else "") +
                  " (ebusd-cache; fysieke meettijd onbekend, niet als live waarde gebruiken)",
        "value": value, "unit": field.unit, "freshness_verified": False,
    }


class IngressHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: ReadOnlyState
    trusted_peers = INGRESS_PEERS
    root = WEB_ROOT
    terminal_reader = staticmethod(read_cached)
    active_streams = threading.BoundedSemaphore(4)

    def log_message(self, fmt, *args):
        LOG.debug("%s %s", self.client_address[0], fmt % args)

    def _headers(self, status, kind, size=None):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; connect-src 'self'; script-src 'self'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "object-src 'none'; base-uri 'self'; form-action 'none'")
        if size is not None:
            self.send_header("Content-Length", str(size))
        self.end_headers()

    def _json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def do_POST(self):
        if self.client_address[0] not in self.trusted_peers:
            self._json({"error": "Ingress-only access"}, 403)
        else:
            self._json({"error": "Read-only; POST not supported"}, 405)

    def do_GET(self):
        if self.client_address[0] not in self.trusted_peers:
            return self._json({"error": "Ingress-only access"}, 403)
        parsed = urlsplit(self.path)
        path = parsed.path
        if path in STATIC:
            name, mime = STATIC[path]
            body = (self.root / name).read_bytes()
            self._headers(200, mime, len(body))
            self.wfile.write(body)
            return
        if path == "/api/v1/status":
            return self._json(self.state.status())
        if path == "/api/v1/diagnostics":
            return self._json({
                "source": "ebusd-cache", "freshness_verified": False,
                "telemetry": self.state.status()["telemetry"],
            })
        if path == "/api/v1/events":
            return self._json(self.state.recent_events())
        if path == "/api/v1/mqtt":
            value = parse_qs(parsed.query).get("after", ["0"])[0]
            if not value.isdecimal() or len(value) > 15:
                return self._json({"error": "Invalid after index"}, 400)
            return self._json(self.state.snapshot(int(value)))
        if path == "/api/v1/terminal":
            values = parse_qs(parsed.query).get("command", [])
            if len(values) != 1:
                return self._json({"error": "One read-only command required"}, 400)
            try:
                return self._json(terminal_command(values[0], self.state, self.terminal_reader))
            except ValueError:
                return self._json({"error": "Command not allowed"}, 400)
        if path == "/api/v1/mqtt/stream":
            value = parse_qs(parsed.query).get("after", ["0"])[0]
            if not value.isdecimal() or len(value) > 15:
                return self._json({"error": "Invalid after index"}, 400)
            header_index = self.headers.get("Last-Event-ID", "")
            if header_index.isdecimal() and len(header_index) <= 15:
                value = str(max(int(value), int(header_index)))
            return self._stream(int(value))
        return self._json({"error": "Not found"}, 404)

    def _stream(self, since):
        if not self.active_streams.acquire(blocking=False):
            return self._json({"error": "Too many streams"}, 429)
        try:
            self._headers(200, "text/event-stream; charset=utf-8")
            self.wfile.write(b": read-only MQTT notifications\n\n")
            self.wfile.flush()
            until = time.monotonic() + 25
            while time.monotonic() < until:
                snap = self.state.snapshot(since)
                for msg in snap["messages"]:
                    data = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
                    self.wfile.write(("id: " + str(msg["id"]) + "\ndata: " + data + "\n\n").encode("utf-8"))
                    since = msg["id"]
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                with self.state.condition:
                    self.state.condition.wait(timeout=2)
        except (ConnectionError, BrokenPipeError, TimeoutError, OSError):
            pass
        finally:
            self.close_connection = True
            self.active_streams.release()


def make_server(state: ReadOnlyState, address=("0.0.0.0", 8099),
                trusted_peers=INGRESS_PEERS, root=WEB_ROOT,
                reader=read_cached):
    """Test injection of trusted peers is NOT used in production startup."""
    handler = type("ReadOnlyIngress", (IngressHandler,), {
        "state": state, "trusted_peers": frozenset(trusted_peers),
        "root": Path(root), "terminal_reader": staticmethod(reader),
        "active_streams": threading.BoundedSemaphore(4),
    })
    return ThreadingHTTPServer(address, handler)


def attach_mqtt(state: ReadOnlyState, stop: threading.Event):
    """MQTT observer is separate from the monitor controller; never publishes."""
    import paho.mqtt.client as mqtt
    while not stop.is_set():
        client = None
        try:
            broker = mqtt_broker()
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                 client_id="vaillant-webui-readonly", protocol=mqtt.MQTTv311)
            if broker.username:
                client.username_pw_set(broker.username, broker.password)
            if broker.ssl:
                client.tls_set()
            client.reconnect_delay_set(min_delay=1, max_delay=30)

            def on_connect(cli, userdata, flags, reason, properties):
                ok = not reason.is_failure
                state.set_connected(ok)
                if ok:
                    # No climate command / raw publish / arbitrary household topics.
                    for name in ("vaillant_ebus/v1/state/#",
                                 "vaillant_ebus/v1/availability", "ebusd/bai/+"):
                        cli.subscribe(name, qos=0)

            def on_disconnect(cli, userdata, flags, reason, properties):
                state.set_connected(False)

            def on_message(cli, userdata, msg):
                state.ingest(msg.topic, msg.payload, msg.qos, msg.retain)

            client.on_connect = on_connect
            client.on_disconnect = on_disconnect
            client.on_message = on_message
            client.connect_async(broker.host, broker.port, keepalive=45)
            client.loop_start()
            # Paho owns automatic reconnect after broker or network failure.
            while not stop.wait(2):
                pass
        except (OSError, ValueError, RuntimeError) as exc:
            LOG.warning("MQTT viewer disconnected: %s", type(exc).__name__)
            stop.wait(10)
        finally:
            state.set_connected(False)
            if client:
                try:
                    client.disconnect()
                    client.loop_stop()
                except (OSError, RuntimeError):
                    pass


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    state = ReadOnlyState(bus_enabled=settings.enable_bus)
    stop = threading.Event()
    thread = threading.Thread(target=attach_mqtt, args=(state, stop), daemon=True)
    thread.start()
    # Production access ALWAYS restricted to HA Supervisor ingress proxy.
    with make_server(state) as server:
        LOG.warning("WebUI Ingress monitor-only on 8099; no eBUS or shell writes")
        try:
            server.serve_forever(poll_interval=0.4)
        finally:
            stop.set()
            thread.join(timeout=3)


if __name__ == "__main__":
    main()
