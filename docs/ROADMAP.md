# Public roadmap

These are proposed milestones, **not promises or deployment schedules**. Detailed device logs and private investigation notes are deliberately excluded.

## Current — v0.2.0 experimental monitor

- [x] Combined read-only Home Assistant add-on source and pinned ebusd build
- [x] Eight-tab WebUI: local simulation plus Ingress backend
- [x] Typed diagnostic cache snapshots with explicit quality / unknown freshness
- [x] Bounded MQTT status debugging and allowlisted read-only terminal
- [x] Offline simulation download, Docker mock-Supervisor integration smoke test
- [x] Public privacy/secret scanning and curated release process

## Next — installation and quality

- [ ] Test Ingress / Supervisor on a real Home Assistant OS installation with **bus disabled**
- [ ] Validate MQTT topic compatibility with an existing ebusd installation
- [ ] Confirm passive BAI profile decoding, actual device compatibility and source timestamps where possible
- [ ] Review accessibility, keyboard navigation, mobile layouts and failure-state UX
- [ ] Add reproducible example datasets, never actual user captures

## Planned — history and comparison

- [ ] Opt-in historical data import or Home Assistant Recorder integration
- [ ] Compare measured and simulated heating cycles
- [ ] Optional thermal parameter calibration against documented historical samples
- [ ] Export with privacy safeguards and explicit user consent

## Long-term research, not active control

- [ ] Evaluate control strategies offline and document failure modes
- [ ] Separate, explicitly approved architecture and safety review **before** any proposal to control a physical boiler
- [ ] Additional device models only after independent, documented compatibility tests

No heating control, pump override, SetMode or unrestricted shell is committed by this roadmap.
