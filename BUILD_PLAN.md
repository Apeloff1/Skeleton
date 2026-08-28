# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Generated 2026-08-28, anchored to the deep-cut ledger (fe5ec07, c553ef8, bdca180b).

## Correction log

- The first scaffold attempt (ca9238c) mistakenly REWROTE the existing
  `api/server.py` (full AppState + lifespan wiring + health probes + metrics)
  and `api/errors.py` (ApiErrorResponse) with thin versions. Both were
  restored verbatim (b4790a1). Rule going forward: never rewrite an
  existing file for this build plan — extend only, and read before touching.

## Track A — Interface plane (skeleton/api)

- [x] A1. routes.py surveyed — endpoints exist for health, metrics, genesis,
      capabilities, jeeves, memory, swarm, ledger, scheduler, pipelines,
      forge, intelligence, resilience, context, gameforge, auth.
- [x] A2. Added missing handle-introspection endpoints: `GET /genesis/handles`
      and `GET /interface/reranker/stats` (f6c7a78).
- [x] A-fix. `AppState` declares `cockpit`/`gameforge` as Optional —
      `/context/*` and `/gameforge/*` previously raised AttributeError (500)
      instead of the intended 503 (f6c7a78).
- [x] A3. `api/telemetry.py` optionally mirrors request samples onto the
      kernel EventBus (topic `api.request.completed`) (31c8541).
- [x] A4. `api/idempotency.py` gained `extract_key` + `IdempotencyGuard`
      (`X-Idempotency-Key` header → replay recorded payload). Mounting on
      forge/materialise + gameforge POST handlers is the remaining step;
      needs a Request-typed param on those handlers (this commit).
- [ ] A5. Wire a `RouteTelemetry(bus=state.bus)` instance into
      request_id_middleware so A3 actually emits at runtime.

## Track B — Memory/caching convergence (backend ↔ skeleton)

Decision required before surgery: backend `services/memory_engine.py` stack
is LIVE (routes.memory_engine → services {cag, mag, rag_service}). Two
architectures overlap:

- skeleton/memory: RAG TF-IDF store, CAG persona store, MAG episodic store
- backend/services: CAG prefix renderer, MAG KV-cache fillers, RAG ChromaDB

- [ ] B1. Decide ownership: skeleton/memory becomes canonical for semantics;
      backend services become thin HTTP-era adapters.
- [ ] B2. Port `services/cag.py` prefix rendering INTO
      `skeleton/memory/cag.py` as a sibling concern (PrefixRenderer class).
- [ ] B3. Port `services/mag.py` filler TTL/warmer INTO a new
      `skeleton/memory/warmer.py`.
- [ ] B4. `services/memory_engine.py` collapses into
      `skeleton/memory/trinity.py`; MemoryEngine becomes a facade re-export.

## Track C — Retrieval rank plane

- [x] C1. `retrieval/pipeline.py` accepts optional rule `Reranker`,
      `FeatureReranker`, and `Ranker` stages; fixed order
      (rule-boost → feature-rerank → diversity-rank) (31c8541).
- [x] C2. Stage order documented in module docstring; stages optional (31c8541).

## Track D — Kernel queue convergence

- [ ] D1. Migrate lane-based consumers to `WorkQueue`; keep `workqueue.py`
      and `fair_queue.py` shims until the rename pass, then collapse.
- [x] D2. `WorkQueue` now supports optional per-submitter caps
      (`per_submitter_cap` + `SubmitterCapError`) and deadline expiry
      (`WorkItem.deadline`; expired items retire silently, counted under
      `stats().expired`). Opt-in; default construction is unchanged
      (this commit).

## Track E — Cleanup pass (deferred, requires local git ops)

- [ ] E1. Move 50 loose root test/sweep scripts into `tests/` and `scripts/`.
- [ ] E2. Move 8 `SEVEN_BY_*.md` docs into `docs/archive/`.
- [ ] E3. `backend/godot` (103 MB) → git-lfs or release asset + history purge.
- [ ] E4. Remove collapsed shims after consumer migration (D1, rename pass).

## Completed cuts (ledger)

- ✅ kernel/fair_queue.py → shim over work_queue.py DRR lanes (fe5ec07)
- ✅ kernel/vclock.py → shim over clocks.py immutable impl (fe5ec07)
- ✅ services/cag.py dead route-import sever + prefix text single-sourced (c553ef8)
- ✅ retrieval twin Reranker → FeatureReranker rename + alias (bdca180b)
- ✅ genesis.py imports canonical clocks path (bdca180b)
- ✅ api/server.py + api/errors.py restored after bad rewrite (b4790a1)
- ✅ Track A1/A2 + AppState cockpit/gameforge fix (f6c7a78)
- ✅ Track A3 telemetry bus mirror + Track C1/C2 rank-stage pipeline (31c8541)
- ✅ Track A4 idempotency guard + Track D2 queue policies (this commit)
