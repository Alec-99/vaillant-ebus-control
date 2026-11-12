# Vaillant eBUS Monitor for Home Assistant

> **Experimental, monitor-only Home Assistant app (v0.2.0).** No physical heating commands. Not yet validated on a production Home Assistant OS / Vaillant installation.

An open-source Home Assistant add-on for reading cached diagnostics from Vaillant eBUS heating systems, viewing allowed MQTT status messages and exploring simulated thermostat and heating-curve strategies.

**This is not a replacement for a functioning room thermostat, boiler safety system or heating controller.**

## What is included

- Home Assistant Ingress WebUI with eight tabs: overview, thermostat simulation, heating curve / timeline simulation, diagnostics, events, MQTT debugger, a restricted ebusd cache terminal and settings.
- A Python monitor service that publishes a simulated climate entity and read-only typed BAI cache telemetry to MQTT.
- An optional pinned ebusd 26.1 build using strict `--readonly` and an explicitly configured enhanced network adapter.
- A bounded, allowlisted MQTT status stream. Browser clients do not receive MQTT credentials.
- Offline standalone HTML preview built by GitHub Actions, **with no backend or device connection**.
- Automated unit tests, an isolated broker / Supervisor integration smoke test, and a privacy gate.

## Safety first

| Capability | v0.2.0 |
| --- | --- |
| View MQTT diagnostic status through Ingress | Yes, if broker available |
| Run heating-curve simulations | Yes, **demo only** |
| Read cached BAI diagnostics | Optional, after explicitly enabling the bus |
| eBUS active scan or write / SetMode | **Not available** |
| Physical pump / burner control | **Not available** |
| Arbitrary shell terminal | **Not available** |
| Tested on production Home Assistant OS | **No** |

**Default: `enable_bus: false`.** Installing with defaults does not connect to any eBUS adapter. It still communicates with the Home Assistant MQTT broker, publishes simulated statuses / discovery and can persist simulated setpoints. To connect an adapter later, ensure your previous ebusd instance is stopped first; never connect two instances to the same physical adapter. Continue using your existing thermostat.

Cached measurements may be **old**: the original eBUS telegram timestamp is not available, and quality is intentionally marked `cache_unverified`. The add-on must not be used to make safety-critical or autonomous boiler decisions.

## Installation

For public installations, add this GitHub URL to the Home Assistant **Apps / Add-on repository** list and select *Vaillant eBUS Control (monitor-only)*. Follow the [installation and rollback guide](docs/INSTALLATION.md) before starting. First boot: keep `enable_bus: false` and verify MQTT and Ingress. Do not migrate the bus adapter until explicitly ready for a separate read-only experiment.

Home Assistant needs a supported Supervisor environment (Home Assistant OS / Supervised) and an MQTT broker service. The application image is built locally during installation; large downloads and compilation are expected.

## Resources

- [Installation and rollback](docs/INSTALLATION.md)
- [Architecture and security boundaries](docs/ARCHITECTURE.md)
- [Public roadmap and limitations](docs/ROADMAP.md)
- [Privacy and data provenance](docs/PRIVACY.md)
- [License, attribution and third-party software](docs/LICENSES.md)
- [Contributing](CONTRIBUTING.md), [security reports](SECURITY.md) and [changelog](CHANGELOG.md)

## Development and releases

This public repository is a **curated, independently versioned distribution**. Development and detailed research take place in a maintainer-controlled private workspace because they contain real device logs and installation data. Only explicitly reviewed, sanitized, tested releases are published here. Public issues and contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

**No personal captures, installation-specific addresses or user secrets are bundled in this repository.** If you find a privacy or security issue, please report it privately rather than including sensitive content in an issue.

## License

Original project source is provided under **GPL-3.0-only**. [ebusd](https://github.com/john30/ebusd) is separate third-party GPL software built from a pinned public source commit. See [LICENSE](LICENSE) and [license notices](docs/LICENSES.md). Not affiliated with Vaillant, Home Assistant or the ebusd maintainers.
