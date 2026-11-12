# Install and roll back

**Experimental software. Never remove a working thermostat or alter boiler safety settings based on this app.**

## Requirements

- Supported Supervisor-based Home Assistant installation, with the Apps/add-on store.
- MQTT broker service available to Supervisor.
- A platform listed in the add-on manifest (amd64 or aarch64).
- Network to fetch the pinned ebusd source during the local Docker build.

## Install the public app

1. Make a Home Assistant backup and document your current ebusd configuration.
2. In Home Assistant, open **Settings → Apps** (or **Settings → Add-ons**, depending on your version), locate the repository management menu and add `https://github.com/Alec-99/vaillant-ebus-control`.
3. Reload repositories, select **Vaillant eBUS Control (monitor-only)** and install the app.
4. **Keep `enable_bus: false` and `network_device: ""` for your first start.** This must not open the physical eBUS adapter.
5. Start the app and use **Open Web UI** (Home Assistant Ingress). Check MQTT connectivity and the monitor-only status. The UI's climate settings are simulations, not real boiler settings.
6. Confirm that your existing thermostat and ebusd setup continue operating normally. Keep the old ebusd add-on and this new app from sharing the same physical adapter.

## Optional passive bus connection (later, separately planned)

If you intentionally wish the new bundled ebusd to own your adapter, first stop the existing ebusd owner. Configure the exact enhanced TCP adapter address on the local Home Assistant system; **never commit it to GitHub**. Only one process may use the adapter. The app runs the bundled ebusd with strict `--readonly` (no active bus scan); without active polling some diagnostic fields might be unavailable. A cache value is not guaranteed current.

## Rollback

Stop the new monitor app. If you had intentionally transferred adapter ownership, restore the prior ebusd service and its original settings before starting it. Verify that the physical thermostat, heating and hot-water functions remain normal. If you did not enable the bus, stopping the monitor app does not require changing the old ebusd installation.

## Known limitations

- CI validates a disposable broker and mocked Supervisor only; actual HA OS acceptance testing is outstanding.
- The UI has a separate offline HTML preview, which displays demonstration values, not live device telemetry.
- No physical control API, native eBUS writes or general command shell exists.
- Building the image from source may take time and require significant CPU/memory.
