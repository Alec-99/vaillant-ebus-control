"""Structural regression checks for the frontend-only tabbed WebUI prototype."""
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "addons" / "vaillant-ebus-control" / "webui"
TABS = {"overview", "climate", "curve", "diagnostics", "events", "mqtt", "terminal", "settings"}


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tabs = set()
        self.panels = set()
        self.names = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            assert attributes["id"] not in self.names, f"Duplicate id: {attributes['id']}"
            self.names.add(attributes["id"])
        if attributes.get("role") == "tab":
            self.tabs.add(attributes.get("data-tab"))
        if attributes.get("role") == "tabpanel":
            self.panels.add(attributes.get("id"))


def test_eight_distinct_tab_panels():
    elements = Elements()
    elements.feed((WEB / "index.html").read_text(encoding="utf8"))
    assert elements.tabs == TABS
    assert elements.panels == {"panel-" + tab for tab in TABS}
    for tab in TABS:
        assert "tab-" + tab in elements.names


def test_all_assets_are_local_and_frontend_only():
    html = (WEB / "index.html").read_text(encoding="utf8")
    js = "\n".join((WEB / name).read_text(encoding="utf8") for name in ("curve_simulator.js", "app.js", "mqtt_viewer.js"))
    assert 'href="styles.css"' in html
    assert 'src="curve_simulator.js"' in html
    assert 'src="app.js"' in html
    assert 'src="mqtt_viewer.js"' in html
    html_without_svg_ns = html.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "https://" not in html_without_svg_ns and "http://" not in html_without_svg_ns
    for pattern in (r"\bfetch\s*\(", r"\bnew\s+WebSocket\s*\(", r"\bnew\s+XMLHttpRequest\s*\(",
                    r"\blocalStorage\.", r"\bsessionStorage\."):
        assert re.search(pattern, js) is None, f"Unexpected live browser I/O: {pattern}"
    assert "write_enabled: false" in js
    assert "bus_enabled: false" in js
    assert "simulated_demand" in js


def test_webui_now_packaged_for_ingress_without_public_port():
    if not (WEB.parent / "Dockerfile").exists():
        pytest.skip("Run in a full repository checkout to check the existing add-on Dockerfile")
    docker = (WEB.parent / "Dockerfile").read_text(encoding="utf8")
    config = (WEB.parent / "config.yaml").read_text(encoding="utf8")
    assert "COPY webui/ /opt/vaillant/webui/" in docker
    assert "ingress: true" in config
    assert "ingress_port: 8099" in config
    assert "panel_admin: true" in config
    assert "ports:" not in config


def test_javascript_syntax_when_node_available():
    node = shutil.which("node")
    if node:
        subprocess.run([node, "--check", str(WEB / "curve_simulator.js")], check=True, timeout=20)
        subprocess.run([node, "--check", str(WEB / "app.js")], check=True, timeout=20)
        subprocess.run([node, "--check", str(WEB / "mqtt_viewer.js")], check=True, timeout=20)


def test_terminal_is_demonstration_only():
    html = (WEB / "index.html").read_text(encoding="utf8")
    js = (WEB / "app.js").read_text(encoding="utf8")
    assert 'id="panel-terminal"' in html
    assert 'data-terminal-mode="ebusd"' in html
    assert 'data-terminal-mode="shell"' in html
    assert 'id="terminal-output"' in html
    assert 'id="terminal-form"' in html
    assert "NIET UITGEVOERD" in js
    assert "shell" in js and '$("terminal-input").disabled = locked' in js
    for token in ["child_process", "exec(", "spawn(", "new WebSocket(", "fetch("]:
        assert token not in js


def test_mqtt_debugger_ui_is_bounded_readonly_and_mock_only():
    html = (WEB / "index.html").read_text(encoding="utf8")
    js = (WEB / "mqtt_viewer.js").read_text(encoding="utf8")
    for identifier in ("panel-mqtt", "mqtt-tree", "mqtt-feed", "mqtt-detail-payload", "mqtt-filter", "mqtt-search", "mqtt-pause", "mqtt-clear"):
        assert 'id="' + identifier + '"' in html
    assert "MAX_MESSAGES = 200" in js
    assert "VIEW_LIMIT = 100" in js
    assert "textContent" in js
    assert "matches(topic, filter)" in js
    assert "validFilter(filter)" in js
    assert "vaillant_ebus/v1/" in js and "ebusd/bai/" in js
    for prohibited in ("new WebSocket(", "fetch(", "XMLHttpRequest(", "localStorage.", "sessionStorage.", "eval(", ".innerHTML", "mqtt.publish(", "mosquitto"):
        assert prohibited not in js



