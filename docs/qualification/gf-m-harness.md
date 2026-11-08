# GF-M qualification harness (Game Frontier P3, #4170)

`skeleton/qualification` evaluates declared qualification cases against
recorded evidence bound to an exact head SHA.

- **Cases** (`skeleton/qualification/cases/*.json`): id `GFM-<GATE>-NN`, gate, TODO ref, severity, gate params, `requires_hardware`.
- **Evidence** (`artifacts/qualification/evidence/*.json`): `case_id`, 40-char `head_sha`, `source` (ci/device/manual), `data`, optional sha256 `digest` of canonical `data`.
- **Gates**: `fps` (30/50/60/120 profiles, fixed sim rate, no state divergence), `perf` (p50/p95/p99 budgets), `soak` (hours, RSS slope, error rate, restarts), `retention` (min days per signal, PII cap), `replay` (restore hash fidelity), `promotion` (shadow→canary→production receipts, rollback).
- **Verdicts**: pass / fail / blocked. Missing evidence, stale-head evidence, or CI evidence for a hardware case is **blocked**, never pass. Overall = worst verdict; an empty run is blocked.

```
python -m skeleton.qualification --head <sha> [--evidence DIR] [--format md] [--out FILE]
```
Exit codes: 0 pass, 1 fail, 2 blocked, 3 schema error.

No production qualification is claimed by this PR: all shipped cases report
blocked until real evidence is recorded. CI wiring of the gate is left for a
follow-up, since this PR does not modify workflows.
