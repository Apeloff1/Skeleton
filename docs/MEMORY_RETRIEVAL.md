# Canonical memory and retrieval boundary

Issue #118 consolidates storage and retrieval without deleting the useful legacy
RAG/CAG/MAG implementations in one flag day.

## Canonical contracts

There are two boundaries with different responsibilities:

1. `skeleton.frontier.contracts.MemoryContract` is the storage contract. It owns
   `put`, `search`, and `delete` and returns portable mapping-shaped hits.
2. `skeleton.frontier.retrieval_context.RetrieverContract` is the runtime
   retrieval contract. `MemoryRetriever` adapts any `MemoryContract` and
   validates source attribution before content can enter an agent context.

`AgentRuntime` remains the only promoted execution lifecycle. Runtime retrieval
uses the canonical memory/retrieval normalization and injects validated hits
under the reserved `retrieved_context` key. The request identity participates in
idempotency, and execution provenance records only source identifiers and a
content digest, never the retrieved document text.

## Required source provenance

Any memory that may be injected into agent execution must carry
`metadata.source_repository` as a normalized non-empty string. The following
fields are also preserved when known:

- `metadata.source_revision`
- `metadata.source_path`
- `metadata.source_tier`

Retrieval fails closed when source repository attribution is absent. Revision
and path are optional so runtime-generated or external stores that cannot expose
a finer source location can still participate honestly.

## Backend conformance

The shared Frontier contract suite exercises the same portable behavior across:

- `skeleton.frontier.memory.InMemoryStore`
- `CollectionMemoryAdapter(SQLiteCollection(...))`
- `LegacyMemoryStoreAdapter(InMemoryTFIDFStore(...))`

Conformance covers normalized writes, exact metadata filters, ranked reads,
deletes, strict JSON metadata, and end-to-end source preservation.

## Legacy migration plan

The synchronous `skeleton.memory.MemoryStore` hierarchy remains a compatibility
source while callers migrate. New runtime code must not consume its `query`
results directly.

Migration sequence:

1. Wrap an existing `MemoryStore` with
   `skeleton.memory.frontier_adapter.LegacyMemoryStoreAdapter`.
2. Program new storage callers against `MemoryContract` rather than concrete
   RAG/CAG/MAG classes.
3. Program retrieval callers against `RetrieverContract` / `MemoryRetriever`.
4. Supply source repository metadata at ingestion, before the item becomes
   eligible for agent retrieval.
5. Move backend-specific ranking/index logic behind an adapter; do not add
   provider fields to agent/runtime types.
6. Once a legacy store has no direct production consumers, retire its duplicate
   public query path or keep it as an internal backend implementation only.

`ChromaDBStore`, `InMemoryTFIDFStore`, CAG, and MAG are therefore not new
canonical runtime contracts. They are storage/index implementations that must
cross the Frontier boundary through adapters when used by promoted runtime code.

## Guardrails

- Retrieved content is never copied into execution provenance; only a SHA-256
  digest and source identifiers are retained there.
- Metadata and filters must stay inside the finite strict-JSON data model.
- A backend returning more hits than requested, malformed identities, invalid
  relevance scores, or unattributed content fails closed.
- The reserved runtime context key `retrieved_context` cannot be supplied by a
  caller when runtime retrieval is requested.
- New retrieval backends must pass the shared contract suite before promotion.
