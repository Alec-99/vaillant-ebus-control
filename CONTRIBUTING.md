# Contributing

Thanks for helping improve Vaillant eBUS Monitor.

## Working model

This is a curated public **release mirror**. The maintainers' development source also contains private diagnostic captures and device-specific notes, and is kept private. Public changes are not developed directly on the production release branch.

- File a public issue for a bug or general proposal, with **synthetic** examples and reproducible steps.
- You may propose a PR here, but maintainers must first incorporate and test the change in the private development source and then publish a vetted release. A public PR is not automatically merged. Attribution will be preserved where applicable.
- For vulnerabilities, use the process in [SECURITY.md](SECURITY.md) instead of public issues.
- All public tests and screenshots must use anonymized, generated data. Never upload IPs, MACs, device serials, broker passwords, access tokens, HA backup files or unredacted ebusd logs.
- Respect the monitor-only architecture. No unrestricted shell, eBUS writes, active scans, dangerous pump overrides or consumer-facing claims of fresh telemetry without separate design review.

## Local checks

```sh
python3 scripts/check_public_release.py --root .
python3 -m pip install pytest PyYAML
python3 -m pytest tests -q
python3 scripts/build_webui_standalone.py --output dist/vaillant-ebus-webui.html
```

The project uses pinned ebusd source in `build/ebusd-source.lock`. Docker builds and the integration smoke test run in CI with **no real eBUS device**. Follow the current [architecture](docs/ARCHITECTURE.md) and [roadmap](docs/ROADMAP.md). Publication of any new release requires a separate maintainer approval and privacy review.
