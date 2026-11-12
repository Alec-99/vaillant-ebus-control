# Changelog

All public versions are curated from reviewed changes in the maintainer's private development source. Private research logs and intermediate commits are not mirrored.

## 0.2.0 — Initial public preview

- Eight-tab offline demo and add-on Ingress UI.
- Read-only MQTT diagnostic viewer, bounded event stream and backend status.
- Typed BAI cache telemetry with explicit availability and *unverified freshness* states.
- Restricted allowlisted ebusd cache terminal; no shell or physical boiler writes.
- Simulated thermostat, heating curves, pump and return-temperature hysteresis.
- Home Assistant add-on structure and local mock-Supervisor/Mosquitto CI coverage.
- First privacy-reviewed public source export; independent public Git history.

**Limitations:** not validated on production Home Assistant OS or an actual heating system; do not treat simulations or cached data as physical measurements.
