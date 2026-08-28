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

## Track G — Swarm/mesh audit — DONE (972b802, e6e765b)

## Track H — Context/gameforge wiring — DONE (df7fbcd)

- [x] H1. Discovered `skeleton/context/` (cockpit, tensor, helix, ledger,
      oracle, snowball, questionnaire, ten-stage pipeline) and
      `skeleton/cortex/` (44-module ML substrate) — packages absent from the
      original tree map.
- [x] H2. `state.cockpit`/`state.gameforge` were Optional-but-never-wired,
      so `/context/*` and `/gameforge/*` 503'd permanently. Lifespan now
      constructs one shared Cockpit and a GameForgeRun over it (df7fbcd).
- [x] H3. Lazy-import contract verified: `api/oauth.py`,
      `context/questionnaire.py`, `observability.probe`, `vault.ShamirSeal`,
      `MemoryTrinity.query_unified` all resolve; `fusion_contribution` field
      confirmed on MemoryQueryResult.
- [ ] H4. Wire the quad retriever endpoint (`POST /api/v1/retrieval/query`
      over genesis `quad` handle) — small additive route; next pass.
- [ ] H5. Cortex (44 modules) is unwired: neocortex/lm/heads/moe have no
      genesis phase and no API surface. Needs its own design pass — big
      enough to be its own track.

## Track E — Cleanup pass (deferred, requires local git ops)

- [ ] E1. Move 50 loose root test/sweep scripts into `tests/` and `scripts/`.
- [ ] E2. Move 8 `SEVEN_BY_*.md` docs into `docs/archive/`.
- [ ] E3. `backend/godot` (103 MB) → git-lfs or release asset + history purge.
- [ ] E4. Remove the three kernel shims + `Reranker` alias after consumer
      migration window.

## Verification

- [x] `skeleton/testing/test_build_plan_smoke.py` — 15 tests (queue, shims,
      reranker, pipeline, prefix renderer, warmer, idempotency, quad, genesis).
- [x] `skeleton/testing/test_swarm_consensus.py` — 6 tests (ballot carrying,
      three raise paths, majority pass, BFT happy path).
- [ ] Run both suites in CI/local; then `docker compose build backend` and
      confirm the `jeeves:system` prefix SHA is unchanged after the B5 flip;
      then a live smoke: `GET /api/v1/context/snapshot` (was 503, should now
      return the cockpit snapshot) and a `POST /api/v1/gameforge/run` with a
      small vision.

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
- ✅ Track G swarm consensus ballot/AgentId fixes + mesh boundary (972b802, e6e765b)
- ✅ Track H context/gameforge wiring + import contract audit (df7fbcd, this commit)
