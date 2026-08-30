# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-08-30, anchored to the deep-cut ledger (fe5ec07 → 62b36bf).

## Correction log

- ca9238c mistakenly rewrote api/server.py + api/errors.py; restored (b4790a1).
- B4/B5 deploy constraint: backend image originally vendored only backend/;
  shims guarded; B5 vendored skeleton/ (48963bd).

## Tracks — all DONE

A · B · C · D · F · G · H · H5 · I · J · K · Docs (see git log for chains).

## Track L — Social-media SOTA sweep + archive — DONE (90118451, this commit)

Sourced from current (Aug 2026) retrieval/inference/agentic-memory discourse
and mapped onto Skeleton's real surfaces:

- [x] L1. Adaptive RRF plane weights — `retrieval/plane_weights.py`:
      EMA-bandit learner per plane; `observe(used, all)` moves weights in a
      bounded [0.3, 2.0] band so no plane starves. Attaches to QuadRetriever
      via constructor `weight_learner=` (optional; static weights otherwise).
- [x] L2. Workflow-aware cache eviction (KVFlow insight) —
      `memory/eviction.py`: keep_score = recency + freshness + rebuild cost
      + hit bonus; `evict_for_capacity` replaces naive eviction under
      pressure. Deterministic (name tiebreak).
- [x] L3. Utility-prioritized sleep replay — `cortex/sleep_prior.py`:
      trace priority = conf × (1 + slack); `attach_priority_replay` orders
      the buffer so high-value traces consolidate first. Uniform random
      sampling stays the default when unattached.
- [x] L4. SEVEN_BY series archived — `docs/archive/SEVEN_BY_INDEX.md`
      freezes the nine volumes (75 012 catalogued items); BUILD_PLAN.md is
      the living roadmap.
- [x] L5. `test_sota_upgrades.py` — 10 tests pinning all three modules.

## Track E — Cleanup pass (deferred, requires local git ops)

E1–E4 unchanged (root sprawl, SEVEN_BY file moves, godot binary, shim
removal). Note: SEVEN_BY volumes stay at root for link stability; only the
index lives under docs/archive/.

## Remaining ideas

- Wire PlaneWeightLearner into the API retrieval route: after a consumer
  marks which fragments it used, call `quad.observe(...)`. Needs a feedback
  endpoint decision.
- H5.4: genesis cortex twin vs live singleton, once $SKELETON_OWN persistence
  exists in the container.

## Completed cuts (ledger)

fe5ec07 · c553ef8 · bdca180b · b4790a1 · f6c7a78 · 31c8541 · e3eaeca ·
3ebed65 · 9622493 · 5a4d78a · 972b802 · e6e765b · df7fbcd · a5abbdc ·
3b22c74 · 3892273 · 3033821 · bc4fa6b · 4126b52 · 6fab006 · c81cfbe ·
3b06f15 · 90118451
