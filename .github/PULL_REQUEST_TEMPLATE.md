## Change summary

Describe user-visible behavior, limitations and backwards compatibility.

## Release safety checklist

- [ ] This change is represented and reviewed in the maintainer's private development source.
- [ ] Only explicitly allowlisted, synthetic, privacy-reviewed files are included.
- [ ] No real boiler captures, credentials, installation IPs, home sensor identities, agent memory or private history.
- [ ] `python scripts/check_public_release.py --root .` succeeds.
- [ ] Gitleaks and unit/CI checks succeed; any scanner finding was investigated.
- [ ] Monitor-only guarantees remain intact or the change received separate safety review.
- [ ] Documentation, dependency attribution, license and changelog are updated if needed.

Never attach private logs to this PR.
