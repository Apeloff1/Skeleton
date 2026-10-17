# Jeeves × Dragon game-production E2E operating plan
Date: 2026-10-17  
Owner: canonical Jeeves studio goal journal + game-builder runtime; Dragon observes as a non-executing evidence consumer.

## Product journey

An operator creates an authenticated original-game project; Jeeves issues typed goals and obtains bounded model decisions; the existing application owner rechecks permissions and authorizes each tool step. The original world is edited or built with real source mutations, replayed through the runtime, reviewed through its deterministic and independent mirror, compiled or packaged, and exported with the current source identity. Dragon observes the already sealed tool/goal receipts. It may propose experiments for review, but observations never grant training or publishing authority.

The application continues to own execution, leases, idempotency, terminal status, storage and recovery. The Dragon view is a read-only, owner-scoped projection over the canonical goal journal. There is **no new API service, provider boundary, activity store, background recorder, privilege elevation or implicitly authorized capture**.

## First tranche: work delivered on the feature branch

| ID | Milestone | Implementation | Evidence / condition |
| --- | --- | --- | --- |
| E2E-001 | Current canonical architecture and ownership inspection | completed inspection | Architecture bootstrap, existing studio owner and Dragon trust boundaries read |
| E2E-002 | Typed Dragon goal-observation projection | implemented, not production-qualified | `skeleton/ai/game_builder/studio_e2e_observation.py` |
| E2E-003 | Event-chain replay across paginated goal steps | implemented, offline test supplied | Source step digests, owner-validated journal, stable sequence/hash chain |
| E2E-004 | Read-only authenticated owner/tenant ingress | implemented, not live tested | `GET /game-studio-agent/goals/{goal_id}/dragon-observation` delegates to existing scoped `agent.inspect` |
| E2E-005 | Anti-leak bounded evidence projection | implemented, offline tests supplied | Whitelist only tool ids, status, hashed evidence, phase/action counts and recovery |
| E2E-006 | Real local game-build-to-mirror exercise | test supplied; execution not performed in this session | Generate original world; run playable proof; compile browser/Godot source; run independent mirror |
| E2E-007 | Distinguish activity from successful production | implemented, test supplied | No output claims video, rights certification, hardware verification, weight promotion or qualified game |
| E2E-008 | Negative/fault-mode gate coverage | test supplied; execution not performed in this session | Tampered chain/head, legacy journals, invalid cursor, forged receipt, unauthorized local execution |
| E2E-009 | Register focused low-noise offline E2E | implemented | `machine/e2e_suites.json`, not a new global CI gate |

## Next operational milestones — not yet complete

| ID | Required acceptance proof |
| --- | --- |
| E2E-010 | Authenticated live CORE_DB E2E with two tenant accounts, isolation, lease contention and goal restart |
| E2E-011 | Explicit consent-bound Dragon desktop/window/video capture through existing Dragon consent and capture owners; mask secrets, recording status and retention controls |
| E2E-012 | Synchronize captured frame timestamps, visual state transitions and typed Jeeves action receipts without confusing the camera with an execution oracle |
| E2E-013 | Actual locally loaded Jeeves model checkpoint inference (not mock / provider fallback) and independent decision-review |
| E2E-014 | Complete interactive first-install → game project → original source → compiled native binary → playthrough → export; retain all artifact checksums |
| E2E-015 | Multi-ending paths, save/load, controls, cameras, physics and quest continuity, including resumed sessions and negative playthroughs |
| E2E-016 | Hours-to-weeks resumed execution, bounded maintenance windows, checkpoint recovery, storage backpressure, cancellation/lease fencing, leak/latency/resource measurements |
| E2E-017 | Dragon generated lesson candidates routed to existing reviewed almanac and rights-governance owners; no auto-promotion |
| E2E-018 | Independent replay/causality checks before any behavioral adjustment, plus negative controls for ambiguous, contradictory, and stale learning |
| E2E-019 | Shadow-model training on reviewed consented data, contamination scanning, isolated eval, rollback and explicitly authorized checkpoint promotion |
| E2E-020 | Product inspection UI: bounded phase filmstrip, evidence links, playback controls, permission/consent statuses, recovery console, learning proposals |

## Trust and qualification

- **Observation is not video**: this tranche derives operational evidence from actual existing receipts. No screen, mic, camera or desktop content is recorded.
- **Observation is not learning**: the dragon's observation queue has zero promoted training candidates; user-granted capture and separate reviewed knowledge must precede learning.
- **Executed is not passed**: a tool execution receipt establishes that an authorized invocation occurred; only the separate underlying runtime, final playthrough and qualified release evidence can prove the resulting game is shippable.
- **No inflated E2E percentage**: code authored and focused tests added are work delivered, not test passes. Stage completeness depends on measured exact-head CI and operational evidence.
- **Current source dependency**: changing gameplay source invalidates downstream play/review/package/export evidence. No release or weight promotion without fresh source-bound proofs.

## Focused validation

```sh
python -m pytest -q -ra --tb=short --noconftest tests/test_jeeves_game_e2e_observation.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Verification result for this session: the changes were committed to a feature branch through the GitHub connector; local runtime tests and live backend tests were **not executed**. This file is a working acceptance plan, not a qualification certificate.
