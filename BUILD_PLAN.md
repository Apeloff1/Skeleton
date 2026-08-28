# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Generated 2026-08-28, anchored to the deep-cut ledger (fe5ec07, c553ef8, bdca180b).

## Correction log

- ca9238c mistakenly rewrote api/server.py + api/errors.py; restored (b4790a1).
- B4/B5 deploy constraint discovered via backend/Dockerfile + compose: image
  originally vendored only backend/. Shims guarded; B5 vendored skeleton/.

## Track A — Interface plane — DONE (f6c7a78 → 3ebed65)

## Track B — Memory/caching convergence — DONE (51275cb → 48963bd)

## Track C — Retrieval rank plane — DONE (31c8541)

## Track D — Kernel queue convergence — DONE (9622493)

## Track F — Quad retriever wiring — DONE (5a4d78a)

## Track G — Swarm/mesh audit — DONE (972b802, e6e765b)

## Track H — Context/gameforge wiring + import audit — DONE (df7fbcd, a5abbdc)

- [x] H1–H3. context/cortex mapped, Cockpit+GameForgeRun wired into lifespan,
      lazy-import contract verified (df7fbcd).
- [x] H4. Quad retriever endpoints live: `POST /retrieval/query` (RRF over
      RAG/CAG/MAG/KAG, plane stats included) and `POST /retrieval/ingest`
      (chunk + index documents) over the genesis `quad` handle (a5abbdc).
- [ ] H5. Cortex (44 modules) unwired: neocortex/lm/heads/moe have no genesis
      phase and no API surface. Needs its own design pass — own track.

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
      then live smokes: `GET /api/v1/context/snapshot` (was 503), a small
      `POST /api/v1/gameforge/run`, and `POST /api/v1/retrieval/query` after
      an ingest.

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
- ✅ Track H context/gameforge wiring + import audit (df7fbcd)
- ✅ H4 quad retrieval endpoints (a5abbdc)
