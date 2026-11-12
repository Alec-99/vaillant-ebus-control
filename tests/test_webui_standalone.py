"""Standalone WebUI build must contain ALL current tabs and offline scripts."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


class CheckMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tabs = set()
        self.panels = set()
        self.external_scripts = []
        self.external_styles = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if data.get("role") == "tab":
            self.tabs.add(data.get("data-tab"))
        if data.get("role") == "tabpanel":
            self.panels.add(data.get("id"))
        if tag == "script" and data.get("src"):
            self.external_scripts.append(data["src"])
        if tag == "link" and data.get("rel") == "stylesheet":
            self.external_styles.append(data.get("href"))


def test_build_standalone_inlines_all_current_tabs(tmp_path):
    target = tmp_path / "vaillant-ebus-webui.html"
    subprocess.run([
        sys.executable, str(ROOT / "scripts/build_webui_standalone.py"),
        "--output", str(target)
    ], check=True, timeout=15)
    text = target.read_text(encoding="utf-8")
    parsed = CheckMarkup()
    parsed.feed(text)
    names = {"overview", "climate", "curve", "diagnostics",
             "events", "mqtt", "terminal", "settings"}
    assert parsed.tabs == names
    assert parsed.panels == {"panel-" + tab for tab in names}
    assert not parsed.external_scripts and not parsed.external_styles
    assert "curve_simulator.js" in text
    assert "mqtt_viewer.js" in text  # comment/banner is okay; JS is inlined
    assert "MAX_MESSAGES = 200" in text
    assert "function submitTerminalCommand" in text
    assert text.index("/* Offline visualization") < text.index("/* Vaillant eBUS Control") < text.index("/* Frontend-only MQTT Explorer mock")
    assert text.index("</body>") > text.index("/* Frontend-only MQTT Explorer mock")
    assert 'href="styles.css"' not in text
    assert 'src="curve_simulator.js"' not in text
    assert 'src="app.js"' not in text
    assert 'src="mqtt_viewer.js"' not in text
    assert 'src="live_adapter.js"' not in text
    assert "window.VaillantLive = {" not in text


def test_build_fails_for_missing_asset(tmp_path, monkeypatch):
    # Build script source does not silently degrade to a partial preview.
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("bundle", ROOT / "scripts/build_webui_standalone.py")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ASSETS", ("missing_file.js",))
    try:
        mod.build(tmp_path / "bad.html")
    except ValueError as err:
        assert "Expected exactly one reference" in str(err)
    else:
        raise AssertionError("Missing JS reference must stop the preview build")
