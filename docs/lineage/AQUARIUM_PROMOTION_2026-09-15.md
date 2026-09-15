# Aquarium / Display Promotion — 2026-09-15

## Source lineage

Aquarium/display policy is promoted exactly once from the byte-identical source implementation:

- `Apeloff1/Lorebuffa/backend/aquarium_routes.py`
  `223f65a8b8cb4c60528e6c4cc585a01296178ea0`
- `Apeloff1/Openworld/backend/aquarium_routes.py`
  `223f65a8b8cb4c60528e6c4cc585a01296178ea0`

The two source repositories therefore provide one lineage source, not two independent primitives.

## Frontier targets

- `skeleton/frontier/aquarium_models.py`
- `skeleton/frontier/aquarium_state.py`
- `skeleton/frontier/aquarium.py`
- `skeleton/frontier/aquarium_adapters.py`
- `skeleton/frontier/gameplay.py`

## Promoted policy

The frontier surface retains only portable aquarium/display semantics:

- tank capacity, unlock level, decoration limit and multi-currency cost normalization;
- immutable aquarium/tank state with total-fish accounting;
- tank purchase planning without wallet mutation;
- fish add/remove transitions without tacklebox persistence;
- decoration ownership and exact-one placement consumption;
- explicit theme allowlists;
- bounded normalized display positions;
- provider-neutral event and memory projection using the canonical `DomainEvent` and memory-item boundary;
- stable subject identity and state-content SHA-256 digests;
- fail-closed hydration of event payloads back through aquarium state invariants.

## Deliberate hardening over source behavior

### Position bounds

The source request models accept arbitrary integer coordinates. Frontier display coordinates are constrained to `0..100` for both axes so malformed or hostile values cannot silently escape the normalized display plane.

### Global fish identity

The source route checks database records during transfers but does not define a portable state invariant preventing one fish identity from appearing in multiple tanks after corrupted persistence hydration. `AquariumState` now enforces global fish identity uniqueness across the whole aquarium.

### Decoration quantity semantics

The source stores owned decorations as repeated IDs and uses MongoDB `$pull` when placing one decoration. `$pull` removes every matching array element, so duplicate owned copies can collapse to zero after a single placement. Frontier inventory is quantity-based and placement consumes exactly one copy.

### Count consistency

`total_fish_displayed` must equal the sum of fish across all hydrated tank states. Persisted or event-derived mismatches fail closed.

### Event integrity

Aquarium events include stable subject identity and canonical state digests. Event-to-memory recovery reconstructs the full portable state and re-runs its invariants before accepting the digest. Malformed state therefore remains rejected even if an attacker recomputes a digest for the malformed payload.

### Deterministic boundaries

Clock and generated decoration identity are injected by callers. Process-global randomness, UUID generation, database clients and mutable service state are not promoted into the kernel.

## Rejected from the frontier kernel

- FastAPI routers and Pydantic request models;
- MongoDB/Motor connection and collection access;
- user wallet mutation;
- tacklebox deletion/insertion;
- visit/like persistence and daily-like queries;
- source tank, decoration and theme catalogs;
- frontend presentation data such as icons and palette colors;
- database upserts and framework-specific response structures.

Source repositories remain authoritative for those catalogs and application-service concerns.

## Evidence

- `skeleton/testing/test_frontier_aquarium_policy.py`
- `skeleton/testing/test_frontier_aquarium_event_memory.py`
- `skeleton/testing/test_frontier_aquarium_gameplay_facade.py`
- `skeleton/testing/test_frontier_aquarium_benchmark.py`
- `scripts/benchmark_frontier_aquarium.py`

Benchmark timing is observational only. Correctness invariants — duplicate identity rejection, exact-one decoration consumption, stable event/memory projection, digest uniqueness and accounting — are gated.

## Selective-promotion boundary

This wave does not create a second event bus, memory store, wallet, inventory service, persistence layer, catalog framework or API framework. Aquarium remains a pure gameplay policy composed with the existing frontier event/memory primitives.
