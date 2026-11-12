# Data privacy and example values

This public distribution intentionally contains **no raw household eBUS captures, original device log files, installation IP addresses, access tokens or personal history**. User-specific logs and internal agent research are not public release materials.

## Runtime data

- The MQTT broker credentials are obtained from Home Assistant Supervisor at runtime, not committed to source.
- Monitoring publishes a small set of state/telemetry messages under `vaillant_ebus/v1/` and a simulated MQTT climate discovery entity.
- The WebUI MQTT debugger retains up to 200 allowed messages in memory and shows the server receipt time, *not* the time of original physical measurement.
- Controller intent (simulated thermostat setpoint/mode) can be stored locally in the add-on `/data/` directory; the add-on does not collect personal cloud telemetry for this project.
- Installed ebusd may contact public network resources for configuration unless explicitly configured otherwise; consult the upstream documentation.
- Home Assistant may record published MQTT entities according to your **own** Recorder and broker settings. Review those settings before storing history.

## Sharing diagnostics

Do not attach unredacted Home Assistant backups, MQTT dumps, ebusd logs, device serials, local IPs/hostnames, Wi-Fi identifiers or credentials to public issues. Replace all real values with intentionally synthetic examples.

## Public development process

This repository is a curated release mirror. Detailed experiments, agent notes, logs and the private Git history are not copied into it. Release files are audited with both a privacy allowlist and an independent secrets scan before publication.
