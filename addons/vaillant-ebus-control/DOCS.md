# Vaillant eBUS Monitor — app documentation

This is an **experimental, monitor-only** Home Assistant app. The physical thermostat remains responsible for heating and hot water.

**Default `enable_bus: false`**: the combined app does not contact an eBUS adapter. It connects to Home Assistant MQTT for simulated state and optional read-only status display. All MQTT climate settings are simulated only and may be persisted in the add-on's data folder.

If an operator explicitly enables the bundled ebusd, stop any existing daemon using the same enhanced adapter first. The bundled daemon runs with strict `--readonly`. It can read available passive cache messages, but cannot actively scan, transmit SetMode or override the pump. Cached values may not have current measurement timestamps.

Open the interface with **Open Web UI** after starting the add-on. It is served behind Home Assistant administrator Ingress; there is no supported public HTTP port. The ebusd terminal accepts only a fixed allowlist of cache reads. The browser MQTT debugger is similarly restricted to monitored topics and cannot publish.

For installations and rollback see [the repository installation guide](../../docs/INSTALLATION.md); for diagnostics and limitations see [architecture](../../docs/ARCHITECTURE.md) and [roadmap](../../docs/ROADMAP.md). The download offered by GitHub Actions is an entirely **offline demo HTML**, not a live monitor.

**Not yet field-tested on a production Home Assistant OS installation.** Do not remove your existing thermostat or use this application for safety-critical heating control.
