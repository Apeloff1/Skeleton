# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Generated 2026-08-28, anchored to the deep-cut ledger (fe5ec07, c553ef8, bdca180b).

## Correction log

- ca9238c mistakenly rewrote api/server.py + api/errors.py; restored (b4790a1).
- B4/B5 deploy constraint discovered via backend/Dockerfile + compose: image
  originally vendored only backend/. Shims guarded; B5 vendored skeleton/.

## Track A — Interface plane (skeleton/api) — DONE (f6c7a78 → 3ebed65)

## Track B — Memory/caching convergence — DONE (51275cb → 48963bd)

## Track C — Retrieval rank plane — DONE (31c8541)

## Track D — Kernel queue convergence — DONE (9622493)

## Track F — Quad retriever wiring — DONE (5a4d78a)

## Track G — Swarm/mesh audit — DONE (this commit)

- [x] G1. Twin-mesh finding: `agents/mesh.py` (operational roster, API-wired)
      and `swarm/mesh.py` (research substrate: partitions, circuit breakers,
      chaos, Vickrey auctions, reputation routing — Genesis-wired). Audited:
      NOT a fold — different layers, both live. Boundary documented in
      `skeleton/swarm/mesh_boundary.py` with the no-fold rule and the
      adaptation direction if a unified roster is ever wanted.
- [x] G2. Runtime bug: `ConsensusError(…, ballot=…)` hit
      `SkeletonError.__init__` (unknown kwarg) → TypeError on every failed
      quorum across consensus.py + mesh.py. Fixed at the root: ConsensusError
      now accepts `ballot=` and folds it into context (972b802).
- [x] G3. Runtime bug: BFT consensus called `AgentId.generate()` — the id
      lattice only exposes `new()`. Fixed (972b802).
- [x] G4. `test_swarm_consensus.py`: regression coverage for ballot carrying,
      all three raise paths, majority pass, BFT happy path.

## Track E — Cleanup pass (deferred, requires local git ops)

- [ ] E1. Move 50 loose root test/sweep scripts into `tests/` and `scripts/`.
- [ ] E2. Move 8 `SEVEN_BY_*.md` docs into `docs/archive/`.
- [ ] E3. `backend/godot` (103 MB) → git-lfs or release asset + history purge.
- [ ] E4. Remove the three kernel shims + `Reranker` alias after consumer
      migration window.

## Verification

- [x] `skeleton/testing/test_build_plan_smoke.py` — 15 tests covering DRR
      fairness, deadline expiry, submitter caps, shim identity,
      FeatureReranker, pipeline stages, prefix byte-determinism, filler
      persistence, warmer refresh, idempotency replay, quad event shape /
      cache hit / genesis wiring, SubmitterCapError export.
- [x] `skeleton/testing/test_swarm_consensus.py` — 6 tests covering ballot
      carrying, all three consensus raise paths, majority pass, BFT happy
      path (972b802).
- [ ] Run both suites in CI/local; then `docker compose build backend` and
      confirm the `jeeves:system` prefix SHA is unchanged after the B5 flip.

## Completed cuts (ledger)

- ✅ kernel/fair_queue.py → shim over work_queue.py DRR lanes (fe5ec07)
- ✅ kernel/vclock.py → shim over clocks.py immutable impl (fe5ec07)
- ✅ services/cag.py dead route-import sever + prefix text single-sourced (c553ef8)
- ✅ retrieval twin Reranker → FeatureReranker rename + alias (bdca180b)
- ✅ genesis.py imports canonical clocks path (bdca180b)
- ✅ api/server.py + api/errors.py restored after bad rewrite (b4790a1)
- ✅ Track A (f6c7a78, 31c8541, e3eaeca, 3ebed65)
- ✅ Track B (51275cb, 324db3d, 7790918, 656406a, 48963bd)
- ✅ Track D1 audit closed (9622493)
- ✅ Track F quad bus-contract fix + genesis wiring (5a4d78a)
- ✅ Track G swarm consensus ballot/AgentId fixes + mesh boundary (this commit)
