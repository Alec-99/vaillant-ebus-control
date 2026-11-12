# WebUI

The same source files serve two distinct modes:

1. **Standalone HTML demo:** run `python scripts/build_webui_standalone.py` from the repository root (or download the Actions artifact). The bundler deliberately **removes** `live_adapter.js`. All climate, MQTT and terminal interactions are locally simulated. No backend, network or eBUS connections.
2. **Home Assistant Ingress:** within the installed add-on, `live_adapter.js` uses same-origin HTTP GET/SSE to request controller status, typed BAI cache diagnostic quality, recent status events and a bounded MQTT stream. It also exposes a server-validated subset of ebusd cache reads through the terminal.

Eight tabs: Overview, Thermostat, Heat Curve / Timeline, Diagnostics, Events, MQTT Debugger, Terminal and Settings. The thermostat and heat curve inputs remain simulations **even in Ingress mode**. Cached BAI readings include `cache_unverified` because the physical measurement timestamp is unknown.

The MQTT viewer is read-only, the container shell is disabled, and no SetMode or pump controls exist in this release.

Documentation: [architecture](../../../docs/ARCHITECTURE.md), [installation](../../../docs/INSTALLATION.md), [roadmap](../../../docs/ROADMAP.md).