def test_compact_searchable_sensor_dropdowns_are_frontend_only():
    html = (WEB / "index.html").read_text(encoding="utf8")
    css = (WEB / "styles.css").read_text(encoding="utf8")
    js = (WEB / "app.js").read_text(encoding="utf8")
    for kind in ("room", "outdoor"):
        for suffix in ("trigger", "menu", "search", "options", "selected", "availability", "value"):
            assert f'id="sensor-{kind}-{suffix}"' in html
        assert f'id="sensor-{kind}-menu" hidden' in html
    assert "sensor-select-trigger" in css
    assert "position:absolute" in css and ".sensor-dropdown" in css
    assert 'placeholder="Zoek sensor..."' in html
    assert "Geavanceerde sensorinstellingen" in html
    assert 'role="listbox"' in html
    assert "DEMO_SENSORS" in js and "sensorChoice" in js
    assert "renderSensorOptions" in js and "closeSensorDropdown" in js
    assert "state[kind] = item.value" in js
    assert "document.createElement" in js and "textContent = item.label" in js
    assert "fetch(" not in js and "new WebSocket(" not in js


def test_curve_and_timeline_controls_exist():
    html = (WEB / "index.html").read_text(encoding="utf8")
    for item in ("curve-panel-static","curve-panel-sim","curve-chart","sim-chart","sim-play","sim-cursor","sim-scenario","sim-duration","curve-base-comp","sim-integral"):
        assert f'id="{item}"' in html
    assert 'data-curve-view="sim"' in html


def test_flow_gate_has_local_controls_and_no_bus_calls():
    html=(WEB/"index.html").read_text(encoding="utf8")
    js=(WEB/"curve_simulator.js").read_text(encoding="utf8")
    for name in ("return-gate-enabled","return-gate-on","return-gate-off","return-gate-error",
                 "return-gate-slider","return-gate-valid","return-gate-room","return-gate-target",
                 "return-gate-state","return-gate-reason","return-gate-warning","return-gate-reset"):
        assert f'id="{name}"' in html
    assert 'function returnGate(' in js
    assert 'roomDemand' in js and 'measuredReturn' in js and 'sensorValid' in js
    for prohibited in ("fetch(", "WebSocket(", "XMLHttpRequest(", "localStorage.", "sessionStorage."):
        assert prohibited not in js


def test_flow_hysteresis_is_integrated_in_simulation_panel():
    html=(WEB/"index.html").read_text(encoding="utf8")
    js=(WEB/"curve_simulator.js").read_text(encoding="utf8")
    sim=html.split('<div id="curve-panel-sim" hidden>',1)[1]
    assert sim.index('class="card return-gate-card"')<sim.index('id="sim-chart"')
    for ident in ("sim-measured-flow","sim-measured-return","sim-water-delta","sim-room-demand","sim-cycle-summary","return-gate-on","return-gate-off"):
        assert f'id="{ident}"' in sim
    assert 'simulate(readState(),scenario,hours,returnSettings,roomSettings,pumpSettings)' in js
    assert 'if(view==="sim")run(Number($("sim-cursor").value))' in js
    assert 'bands("roomDemand"' in js and 'bands("demand"' in js
    assert 'path("measuredFlow"' in js
    assert 'returnSegments(true,"sim-return-line")' in js
    assert 'returnSegments(false,"sim-return-stagnant-line")' in js


def test_room_temperature_controls_are_in_same_time_simulation():
    html=(WEB/"index.html").read_text(encoding="utf8")
    js=(WEB/"curve_simulator.js").read_text(encoding="utf8")
    panel=html.split('<div id="curve-panel-sim" hidden>',1)[1]
    for ident in ("sim-room-start","sim-room-target","sim-room-hysteresis",
                  "sim-room-reset","sim-room-settings-status"):
        assert f'id="{ident}"' in panel
    assert panel.index('id="sim-room-start"') < panel.index('id="sim-chart"')
    assert 'Number.isFinite(roomOptions.start)' in js
    assert 'Number.isFinite(roomOptions.target)' in js
    assert 'Number.isFinite(roomOptions.hysteresis)' in js
    assert 'initRoomInputs();' in js
    assert 'roomSettings.customStart' in js
    assert 'roomSettings.start=defaultRoomStart(' in js
    assert 'run(Number($("sim-cursor").value))' in js


def test_return_hysteresis_controls_are_not_flow_hysteresis():
    html=(WEB/"index.html").read_text(encoding="utf8")
    js=(WEB/"curve_simulator.js").read_text(encoding="utf8")
    sim=html.split('<div id="curve-panel-sim" hidden>',1)[1]
    assert "Retourhysterese" in sim
    assert 'id="return-gate-slider"' in sim
    assert 'id="return-gate-supply-slider"' in sim
    assert 'id="sim-measured-return"' in sim
    assert "returnGate(allowed" in js
    assert "measuredReturn:valid&&gate.valid!==false?measuredReturn:null" in js
    assert "returnSensorValid=valid&&pumpOn" in js
    assert "flowGate(" not in js
    assert "flow-gate-on" not in html


