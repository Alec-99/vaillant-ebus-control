from dataclasses import replace
import json
from pathlib import Path
import pytest
from vaillant_control.settings import Settings
from vaillant_control.storage import load, save


def test_default_disables_bus():
    assert Settings.from_mapping({}).enable_bus is False


def test_network_device_only_for_enabled_bus():
    assert Settings.from_mapping({"network_device":"enh:192.0.2.128:9999", "enable_bus":True}).enable_bus
    for raw in ({"enable_bus": True}, {"enable_bus": True, "network_device": "192.0.2.128:9999"},
                {"enable_bus": "false"}, {"scanconfig": "true"}):
        with pytest.raises(ValueError): Settings.from_mapping(raw)


def test_settings_rejects_unsafe_ranges_and_topic():
    for raw in ({"flow_min": 70, "flow_max": 65}, {"flow_max": float('nan')},
                {"mqtt_prefix": "ebus/raw"}, {"poll_interval": 3}):
        with pytest.raises(ValueError): Settings.from_mapping(raw)


def test_persistence_roundtrip(tmp_path: Path):
    p = tmp_path / "intent.json"
    assert load(p, 20) == ("off", 20)
    save(p, "heat", 21.0)
    assert load(p, 20) == ("heat", 21.0)
    p.write_text('{"mode":"invalid","target_c":9}', encoding="utf-8")
    assert load(p, 20) == ("off", 20)


def test_readonly_rejects_scanconfig_even_if_enabled():
    from vaillant_control.settings import Settings
    import pytest
    with pytest.raises(ValueError, match="scanconfig"):
        Settings.from_mapping({"enable_bus": True, "network_device": "enh:127.0.0.1:9999", "scanconfig": True})
