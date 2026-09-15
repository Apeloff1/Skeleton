# Aquarium / Display Promotion — 2026-09-15

## Source lineage

Aquarium/display policy is promoted exactly once from the byte-identical source implementation:

- `Apeloff1/Lorebuffa/backend/aquarium_routes.py`
  `223f65a8b8cb4c60528e6c4cc585a01296178ea0`
- `Apeloff1/Openworld/backend/aquarium_routes.py`
  `223f65a8b8cb4c60528e6c4cc585a01296178ea0`

The two repositories therefore provide one lineage source, not two independent primitives.

## Reconciliation decision

A parallel aquarium promotion landed on the frontier branch while a split model/state implementation was being developed on a stacked branch. The parallel implementation is retained as the canonical domain primitive because it is broader and structurally stronger: it derives fish/decoration totals from canonical tank state, models tank dimensions/themes/visits/likes, preserves source record conversion, and keeps the portable policy in one coherent module.

The split duplicate `aquarium_models.py` / `aquarium_state.py` design is deliberately **not** promoted. Its useful integrity work is retained only as a non-duplicative adapter/test layer on top of the canonical module.

## Frontier targets

- `skeleton/frontier/aquarium.py` — canonical pure aquarium policy
- `skeleton/frontier/aquarium_adapters.py` — existing event/memory boundary adapter
- `skeleton/frontier/gameplay.py` — collision-free public gameplay surface

## Promoted policy

The canonical aquarium module retains portable semantics only:

- tank capacity, dimensions, unlock level, decoration limit and multi-currency costs;
- source record normalization for tanks, decorations, themes and displayed fish;
- immutable materialized tank state with globally unique fish and placement identities;
- **derived** fish/decoration totals rather than mutable counter fields;
- affordability shortfalls and purchase plans without wallet mutation;
- fish add/remove transitions without tacklebox persistence;
- quantity-aware decoration ownership with exact-one placement consumption;
- bounded source-compatible display positions (`0..100`);
- theme assignment using explicit theme specs;
- visit count policy and per-identity/per-day like ledger policy;
- injected timestamps and placement identities instead of process-global UUID/random behavior.

## Integrity adapter

`aquarium_adapters.py` composes the canonical state with existing frontier primitives. It adds no second event bus, memory store, or aquarium state model.

It provides:

- stable subject identity via canonical SHA-256 digest;
- canonical aquarium-state payload/digest;
- allowlisted aquarium `DomainEvent` topics;
- full event-state rehydration through canonical aquarium constructors;
- event→memory projection with fish, decoration, visit and like evidence;
- fail-closed digest format, identity and state-content verification.

An attacker cannot bypass state invariants merely by recomputing a digest over a malformed payload: event recovery first reconstructs canonical aquarium state, which re-runs tank ownership, identity, coordinate and value invariants before the digest is accepted.

## Deliberate hardening over source behavior

### Derived counts

The source stores `total_fish_displayed` alongside tank arrays. The frontier model derives totals from materialized tank state, eliminating list/counter drift by construction.

### Bounded positions

Source request models accept arbitrary integer coordinates. Frontier coordinates are constrained to the normalized `0..100` display plane.

### Global identities

Fish identities and placed-decoration identities must be unique across all materialized tanks, so corrupted hydration cannot duplicate one entity across displays.

### Decoration quantity semantics

The source stores repeated decoration IDs and uses MongoDB `$pull` during placement, which can remove every duplicate match. Frontier decoration inventory is quantity-aware and placement consumes exactly one copy.

### Daily like identity

The source daily-like query is represented as a pure `(liker_id, date)` ledger invariant, separated from database persistence.

### Event integrity

Aquarium events bind subject identity and canonical state content separately and rehydrate through canonical domain invariants before memory projection.

## Rejected from the frontier kernel

- source tank/decoration/theme catalogs;
- FastAPI routers and Pydantic request models;
- MongoDB/Motor clients and collection access;
- wallet mutation;
- tacklebox deletion/insertion;
- visit/like database persistence;
- application response envelopes;
- frontend-only presentation catalogs/assets;
- duplicate aquarium model/state modules.

Source repositories remain authoritative for catalogs and application-service persistence.

## Evidence

- `skeleton/testing/test_frontier_aquarium_policy.py`
- `skeleton/testing/test_frontier_aquarium_event_memory.py`
- `skeleton/testing/test_frontier_aquarium_gameplay_facade.py`
- `skeleton/testing/test_frontier_aquarium_benchmark.py`
- `scripts/benchmark_frontier_aquarium.py`

Benchmark timing is observational only. Correctness — identity uniqueness, derived counts, exact-one decoration consumption, state rehydration, digest integrity and memory projection — is gated.
