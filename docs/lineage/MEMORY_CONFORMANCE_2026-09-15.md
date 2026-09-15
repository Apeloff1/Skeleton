# Frontier memory conformance

The canonical memory boundary adapts the Prood/Tutolage RAG semantics once rather than carrying two source implementations.

## Source lineage

- Primary: `Apeloff1/Prood/backend/services/rag_service.py`
- Equivalent: `Apeloff1/Tutolage/backend/services/rag_service.py`
- Shared source blob: `b67167f1135744e74827ce03b0bf5d766e800cf4`
- Canonical boundary: `MemoryContract`
- Reference backend: `skeleton.frontier.memory.InMemoryStore`
- Persistent backend: `skeleton.frontier.memory_adapters.SQLiteCollection` through `CollectionMemoryAdapter`

## Conformance invariants

All canonical backends now share one normalization and lexical-relevance implementation. Explicit ids must be non-empty. Content must be present through `content`, `text`, or `document`. Metadata must be a mapping. Top-level filter fields are flattened into metadata, and conflicting top-level/nested representations fail closed.

Search results use the canonical shape `id`, `content`, `metadata`, and `relevance`. Exact and partial lexical ranking is shared by the reference and SQLite implementations. Filters are applied to canonical metadata. Reusing an id replaces the previous document and metadata instead of accumulating duplicate logical records. Delete rejects an empty id and is otherwise idempotent for missing records.

## Promotion boundary

This convergence does not promote ChromaDB, provider clients, source service globals, FastAPI routes, or separate Prood/Tutolage memory primitives into the frontier kernel. Provider-specific retrieval remains an adapter concern.

## Evidence

- `skeleton/testing/test_frontier_memory_backends.py`
- `skeleton/testing/test_frontier_memory_benchmark.py`
- `scripts/benchmark_frontier_memory.py`
- `skeleton/testing/test_frontier_integration_wave.py`

The benchmark remains evidence tooling rather than a fixed latency gate; provider backends must execute the same contract workload before promotion.
