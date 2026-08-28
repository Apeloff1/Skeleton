# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Generated 2026-08-28, anchored to the deep-cut ledger (fe5ec07, c553ef8, bdca180b).

## Track A — Interface plane (skeleton/api)

The api package is the thinnest subsystem relative to kernel. Goal: turn it
from a collection of helpers into a serving surface that wraps Genesis.

- [ ] A1. `api/server.py` — boot Genesis lazily, expose `GET /health` mapping
      `Genesis.health()` (phases, subsystem count, invariant violations).
- [ ] A2. `api/routes.py` — register the four canonical subsystem faces:
      memory (trinity query/add), retrieval (search), intelligence (orchestrator
      status), swarm (mesh roster).
- [ ] A3. Wire `api/errors.py` → `kernel.errors.http_status_for` so every
      SkeletonError subclass renders one error envelope.
- [ ] A4. Wire `api/idempotency.py` + `api/middleware.py` onto POST routes
      (memory add, dream trigger) — idempotency keys come from `kernel/dedup`.
- [ ] A5. `api/telemetry.py` → publish request spans onto the kernel EventBus
      so `observability/anomaly` sees API traffic like any other subsystem.

## Track B — Memory/caching convergence (backend ↔ skeleton)

Decision required before surgery (flagged in the ledger): backend
`services/memory_engine.py` stack is LIVE (routes.memory_engine → services
{cag, mag, rag_service}). Two architectures overlap:

- skeleton/memory: RAG TF-IDF store, CAG persona store, MAG episodic store
- backend/services: CAG prefix renderer, MAG KV-cache fillers, RAG ChromaDB

- [ ] B1. Decide ownership: skeleton/memory becomes canonical for semantics;
      backend services become thin HTTP-era adapters.
- [ ] B2. Port `services/cag.py` prefix rendering INTO
      `skeleton/memory/cag.py` as a sibling concern (PrefixRenderer class) —
      persona knowledge graph and KV prefix are the same data viewed two ways.
- [ ] B3. Port `services/mag.py` filler TTL/warmer INTO a new
      `skeleton/memory/warmer.py` — preemptive cache warming is a memory-plane
      concern, not a service-plane concern.
- [ ] B4. `services/memory_engine.py` collapses into `skeleton/memory/trinity.py`
      as a composition entry point; MemoryEngine becomes a facade re-export.

## Track C — Retrieval rank plane

Third rank primitive confirmed this pass: `retrieval/ranking.py` (diversity +
recency post-fusion) alongside `rerank.py` (rule boost) and `reranker.py`
(FeatureReranker). One pipeline should own all three stages.

- [ ] C1. `retrieval/pipeline.py` — accept optional `Ranker`, rule `Reranker`,
      and `FeatureReranker` stages; execute in fixed order
      (fuse → rule-boost → feature-rerank → diversity-rank).
- [ ] C2. Document stage order in module docstring; keep each stage optional
      so the pipeline degrades to today's behavior when stages are absent.

## Track D — Kernel queue convergence

- [ ] D1. Migrate any future lane-based consumers to `WorkQueue`; keep the
      `workqueue.py` and `fair_queue.py` shims until the rename pass, then
      collapse both aliases into one deprecation shim.
- [ ] D2. Add `FairWorkQueue` per-submitter caps as an optional lane-policy
      on `WorkQueue` (the orphan fair_queue's one unique feature worth
      keeping — deadline expiry + submitter caps).

## Track E — Cleanup pass (deferred, requires local git ops)

Deletion-capable cleanup the tool surface can't do via push:

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
