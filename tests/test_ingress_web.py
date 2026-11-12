"""Batch 3: Ingress-only, read-only API and MQTT bridge regressions."""
from contextlib import contextmanager
from http.client import HTTPConnection
import json
from pathlib import Path
import threading
from urllib.parse import quote

import pytest

from web_server import (INGRESS_PEERS, MAX_EVENTS, MAX_MESSAGES, ReadOnlyState,
                        allowed_topic, make_server, terminal_command)

WEB_ROOT = Path(__file__).resolve().parents[1]/"addons/vaillant-ebus-control/webui"


@contextmanager
def started_server(state=None, *, allowed=("127.0.0.1",), reader=None):
    state = state or ReadOnlyState()
    kwargs = {"trusted_peers": allowed, "root": WEB_ROOT}
    if reader is not None:
        kwargs["reader"] = reader
    server = make_server(state, ("127.0.0.1", 0), **kwargs)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def get(port, url, method="GET"):
    client = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        client.request(method, url)
        response = client.getresponse()
        data = response.read()
        return response.status, response.headers, data
    finally:
        client.close()


def test_production_ingress_peer_restriction_and_no_cors():
    assert INGRESS_PEERS == frozenset({"172.30.32.2"})
    with started_server(allowed=INGRESS_PEERS) as port:
        for path in ("/", "/index.html", "/api/v1/status", "/api/v1/terminal?command=help"):
            code, headers, body = get(port, path)
            assert code == 403, (path, body)
        code, headers, body = get(port, "/api/v1/terminal", method="POST")
        assert code == 403
        assert headers.get("Access-Control-Allow-Origin") is None


def test_explicit_proxy_allowlist_allows_only_read_routes_and_static_files():
    with started_server() as port:
        code, headers, data = get(port, "/")
        assert code == 200
        assert b'live_adapter.js' in data
        assert "Content-Security-Policy" in headers
        assert "no-store" in headers.get("Cache-Control", "")
        assert headers.get("X-Content-Type-Options") == "nosniff"
        for path in ("/app.js", "/styles.css", "/curve_simulator.js",
                     "/mqtt_viewer.js", "/live_adapter.js"):
            assert get(port, path)[0] == 200
        for path in ("/../data/options.json", "/%2e%2e/data/options.json",
                     "/.git/config", "/web_server.py", "/api/v1/raw/write"):
            assert get(port, path)[0] == 404
        code, headers, data = get(port, "/api/v1/status", method="POST")
        assert code == 405
        assert json.loads(data)["error"].startswith("Read-only")


def test_bounded_allowlist_does_not_leak_credentials_commands_or_other_topics():
    assert allowed_topic("vaillant_ebus/v1/state/boiler/telemetry")
    assert allowed_topic("vaillant_ebus/v1/state/runtime")
    assert allowed_topic("vaillant_ebus/v1/availability")
    assert allowed_topic("ebusd/bai/FlowTemp")
    for path in ("vaillant_ebus/v1/control/climate/mode/set",
                 "vaillant_ebus/v1/input/room", "vaillant_ebus/v1/state/secrets",
                 "ebusd/bai/SetMode", "ebusd/global/password",
                 "homeassistant/status", "household/sensors/child", "test/bad"):
        assert not allowed_topic(path)
    state = ReadOnlyState()
    assert not state.ingest("household/secret", b"password=secret")
    assert state.snapshot()["messages"] == []
    state.ingest("vaillant_ebus/v1/state/runtime", b'{"controller":"monitor","write_enabled":false}')
    state.ingest("vaillant_ebus/v1/availability", b"online", 1, True)
    assert state.status()["runtime"]["write_enabled"] is False
    assert state.status()["controller_availability"] == "online"
    assert state.snapshot()["messages"][1]["retained"] is True


def test_mqtt_records_bounded_and_receipt_not_physical_timestamp():
    state = ReadOnlyState()
    for i in range(250):
        assert state.ingest("ebusd/bai/FlowTemp", str(i).encode(), qos=0)
    snap = state.snapshot()
    assert snap["latest_id"] == 250
    assert len(snap["messages"]) == MAX_MESSAGES
    assert len(state.recent_events()["events"]) == MAX_EVENTS
    assert len(state.snapshot(after=249)["messages"]) == 1
    assert "timestamp" in snap["messages"][0]
    assert "observed_at" not in snap["messages"][0]
    assert state.status()["boiler_measurement_freshness_verified"] is False
    huge = b"X" * 9000
    state.ingest("ebusd/bai/ReturnTemp", huge)
    last = state.snapshot(after=250)["messages"][-1]
    assert last["truncated"] is True
    assert len(last["payload"]) == 8192


