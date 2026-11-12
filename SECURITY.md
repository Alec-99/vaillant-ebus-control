# Security policy

## Supported scope

Only the latest public `main` branch and its tagged, tested release are maintained. This is an **experimental read-only monitor**, not a certified heating controller. Do not expose its internal ports or MQTT broker to the public internet.

## Reporting vulnerabilities

**Do not publish secrets, real MQTT credentials, eBUS logs, physical device details, home addresses or proof-of-concept attacks in public issues.** Use GitHub's **Report a vulnerability** / private security advisory flow when enabled, or contact a repository maintainer through a private channel. Do not include working credentials in the report.

## Security design

- The web server is reachable through administrator-scoped Home Assistant Ingress, not a published host port.
- The browser never receives MQTT credentials.
- The terminal only accepts a specific read-only cache register allowlist; arbitrary shell execution and eBUS writes are not implemented.
- The daemon starts with `--readonly` only when the operator deliberately enables the bus; otherwise it does not connect to an adapter.
- MQTT subscriptions are constrained; the WebUI does not provide MQTT publishing controls.
- Cached data does not prove the original eBUS measurement timestamp.

## Release safeguards

Only privacy-scanned source files are published, with an independent public Git history. GitHub Actions runs a path/privacy-policy checker and Gitleaks on every public PR and push. These checks are additional to the maintainers' **pre-push** review; post-push CI cannot undo an accidental disclosure. Do not bypass a failed privacy gate.
