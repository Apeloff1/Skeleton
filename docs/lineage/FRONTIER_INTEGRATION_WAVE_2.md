# Frontier integration wave 2

PR #83 establishes provider-neutral runtime, memory, NPC and provenance boundaries. This wave turns those draft boundaries into a selective integration seam without copying source applications or creating parallel primitives.

## Source comparison

| Source | Strongest relevant implementation | Contract fit | Decision |
|---|---|---|---|
| `Apeloff1/Prood` | `backend/services/rag_service.py` (`b67167f…`) and `backend/routes/npc_pipeline.py` v15.5 (`b769cdc…`) | RAG collection/query/filter/relevance maps cleanly to `MemoryContract`; NPC archetype/profile semantics already promoted | **ADAPT RAG ONCE; retain Prood NPC as incumbent** |
| `Apeloff1/Tutolage` | `backend/services/rag_service.py` (`b67167f…`) and NPC v15.0 (`ea140f1…`) | RAG blob is byte-identical to Prood; NPC pipeline is an older sibling implementation | **DEDUPLICATE RAG; no second NPC primitive** |
| `Apeloff1/gameforge-rs` | `crates/gf-core/src/lib.rs` (`481fcfc…`) | Single SHA-256 digest, typed idempotency and durable outbox are strong runtime semantics; MongoDB/outbox infrastructure is too coupled for the frontier kernel | **PROMOTE digest semantics only; defer persistence plumbing** |
| `Apeloff1/Lorebuffa` | `backend/expanded_npcs.py` (`a232cb0…`) | Rich faction, schedule, quests, voice and disposition data exceed the minimal `NPCSpec` fields | **ADAPT records into `NPCSpec.metadata`; do not copy catalog** |
| `Apeloff1/Openworld` | `backend/expanded_npcs.py` (`a232cb0…`) plus world application routes | NPC blob is byte-identical to Lorebuffa; route-heavy world code is not a kernel contract | **DEDUPLICATE NPC catalog; characterize world logic separately** |
| `Apeloff1/hyperforge-cockpit-sota` | `src/lib/preview-host-bridge.ts` (`ef40a5e…`) | Versioned, validated, fail-closed boundary is a useful integration pattern, but the bridge is a cockpit consumer rather than a runtime primitive | **NO kernel copy; keep capability enforcement in `AgentRuntime`** |

## Concrete increment delivered

`CollectionMemoryAdapter` now wraps the synchronous collection surface used by the Prood/Tutolage RAG code behind the asynchronous `MemoryContract`. It preserves IDs, metadata filters and relevance values while keeping ChromaDB out of the kernel.

`npc_spec_from_domain_record()` now normalizes Lorebuffa/Openworld-style records into the existing `NPCSpec`. `NPCSpec.metadata` carries source-domain fields such as schedules, quests, shop data and source IDs, so the repository gains compatibility without a second NPC hierarchy or a copied 64 KB catalog.

`AgentRuntime.execute()` now accepts an all-of capability set in addition to the existing single-capability argument. Required and available capabilities are recorded in execution provenance. Capability names are normalized before enforcement and the boundary fails closed when any requirement is missing.

`ProvenanceRecord.for_artifact()` now binds promoted/generated results to a canonical SHA-256 content digest. This selectively imports the strongest portable invariant from `gameforge-rs` without importing its MongoDB outbox, async database singleton or event persistence path.

## Selective-promotion boundary

The source repositories remain authoritative for their application implementations and catalogs. This wave does **not** import FastAPI routers, ChromaDB, MongoDB, model/provider clients, cockpit message code, generated catalogs or duplicated RAG/NPC implementations. The manifest records exact source blobs so later promotion work can distinguish genuinely new behavior from renamed copies.

## Testable next increment

The next integration increment is deliberately small: attach a real collection backend to `CollectionMemoryAdapter` in an optional service package, run the same `MemoryContract` conformance tests against both the in-memory reference and that backend, then benchmark retrieval/filter behavior before any provider becomes canonical. In parallel, feed a small fixture of Lorebuffa/Openworld NPC records through `npc_spec_from_domain_record()` and validate round-trip domain metadata. Only after those gates pass should world simulation or GameForge durability semantics move inward.

Acceptance gates for that increment are: contract tests green, no new kernel dependency, exact source provenance present, duplicate-blob check clean, and benchmark evidence recorded before promotion.
