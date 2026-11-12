from datetime import datetime, timedelta, timezone
import json
import pytest
from vaillant_control.mqtt_api import parse_mode, parse_setpoint, parse_room_or_outdoor, discovery, topic


def test_setpoint_valid_and_invalid():
    assert parse_setpoint("20.75") == 20.8
    for bad in ("NaN", "Infinity", "-10", "31", "garbage"):
        with pytest.raises(ValueError): parse_setpoint(bad)


def test_mode_only_heat_or_off():
    assert parse_mode("heat") == "heat"
    with pytest.raises(ValueError): parse_mode("auto")


def test_sensor_contract_and_timestamp():
    s = parse_room_or_outdoor('{"value_c":20.5,"observed_at":"2026-10-30T12:00:00Z","source":"sensor.room"}', "room")
    assert s.value_c == 20.5 and s.observed_at.tzinfo is not None


def test_sensor_rejects_invalid():
    for bad in ("not-json", "{}", '{"value_c": -60.44, "observed_at":"2026-10-30T12:00:00Z","source":"cutoff"}',
                '{"value_c": true, "observed_at":"2026-10-30T12:00:00Z","source":"test"}',
                '{"value_c":20,"observed_at":"2026-10-30T12:00:00","source":"test"}'):
        with pytest.raises(ValueError): parse_room_or_outdoor(bad, "room")


def test_discovery_is_versioned_and_conservative():
    d = discovery()
    assert d["mode_command_topic"] == topic("control/climate/mode/set")
    assert d["availability_topic"] == topic("availability")
    assert d["optimistic"] is False
    assert d["name"].endswith("simulation)")

def test_sensor_quality_must_be_ok():
    with pytest.raises(ValueError):
        parse_room_or_outdoor(json.dumps({
            "value_c": 20.0,
            "observed_at": "2026-10-30T12:00:00Z",
            "source": "sensor.unavailable",
            "quality": "error"
        }), "room")
