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

## Track H5 — Cortex wiring — DONE (3b22c74, 3892273)

- [x] H5.1. `JeevesCortex(bus=...)` wired as genesis `_phase_cortex` handle
      `cortex` — a fresh inspectable twin; the process-lived serving
      organism (`skeleton.cortex.live`) stays the singleton and is
      deliberately untouched. Local slots only, no network backends at boot.
- [x] H5.2. `api/cortex_routes.py`: `GET /cortex/status` and
      `POST /cortex/think` over the genesis handle; mounted in server.py.
      Call shapes verified against neocortex.py (`think(stimulus, context)`,
      `status()` dict).
- [x] H5.3. Design decision recorded: mutation paths (train / acquire /
      surpass / LoRA / gossip) stay on CLI + cockpit, NOT on HTTP. The
      cortex is a model organism; the API inspects it.
- [ ] H5.4 (future). Decide whether the genesis twin should BE the live
      singleton (repoint `_phase_cortex` at `cortex.live.live_cortex()`)
      once a persistence story (`$SKELETON_OWN`) exists in the container.

## Track E — Cleanup pass (deferred, requires local git ops)

- [ ] E1. Move 50 loose root test/sweep scripts into `tests/` and `scripts/`.
- [ ] E2. Move 8 `SEVEN_BY_*.md` docs into `docs/archive/`.
- [ ] E3. `backend/godot` (103 MB) → git-lfs or release asset + history purge.
- [ ] E4. Remove the three kernel shims + `Reranker` alias after consumer
      migration window.

## Verification

- [x] `skeleton/testing/test_build_plan_smoke.py` — 15 tests.
- [x] `skeleton/testing/test_swarm_consensus.py` — 6 tests.
- [ ] Run both suites in CI/local; `docker compose build backend` → prefix
      SHA unchanged; live smokes: `/api/v1/context/snapshot`,
      `/api/v1/gameforge/run`, `/api/v1/retrieval/query`, and now
      `/api/v1/cortex/status`.

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
- ✅ H5 cortex genesis phase + API surface (3b22c74, 3892273)