def test_rest_status_diagnostics_and_mqtt_are_not_published_as_live_physical():
    state = ReadOnlyState(bus_enabled=False)
    state.set_connected(True)
    state.ingest("vaillant_ebus/v1/state/boiler/telemetry",
                 json.dumps({"data_freshness_verified":False,"measurements":{
                   "return_actual_c":{"value":34.0,"quality":"cache_unverified",
                                      "freshness_verified":False}}}).encode())
    with started_server(state) as port:
        code, _, data = get(port, "/api/v1/status")
        assert code == 200
        status = json.loads(data)
        assert status["mqtt_connected"] is True
        assert status["write_enabled"] is False
        assert status["boiler_bus_enabled"] is False
        assert status["telemetry"]["measurements"]["return_actual_c"]["quality"] == "cache_unverified"
        assert status["boiler_measurement_freshness_verified"] is False
        code, _, data = get(port, "/api/v1/diagnostics")
        assert code == 200 and json.loads(data)["freshness_verified"] is False
        code, _, data = get(port, "/api/v1/events")
        assert code == 200 and len(json.loads(data)["events"]) == 1
        code, _, data = get(port, "/api/v1/mqtt?after=0")
        assert code == 200
        assert json.loads(data)["messages"][0]["topic"].endswith("state/boiler/telemetry")
        assert get(port, "/api/v1/mqtt?after=-1")[0] == 400
        assert get(port, "/api/v1/mqtt/stream?after=nan")[0] == 400


def test_terminal_rejects_unsafe_commands_and_does_not_read_when_bus_disabled():
    state = ReadOnlyState(bus_enabled=False)
    def forbidden(_):
        pytest.fail("No socket call allowed without bus")
    with started_server(state, reader=forbidden) as port:
        for bad in ("read -c bai SetMode", "read -f bai FlowTemp",
                    "write -c bai SetMode on", "read -c bai FlowTemp;id",
                    "read -c bai FlowTemp\nwrite", "ls -al", "/bin/sh", "read -c bai ReturnTemp --force"):
            path = "/api/v1/terminal?command=" + quote(bad, safe="")
            code, _, data = get(port, path)
            assert code == 400, (bad, data)
        code, _, data = get(port, "/api/v1/terminal?command=read%20-c%20bai%20FlowTemp")
        assert code == 200 and json.loads(data)["kind"] == "unavailable"
        for cmd in ("help", "info", "state"):
            assert get(port, "/api/v1/terminal?command=" + cmd)[0] == 200
        assert get(port, "/api/v1/terminal?command=")[0] == 400
        assert get(port, "/api/v1/terminal?command=help&command=state")[0] == 400


def test_terminal_reads_only_approved_cached_register_and_labels_quality():
    seen = []
    def fake_reader(register):
        seen.append(register)
        return "31.50;65000;ok" if register == "ReturnTemp" else "ERR: not cached"
    state = ReadOnlyState(bus_enabled=True)
    with started_server(state, reader=fake_reader) as port:
        code, _, data = get(port, "/api/v1/terminal?command=read%20-c%20bai%20ReturnTemp")
        item = json.loads(data)
        assert code == 200
        assert item["kind"] == "cache_unverified"
        assert item["value"] == 31.5
        assert item["freshness_verified"] is False
        assert seen == ["ReturnTemp"]
        assert "65000" not in item["output"]
        code, _, data = get(port, "/api/v1/terminal?command=read%20-c%20bai%20FlowTemp")
        assert json.loads(data)["kind"] == "unavailable"


def test_sse_stream_reports_only_allowlisted_messages():
    state = ReadOnlyState(bus_enabled=False)
    state.ingest("ebusd/bai/FlowTemp", b"36.25;ok")
    with started_server(state) as port:
        client = HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            client.request("GET", "/api/v1/mqtt/stream?after=0")
            response = client.getresponse()
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/event-stream")
            lines = [response.fp.readline().decode("utf8") for _ in range(4)]
            assert any("id: 1" in line for line in lines)
            assert any('"topic":"ebusd/bai/FlowTemp"' in line for line in lines)
        finally:
            client.close()