def test_pump_circulation_control_is_connected_to_timeline():
    html=(WEB/"index.html").read_text(encoding="utf8")
    js=(WEB/"curve_simulator.js").read_text(encoding="utf8")
    sim=html.split('<div id="curve-panel-sim" hidden>',1)[1]
    for element in ("sim-pump-mode","sim-pump-warning","sim-pump"):
        assert f'id="{element}"' in sim
    assert 'value="room"' in sim
    assert 'value="room-postrun"' in sim
    assert 'value="release"' in sim
    assert 'pumpSettings.mode=event.target.value' in js
    assert 'simulate(readState(),scenario,hours,returnSettings,roomSettings,pumpSettings)' in js
    assert 'bands("pumpOn",205,"sim-pump-band")' in js
    assert 'returnSensorValid=valid&&pumpOn' in js
    for forbidden in ("fetch(","WebSocket(","XMLHttpRequest(","localStorage."):
        assert forbidden not in js


def test_continuous_pump_button_controls_simulated_postrun():
    html=(WEB/"index.html").read_text(encoding="utf8")
    js=(WEB/"curve_simulator.js").read_text(encoding="utf8")
    css=(WEB/"styles.css").read_text(encoding="utf8")
    sim=html.split('<div id="curve-panel-sim" hidden>',1)[1]
    assert 'id="sim-pump-toggle"' in sim
    assert 'aria-pressed="true"' in sim
    assert '<option value="room-postrun" selected>' in sim
    assert 'id="sim-return-quality"' in sim
    assert "const pumpSettings={mode:\"room-postrun\"};" in js
    assert '$("sim-pump-toggle").addEventListener("click"' in js
    assert 'pumpSettings.mode=pumpSettings.mode==="room-postrun"?"room":"room-postrun";' in js
    assert 'button.setAttribute("aria-pressed",String(active));' in js
    assert 'if(view==="sim")run(Number($("sim-cursor").value))' in js
    assert 'returnSegments(false,"sim-return-stagnant-line")' in js
    assert "sim-return-stagnant-line" in css
    for forbidden in ("fetch(", "WebSocket(", "XMLHttpRequest(", "localStorage."):
        assert forbidden not in js


def test_batch2_diagnostic_page_keeps_live_data_separate_from_historical_demo():
    html=(WEB/"index.html").read_text(encoding="utf8")
    js=(WEB/"app.js").read_text(encoding="utf8")
    diagnostics=html.split('id="panel-diagnostics"',1)[1].split('id="panel-events"',1)[0]
    assert 'id="boiler-telemetry-contract"' in diagnostics
    assert "INGRESS GEKOPPELD" in diagnostics
    assert "cache_unverified" in diagnostics
    assert "state/boiler/telemetry" in diagnostics
    assert "ModulationDesired" in diagnostics
    assert "RemainingBoilerblocktime" in diagnostics
    assert "geen live metingen" in diagnostics.lower()
    assert "voorbeeld" in diagnostics.lower()
    # Batch 2 does not silently connect the prototype browser to Home Assistant.
    assert "fetch(" not in js
    assert "WebSocket(" not in js


def test_batch3_frontend_has_live_ingress_adapter_but_offline_mock_remains_isolated():
    html=(WEB/"index.html").read_text(encoding="utf8")
    live=(WEB/"live_adapter.js").read_text(encoding="utf8")
    app=(WEB/"app.js").read_text(encoding="utf8")
    mqtt=(WEB/"mqtt_viewer.js").read_text(encoding="utf8")
    assert '<script src="live_adapter.js" defer></script>' in html
    for node in ("live-mode-label","live-connection","live-flow_actual_c",
                 "live-return_actual_c","live-flame","live-pump",
                 "live-remaining_boiler_block_min","live-events",
                 "live-stream-status","mqtt-broker-connection"):
        assert f'id="{node}"' in html
    assert 'window.VaillantLive = {' in live
    assert 'new EventSource("api/v1/mqtt/stream?after="' in live
    assert 'fetch(path,' in live
    assert 'read -c bai (FlowTemp|ReturnTemp' in live
    assert 'window.VaillantMqttViewer = {setLive, setConnection, appendLive}' in mqtt
    assert 'window.VaillantLive.readCommand(text)' in app
    assert 'window.VaillantLive?.enabled' in app
    # Only this optional adapter performs authenticated same-origin browser IO.
    for offline in ("app.js","curve_simulator.js","mqtt_viewer.js"):
        code=(WEB/offline).read_text(encoding="utf8")
        assert "fetch(" not in code
        assert "new EventSource(" not in code
    for forbidden in ("mqtt.publish(", "eval(", "localStorage."):
        assert forbidden not in live
