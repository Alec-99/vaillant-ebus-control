from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import json
from vaillant_control.settings import Settings
from vaillant_control.mqtt_api import topic
from main import ControllerService


def test_controller_accepts_commands_without_ebus(tmp_path):
    app = ControllerService(Settings(), tmp_path / "state.json")
    app.mqtt = MagicMock()
    assert app.handle(topic("control/climate/temperature/set"), "21.5")
    assert app.handle(topic("control/climate/mode/set"), "heat")
    app.publish_snapshot()
    results = {call.args[0]:call.args[1] for call in app.mqtt.publish.call_args_list}
    assert results[topic("state/climate/mode")] == "heat"
    assert results[topic("state/climate/action")] == "off"  # truly monitor-only
    assert json.loads(results[topic("state/runtime")])["write_enabled"] is False
    assert json.loads(results[topic("state/runtime")])["simulated_demand"] is False  # no sensors


def test_reject_retained_command(tmp_path):
    app = ControllerService(Settings(), tmp_path / "state.json")
    assert not app.handle(topic("control/climate/mode/set"), "heat", retained=True)
    assert app.mode == "off"


def test_reject_stale_sensor(tmp_path):
    app = ControllerService(Settings(), tmp_path / "state.json")
    assert not app.handle(topic("input/room"), json.dumps({"value_c":20,"observed_at":"2020-01-01T00:00:00Z","source":"test"}))


def test_unknown_topic_not_accepted(tmp_path):
    app = ControllerService(Settings(), tmp_path / "state.json")
    assert not app.handle(topic("raw/ebus/write"), "deadbeef")


def test_readonly_client_allowlist():
    from vaillant_control.ebusd_client import request, safe_value
    import pytest
    with pytest.raises(ValueError): request("SetMode")
    assert safe_value("FlowTemp", "34.06;ok") == "34.06"
    assert safe_value("ReturnTemp", "-60.44;cutoff") is None
    assert safe_value("WP", "ERR: not found") is None


def test_ebusd_launcher_off_by_default():
    from run_ebusd import build_args
    assert build_args(Settings(), None) is None
    s = Settings.from_mapping({"enable_bus":True, "network_device":"enh:192.0.2.128:9999"})
    args = build_args(s, None)
    assert "--readonly" in args
    assert all("SetMode" not in arg and "--accesslevel=*" not in arg for arg in args)


def test_stale_temperature_state_clears_retained_mqtt_value(tmp_path):
    from datetime import datetime, timezone, timedelta
    from vaillant_control.algorithm import Reading
    from vaillant_control.mqtt_api import topic
    app = ControllerService(Settings(), tmp_path / "state.json")
    app.mqtt = MagicMock()
    app.room = Reading(22.0, datetime.now(timezone.utc) - timedelta(hours=1), "test")
    app.outdoor = Reading(5.0, datetime.now(timezone.utc) - timedelta(hours=1), "test")
    app.publish_snapshot()
    results = {call.args[0]: call for call in app.mqtt.publish.call_args_list}
    assert results[topic("state/climate/current_temperature")].args[1] == ""
    assert results[topic("state/weather/outdoor")].args[1] == ""
    assert results[topic("state/climate/current_temperature")].kwargs["retain"] is True
