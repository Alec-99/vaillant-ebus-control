# Licensing and acknowledgements

## Project source

Unless otherwise noted, the original Vaillant eBUS Monitor add-on, UI, test and script code in this distribution is licensed under **GNU GPL version 3 only (GPL-3.0-only)**. See [LICENSE](../LICENSE) for the complete license text. Copyright © 2026 Alec-99 and contributors.

## Separate third-party components

- [ebusd](https://github.com/john30/ebusd), by its own authors, is licensed under **GPL-3.0**. This add-on compiles a version pinned in [build/ebusd-source.lock](../build/ebusd-source.lock) from a [public source fork](https://github.com/Alec-99/ebusd). The Docker build preserves the original ebusd LICENSE at `/usr/share/licenses/ebusd/LICENSE`. This project does not claim original authorship of ebusd.
- [Home Assistant base images](https://github.com/home-assistant) have their respective upstream licenses.
- [paho-mqtt](https://github.com/eclipse-paho/paho.mqtt.python) and other build/runtime dependencies remain under their respective licenses. Consult the upstream package notices when redistributing full container images.
- Vaillant and Home Assistant are trademarks of their respective owners. No manufacturer endorsement or official integration is claimed.

Keep all third-party copyright notices and source availability information when distributing modified builds or binaries.
