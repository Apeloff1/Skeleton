# Breeding Promotion — 2026-09-15

## Source lineage

This wave promotes portable breeding/genetics semantics exactly once from one
byte-identical Lorebuffa/Openworld source lineage:

- `Apeloff1/Lorebuffa/backend/breeding_routes.py`
  `8f016084c60b44a4d3d09d16f6e5076722355212`
- `Apeloff1/Openworld/backend/breeding_routes.py`
  `8f016084c60b44a4d3d09d16f6e5076722355212`

## Promoted targets

- `skeleton/frontier/breeding.py`
- `skeleton/frontier/breeding_adapters.py`

## Promoted policy

- source-record normalization for species, parents and special breeds;
- symmetric species compatibility and max-parent breed timing;
- injected-RNG trait inheritance with explicit mutation probability;
- trait-based rarity/size/color/pattern valuation;
- special-breed matching with exact traits plus source-compatible fallback chance;
- immutable breeding-job start/refresh transitions;
- immutable offspring planning with injected identity, clock and RNG;
- breeding XP progression and rare-discovery tracking;
- breeding speed-up cost policy;
- parent/breeding slot upgrade quote policy;
- canonical offspring `DomainEvent` projection and stable memory identity;
- content digest verification before event-to-memory recovery;
- projection of special-breed completion into the existing achievement signal boundary.

## Deliberate hardening

The promoted policy rejects several unsafe or ambiguous source behaviors:

- one fish cannot occupy both parent positions in the same breeding job;
- booleans are not accepted as integers;
- NaN/Infinity and invalid RNG probability/size draws fail closed;
- dataclass construction is normalized/validated, not only record adapters;
- special-breed `value` is used as the offspring base value instead of being
  silently ignored;
- XP progression can cross multiple thresholds deterministically;
- event consumers revalidate both stable identity and offspring-content digest.

## Rejected from kernel

- FastAPI routers and Pydantic request models;
- Motor/MongoDB clients and database singletons;
- tacklebox insert/delete mutation;
- user wallet/gem mutation;
- full species, trait and special-breed catalogs;
- source UUID/time/random singletons.

## Evidence

- `skeleton/testing/test_frontier_breeding_policy.py`
- `skeleton/testing/test_frontier_breeding_event_memory.py`
- `skeleton/testing/test_frontier_breeding_benchmark.py`
- `scripts/benchmark_frontier_breeding.py`

Benchmark timing is observational only. Correctness and invariants are gated;
machine-dependent latency thresholds are intentionally absent.
