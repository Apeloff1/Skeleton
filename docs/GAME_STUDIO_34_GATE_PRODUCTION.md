# Jeeves Original-Game Studio: 34 Source-Bound Candidate Gates

**Scope:** extension to `skeleton/game/production_studio_gates.py`, the
existing game quality owner and the authorized Jeeves studio command registry.
**State:** implemented candidate evidence contracts; **not** production qualified.

## Seven delivery milestones — domains 28 through 34

| Gate | Required evidence | Fail-closed controls |
| --- | --- | --- |
| `audio_mix` | Authored buses, cue transition graph, hashed asset references, observed true peaks and LUFS | Reject clipping risk, undefined transitions, unmatched source, missing observations and unchecked limiters |
| `procedural_replay` | Generator hash, uint64 seeds, two output hashes and independent replay engine reference | Reject nondeterminism, seed collisions, variation collapse, missing cross-seed coverage |
| `economy_integrity` | Bounded integer double-entry postings, balanced replayed transactions, recipe requirements | Reject minted funds, duplicate transfers, missing crafting inputs, cyclic recipe dependencies |
| `multiplayer_sync` | Per-peer tick, hash of state and input, replay receipt, lag budget | Reject diverging hashes, lost tick acks, duplicate or nonmonotone ticks, excess lag |
| `transport_paths` | Waypoint topology, modalities, finite travel costs, destinations and hazard fallbacks | Reject unreachable target, dangling route, single mode, hazardous journeys without mitigation |
| `privacy_consent` | Purpose/retention policy, source-bound opt-in and opt-out replay observations | Reject opt-out emission, unreviewed raw identifier, excessive retention and missing opt-out trace |
| `endurance_recovery` | Bounded long-run samples spanning >=24h of **declared elapsed time**, checkpoint/reload digests | Reject unstable resource ceilings, gaps, missing recovery receipts and changed restore state |

Every nested `studio.advanced.*.source_sha256` equals the canonical candidate
source digest. `audit_advanced_studio` reuses the 27 existing gates in their
original order and appends seven named gates. A passed candidate is not an
independent native gameplay, audio hardware, privacy-compliance, adversarial
network or long-running wall-clock qualification.

## Six integrated upgrades

1. **Independent recomputation:** `verify_advanced_studio` constructs the full
   34-gate source audit again and rejects modified or injected summaries.
2. **Dragon red-team:** seven concrete domain attacks plus independent report
   forgery and structural summary forgery; no automatic weight promotion.
3. **Objective comparison:** before/after review across all 34 gate findings,
   critical regression detection and strict Pareto improvement.
4. **Accountable remediation:** owner-specific P0/P1 queue with no automatic
   editor mutation, plus read-only cross-domain impact links.
5. **Durable operation:** reuse the existing SQLite/WAL append-only chain,
   expected generation/CAS head and operator review. Ledger reader supports
   13/20/27/34 schemas and rejects cross-source replacement.
6. **Jeeves and CI integration:** eight new `game.studio.advanced.*` commands
   attach only via a trusted host; focused Python 3.11 compile and regression
   checks are registered with existing specialized game CI.

## Operator and authority contract (L00-L13)

- **L00 Intent/owner:** canonical `skeleton/game` production-quality owner,
  host-attached `skeleton/jeeves` interface; no new provider or runtime root.
- **L01 Architecture:** additive to the 27-gate source pipeline and registry.
- **L02 Interfaces:** JSON `game.candidate.advanced_studio.v1`; ordered
  `gates`, `findings`, evidence SHA-256, false `release_certified`.
- **L03 Admission/authority:** callers cannot provide alternate source loaders
  via command payload; `register_studio_tools` authorizes every invocation.
- **L04 Flow:** source -> 27 inherited gates -> 7 additional audits ->
  optional structural/independent verification -> queue/diff/history.
- **L05 State:** same `QualityHistoryStore` WAL store and CAS receipts;
  reports append only, never overwrite; reopen re-verifies entire chain.
- **L06 Security/privacy:** no credentials, arbitrary file writes, raw identity
  ingestion, true legal signoff or covert telemetry collection.
- **L07 Failure/recovery:** malformed, foreign, nonfinite or stale evidence is
  rejected; SQLite transaction rollback on conflict.
- **L08 Observability:** sorted gate findings, per-plane evidence digests,
  P0/P1 owners and read-only impact graph, replayable chain receipts.
- **L09 Capacity/economics:** capped sample arrays, finite bounded scalar
  domains, capped per-request queue; avoid unbounded remote inference costs.
- **L10 Deployment:** opt-in trusted-host attachment; unconfigured owners have
  no authorized operations and no live source access.
- **L11 Evaluation:** seven negative domain mutations, adversarial report and
  summary corruption, queue/diff/CAS/command regression acceptance.
- **L12 Rollback:** unregister advanced handlers; preserve existing 27-gate
  operators and historical records; never silently relabel a 34-gate record.
- **L13 Signoff:** candidate implementation complete only after local exact-head
  focused tests and required security/native checks; release certification
  remains false pending independent native and legal evidence.

## Validation

```shell
python -m compileall -q skeleton/game/production_advanced_*.py skeleton/jeeves/game_advanced_studio_quality_tools.py skeleton/testing/test_game_production_advanced_quality.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q --noconftest skeleton/testing/test_game_production_advanced_quality.py
```

Existing original-game gates, Godot workflows, machine contracts and review
authority remain authoritative. Synthetically authored fixtures provide only
structural and algorithmic candidate tests; they do not authenticate their own
captures or establish device-native facts.
