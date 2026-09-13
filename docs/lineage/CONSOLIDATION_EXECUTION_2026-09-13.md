# Consolidation execution — 2026-09-13

Canonical repository: `Apeloff1/Skeleton`
Base frontier: `frontier/consolidation-foundation`
Execution branch: `frontier/max-workload-consolidated`

## Objective

Turn the repository survey into an executable consolidation gate: promote only source capabilities that strengthen the canonical Skeleton contracts; characterize sibling implementations where they provide stronger invariants; reject duplicate application/framework layers.

## Source decisions

| Source | Decision | Immediate work |
|---|---|---|
| Prood | Selective promotion | Mine Jeeves laws, NPC/game generation, immersive tutor, RAG boundaries. |
| Tutolage | Selective promotion | Treat as historical source; reconcile only capabilities not already canonical. |
| gameforge-rs | Selective parity | Compare cache/pool/backpressure/coalescing/chaos/quorum semantics before adding code. |
| gameforge-middleware | Sibling | Preserve C# gate as an external implementation; extract contracts only. |
| hyperforge-cockpit-sota | Defer | Prototype lineage only; no kernel dependency. |
| Openworld/Newmove/Newsay/Lorebuffa families | Archive/characterize | Mine unique domain contracts, not legacy app scaffolding. |

## Canonical layering gate

1. **Kernel** — deterministic bounded primitives and policy contracts.
2. **Runtime/services** — orchestration, durable transitions, infrastructure adapters.
3. **AI/learning** — provider-neutral cognition and pedagogy contracts.
4. **Game/content** — NPC, game logic, animation, lore pipelines.
5. **Apps/cockpit** — replaceable presentation and transport surfaces.

A source contribution must target one layer explicitly. Cross-layer imports into kernel are a rejection condition.

## High-value parity targets

- Tiered cache semantics and bounded eviction.
- Health-aware connection pooling.
- Adaptive backpressure and fail-closed admission.
- Buffer reuse and explicit ownership.
- Request coalescing/idempotency.
- Chaos degradation state machine.
- Quorum/Court safety invariants.
- Event-bus transition/idempotency contracts.
- Jeeves learning-system laws and tutor boundaries.
- Text-to-NPC/game-logic provider-neutral interfaces.

## Promotion gate

A candidate is promotable only when all are true:

- deterministic behavior is specified;
- tests exist or can be written at the contract boundary;
- no mandatory MongoDB/ChromaDB/Axum/OpenAI dependency enters the kernel;
- source revision and path provenance are recorded;
- duplicate Skeleton implementation is reconciled rather than copied;
- failure behavior is explicit and bounded;
- generated artifacts, secrets, local caches, and machine-specific files are excluded.

## Current state

Inventory artifacts already committed:

- `docs/lineage/PROOD_INVENTORY_2026-09-13.md`
- `docs/lineage/TUTOLAGE_INVENTORY_2026-09-13.md`
- `docs/lineage/GAMEFORGE_RS_INVENTORY_2026-09-13.md`

Repository-level consolidation remains authoritative in `CONSOLIDATION.md`; this execution record narrows the next implementation pass to contract parity and provenance-backed promotion.
