#!/usr/bin/env python3
"""Build one offline, self-contained HTML from the canonical WebUI sources.

This preview includes all tabs but intentionally has no REST/MQTT/ebusd backend.
Generated file belongs in a CI artifact, not in the runtime addon image.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "addons" / "vaillant-ebus-control" / "webui"
ASSETS = ("curve_simulator.js", "app.js", "mqtt_viewer.js")
STYLESHEET_TAG = '<link rel="stylesheet" href="styles.css">'


def build(output: Path) -> Path:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    css = (WEBUI / "styles.css").read_text(encoding="utf-8")
    if html.count(STYLESHEET_TAG) != 1:
        raise ValueError("Expected exactly one local stylesheet")
    if "</style" in css.lower():
        raise ValueError("CSS contains an unexpected closing style tag")
    html = html.replace(STYLESHEET_TAG, "<style>\n" + css + "\n</style>", 1)

    blocks = []
    for filename in ASSETS:
        tag = f'<script src="{filename}" defer></script>'
        if html.count(tag) != 1:
            raise ValueError(f"Expected exactly one reference to {filename}")
        script = (WEBUI / filename).read_text(encoding="utf-8")
        if "</script" in script.lower():
            raise ValueError(f"Unsafe HTML script close in {filename}")
        html = html.replace(tag, "", 1)
        blocks.append(f"<script>\n{script}\n</script>")

    # Ingress adapter is never included in the downloadable OFFLINE artifact.
    live_tag = '<script src="live_adapter.js" defer></script>'
    if html.count(live_tag) != 1:
        raise ValueError("Expected exactly one optional Ingress adapter script")
    html = html.replace(live_tag, "", 1)

    # Inlined scripts must run only AFTER DOM construction: "defer" does not
    # work on inline classic scripts inside <head>.
    if html.count("</body>") != 1:
        raise ValueError("Expected one closing body tag")
    html = html.replace("</body>", "\n".join(blocks) + "\n</body>", 1)
    html = "<!-- Generated WebUI preview. Source: webui/{index.html,styles.css,curve_simulator.js,app.js,mqtt_viewer.js}. UI-only, no backend. -->\n" + html
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package the entire Vaillant WebUI into one offline HTML")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "dist" / "vaillant-ebus-webui.html")
    args = parser.parse_args()
    output = build(args.output)
    print(f"Standalone preview created: {output} ({output.stat().st_size} bytes)")
