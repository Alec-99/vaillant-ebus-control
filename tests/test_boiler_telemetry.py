"""Batch 2: read-only BAI telemetry decoding and safe MQTT publication."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import json

import pytest

from main import ControllerService
from vaillant_control.ebusd_client import ALLOWED, safe_value
from vaillant_control.mqtt_api import topic
from vaillant_control.settings import Settings
from vaillant_control.telemetry import FIELDS, capture, decode, legacy_values


NOW = datetime(2026, 10, 31, 20, 0, tzinfo=timezone.utc)


def sample_reader(register):
    return {
        "FlowTemp": "36.25;ok",
        "ReturnTemp": "31.50;65000;ok",  # mirror is NOT another temperature
        "FlowTempDesired": "39.00;ok",
        "Flame": "on;ok",
        "WP": "yes;ok",
        "Statenumber": "7;ok",
        "ModulationDesired": "32.0;ok",
        "RemainingBoilerblocktime": "12;ok",
    }[register]


def test_cache_snapshot_types_and_no_false_freshness_claims():
    called = []
    def read(register):
        called.append(register)
        return sample_reader(register)
    report = capture(bus_enabled=True, reader=read, now=NOW)
    fields = report["measurements"]
    assert report["schema_version"] == 1
    assert report["kind"] == "read_only_bai_cache"
    assert report["data_freshness_verified"] is False
    assert set(called) == {field.register for field in FIELDS}
    assert set(called) <= ALLOWED
    assert all(value["quality"] == "cache_unverified" for value in fields.values())
    assert all(value["freshness_verified"] is False and value["observed_at"] is None
               for value in fields.values())
    assert fields["flow_actual_c"]["value"] == pytest.approx(36.25)
    assert fields["return_actual_c"]["value"] == 31.5
    assert fields["return_actual_c"]["unit"] == "°C"
    assert fields["flow_target_c"]["value"] == 39.0
    assert fields["flame"]["value"] == "on"
    assert fields["pump"]["value"] == "on"
    assert fields["boiler_state"]["value"] == 7
    assert fields["modulation_desired_pct"]["value"] == 32.0
    assert fields["remaining_boiler_block_min"]["value"] == 12.0
    assert legacy_values(report)["ReturnTemp"] == "31.5"


def test_bus_disabled_never_calls_ebusd_or_invents_telemetry():
    def forbidden(_):
        raise AssertionError("bus reader called while enable_bus false")
    report = capture(bus_enabled=False, reader=forbidden, now=NOW)
    assert all(x["value"] is None and x["quality"] == "disabled"
               for x in report["measurements"].values())
    assert legacy_values(report) == {}


@pytest.mark.parametrize("register,raw", [
    ("FlowTemp", "-60.44;cutoff"),
    ("ReturnTemp", "31.50;cutoff"),
    ("FlowTempDesired", "NaN;ok"),
    ("FlowTemp", "Infinity;ok"),
    ("FlowTemp", "101;ok"),
    ("ReturnTemp", "65abc;ok"),
    ("Flame", "unknown;ok"),
    ("WP", "running;ok"),
    ("Statenumber", "12.4;ok"),
    ("ModulationDesired", "-5;ok"),
    ("ModulationDesired", "105;ok"),
    ("RemainingBoilerblocktime", "-1;ok"),
])
def test_bad_values_are_invalid_and_not_number_zero(register, raw):
    field = next(x for x in FIELDS if x.register == register)
    with pytest.raises(ValueError):
        decode(field, raw)
    report = capture(bus_enabled=True, reader=lambda key: raw if key == register else sample_reader(key), now=NOW)
    item = report["measurements"][field.name]
    assert item["value"] is None and item["quality"] == "invalid"


def test_missing_values_are_not_carried_forward_between_polls():
    healthy = capture(bus_enabled=True, reader=sample_reader, now=NOW)
    def absent(register):
        if register == "ReturnTemp":
            raise TimeoutError("ebusd socket timed out")
        return sample_reader(register)
    later = capture(bus_enabled=True, reader=absent, now=NOW)
    assert healthy["measurements"]["return_actual_c"]["value"] == 31.5
    item = later["measurements"]["return_actual_c"]
    assert item["value"] is None and item["quality"] == "unavailable"
    missing = capture(bus_enabled=True,
                      reader=lambda key: "-" if key == "ReturnTemp" else sample_reader(key), now=NOW)
    assert missing["measurements"]["return_actual_c"]["quality"] == "unavailable"
    no_cache = capture(bus_enabled=True,
                       reader=lambda key: "ERR: not found" if key == "FlowTemp" else sample_reader(key), now=NOW)
    assert no_cache["measurements"]["flow_actual_c"]["quality"] == "unavailable"
    assert later["measurements"]["flow_actual_c"]["quality"] == "cache_unverified"


def test_service_publishes_quality_snapshot_without_bus(monkeypatch, tmp_path):
    import main
    monkeypatch.setattr(main, "read_diagnostic", lambda _: pytest.fail("bus disabled"))
    service = ControllerService(Settings(), tmp_path/"intent.json")
    service.mqtt = MagicMock()
    service.publish_snapshot()
    sent = {call.args[0]: call for call in service.mqtt.publish.call_args_list}
    report = json.loads(sent[topic("state/boiler/telemetry")].args[1])
    assert report["bus_enabled"] is False
    assert all(x["quality"] == "disabled" for x in report["measurements"].values())
    assert sent[topic("state/boiler/telemetry")].kwargs["retain"] is True
    assert json.loads(sent[topic("state/boiler/diagnostics")].args[1]) == {}
    assert json.loads(sent[topic("state/runtime")].args[1])["write_enabled"] is False


def test_service_reads_only_allowlisted_cache_and_clears_invalid(monkeypatch, tmp_path):
    import main
    seen = []
    def reader(register):
        seen.append(register)
        return sample_reader(register) if register != "ReturnTemp" else "ERR: not cached"
    monkeypatch.setattr(main, "read_diagnostic", reader)
    enabled = Settings.from_mapping({
        "enable_bus": True, "network_device": "enh:192.0.2.128:9999",
    })
    service = ControllerService(enabled, tmp_path/"intent.json")
    service.mqtt = MagicMock()
    service.publish_snapshot()
    sent = {call.args[0]: call for call in service.mqtt.publish.call_args_list}
    snapshot = json.loads(sent[topic("state/boiler/telemetry")].args[1])
    assert set(seen) == ALLOWED
    assert snapshot["measurements"]["return_actual_c"]["value"] is None
    assert snapshot["measurements"]["return_actual_c"]["quality"] == "unavailable"
    assert snapshot["measurements"]["flame"]["value"] == "on"
    assert "ReturnTemp" not in json.loads(sent[topic("state/boiler/diagnostics")].args[1])
    assert sent[topic("state/boiler/diagnostics")].kwargs["retain"] is False
    assert sent[topic("state/climate/action")].args[1] == "off"


def test_diagnostic_socket_request_is_cache_only(monkeypatch):
    from vaillant_control import ebusd_client
    sent = []
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def settimeout(self, *_): pass
        def sendall(self, value): sent.append(value)
        def recv(self, _): return b"31.50;65000;ok\n"
    monkeypatch.setattr(ebusd_client.socket, "create_connection", lambda *_args, **_kwargs: Socket())
    assert ebusd_client.request("ReturnTemp") == "31.50;65000;ok"
    assert sent == [b"read -c bai ReturnTemp\n"]
    with pytest.raises(ValueError):
        ebusd_client.request("SetMode")
