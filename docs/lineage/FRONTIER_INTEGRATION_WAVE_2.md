# Frontier integration wave 2

PR #83 establishes provider-neutral runtime, memory, NPC and provenance boundaries. This wave turns those draft boundaries into a selective integration seam without copying source applications or creating parallel primitives.

## Source comparison

| Source | Strongest relevant implementation | Contract fit | Decision |
|---|---|---|---|
| `Apeloff1/Prood` | `backend/services/rag_service.py` (`b67167f…`) and `backend/routes/npc_pipeline.py` v15.5 (`b769cdc…`) | RAG collection/query/filter/relevance maps cleanly to `MemoryContract`; NPC archetype/profile semantics already promoted | **ADAPT RAG ONCE; retain Prood NPC as incumbent** |
| `Apeloff1/Tutolage` | `backend/services/rag_service.py` (`b67167f…`) and NPC v15.0 (`ea140f1…`) | RAG blob is byte-identical to Prood; NPC pipeline is an older sibling implementation | **DEDUPLICATE RAG; no second NPC primitive** |
| `Apeloff1/gameforge-rs` | `crates/gf-core/src/lib.rs` (`481fcfc…`) | Single SHA-256 digest, typed idempotency and durable outbox are strong runtime semantics; MongoDB/outbox infrastructure is too coupled for the frontier kernel | **PROMOTE digest semantics only; defer persistence plumbing** |
| `Apeloff1/Lorebuffa` | `backend/expanded_npcs.py` (`a232cb0…`) and `backend/world_map.py` (`a32259d…`) | Rich NPC/world data and pure generation helpers are useful, but routers/database clients are application infrastructure | **ADAPT records; characterize pure world behavior once** |
| `Apeloff1/Openworld` | `backend/expanded_npcs.py` (`a232cb0…`) and `backend/world_map.py` (`a32259d…`) | Both inspected blobs are byte-identical to Lorebuffa; no second source promotion is justified | **DEDUPLICATE NPC + world lineage; no parallel primitive** |
| `Apeloff1/hyperforge-cockpit-sota` | `src/lib/preview-host-bridge.ts` (`ef40a5e…`) | Versioned, validated, fail-closed boundary is a useful integration pattern, but the bridge is a cockpit consumer rather than a runtime primitive | **NO kernel copy; keep capability enforcement in `AgentRuntime`** |

## Concrete increment delivered

`CollectionMemoryAdapter` wraps the synchronous collection surface used by the Prood/Tutolage RAG code behind the asynchronous `MemoryContract`. It preserves IDs, metadata filters and relevance values while keeping ChromaDB out of the kernel. Portable top-level filter fields are normalized into collection metadata; conflicting representations fail closed instead of silently diverging.

`SQLiteCollection` is now a persistent, dependency-free implementation of that same collection surface. It adds namespace isolation, deterministic lexical retrieval, exact metadata filtering and idempotent upsert behavior without creating a second memory abstraction. `InMemoryStore` and the SQLite-backed adapter run the same conformance workload.

`scripts/benchmark_frontier_memory.py` records repeatable write/search evidence for the reference and persistent backends under an identical `MemoryContract` workload. The benchmark is evidence, not a timing threshold, so ordinary CI is not made flaky by machine-dependent latency.

`npc_spec_from_domain_record()` normalizes Lorebuffa/Openworld-style records into the existing `NPCSpec`. A small source-shaped fixture records the shared `a232cb0…` lineage and verifies that schedules, quests, shop data, backstory, source IDs, faction and disposition survive normalization and serialization without copying the 64 KB source catalog.

`AgentRuntime.execute()` accepts an all-of capability set in addition to the existing single-capability argument. Required and available capabilities are recorded in execution provenance. Capability names are normalized before enforcement and the boundary fails closed when any requirement is missing.

`ProvenanceRecord.for_artifact()` binds promoted/generated results to a canonical SHA-256 content digest. This selectively imports the strongest portable invariant from `gameforge-rs` without importing its MongoDB outbox, async database singleton or event persistence path.

## Selective-promotion boundary

The source repositories remain authoritative for their application implementations and catalogs. This wave does **not** import FastAPI routers, ChromaDB, MongoDB, model/provider clients, cockpit message code, generated catalogs or duplicated RAG/NPC/world implementations. The manifest records exact source blobs so later work can distinguish genuinely new behavior from renamed copies.

## Acceptance evidence

The frontier contract workflow now covers the memory backend conformance suite, benchmark smoke test and source-shaped NPC fixture because it executes `skeleton/testing/test_frontier_*.py`. The persistent backend introduces no third-party runtime dependency: it uses Python's standard-library `sqlite3` and remains behind `CollectionMemoryAdapter`.

Evidence paths:

- `skeleton/testing/test_frontier_memory_backends.py`
- `skeleton/testing/test_frontier_memory_benchmark.py`
- `skeleton/testing/data/frontier_npc_source_fixture.json`
- `skeleton/testing/test_frontier_npc_source_fixture.py`
- `scripts/benchmark_frontier_memory.py`

## Wave 3 target

Lorebuffa and Openworld also share `backend/world_map.py` at blob `a32259d514710c3e87d7ce5fe42f6fb73e63ca1b`. The useful portable behavior is narrow: region lookup, deterministic route math/supply calculation, fog-of-war projection and random-island generation policy. FastAPI, Motor/MongoDB, persistence routes and the full world catalog stay outside the kernel.

Before promotion, Wave 3 must verify there is no incumbent Skeleton world primitive, split deterministic policy from randomness and clocks, inject those nondeterministic dependencies for tests, and promote at most one shared implementation lineage. GameForge durability remains deferred until its outbox/idempotency semantics are compared against Skeleton's existing forge/runtime persistence work rather than copied as a second subsystem.

Wave 3 acceptance gates are: duplicate-source proof, deterministic pure-function tests, no router/database dependency, exact source provenance, and a single canonical world-state surface before any world application data moves inward.
