# Architecture and trust boundaries

```text
Home Assistant Supervisor / MQTT broker
      │ service credentials (server-side only)
      ├── Python monitor controller ── simulated climate state + cache telemetry
      │       └── optional ebusd (--readonly) → enhanced adapter (one owner only)
      └── read-only MQTT subscriber → bounded in-memory message queue
                                          │
                                  Ingress-only HTTP server
                                          │
                           Authenticated HA administrator browser
                           (status / diagnostics / events / SSE)
```

## Key boundaries

- The HA Ingress server handles static assets plus allowlisted GET routes. It refuses non-Supervisor-proxy connections, POSTs, unknown paths and arbitrary commands.
- The browser has no MQTT credentials and cannot publish raw broker commands.
- Only designated state and BAI topics enter the bounded MQTT viewer; this is not a general-purpose household MQTT explorer.
- Browser thermostat, curve, hysteresis and pump controls are simulations. The Python backend also computes demand as a simulated model but never emits physical SetMode.
- The bundled ebusd is optional and starts only with `enable_bus:true` and `--readonly`. A successful cached register read is labelled `cache_unverified`; the original bus telegram time is unknown.
- Runtime service credentials are requested from HA Supervisor; none should be committed, rendered to a browser or logged.

## Components

- `addons/vaillant-ebus-control/app/main.py`: simulated climate and MQTT status.
- `.../app/vaillant_control/telemetry.py`: typed allowlisted BAI cache decoding.
- `.../app/web_server.py`: Ingress read-only status, event stream and cache terminal.
- `.../webui/live_adapter.js`: same-origin Ingress browser client.
- `scripts/build_webui_standalone.py`: packages offline HTML without the live adapter.
- `scripts/check_public_release.py`: strict public source privacy audit.

See also [installation](INSTALLATION.md), [privacy](PRIVACY.md) and [roadmap](ROADMAP.md).
