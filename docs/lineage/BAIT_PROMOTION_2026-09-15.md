# Bait and Fishing-Spot Promotion — 2026-09-15

## Source lineage

Portable bait and fishing-spot policy is promoted exactly once from the
byte-identical source implementation:

- `Apeloff1/Lorebuffa/backend/bait_routes.py`
  `9963db63e814d84b6292ecc0cc4fe3c2b2b077e8`
- `Apeloff1/Openworld/backend/bait_routes.py`
  `9963db63e814d84b6292ecc0cc4fe3c2b2b077e8`

## Target

- `skeleton/frontier/bait.py`

## Promoted policy

- bait record normalization and finite multiplier boundaries;
- quantity-scaled multi-currency purchase-cost planning;
- affordability checks without wallet mutation;
- equip and durability transitions without inventory persistence;
- effective-fish matching including source `all` semantics;
- source-compatible bait + spot catch bonus aggregation;
- fishing-spot normalization, unlock requirements and selection;
- boat and required-item access requirements;
- provider-neutral multiplicative composition with equipment bonuses.

## Deliberate hardening

- booleans do not silently coerce to integers or multipliers;
- NaN and Infinity fail closed;
- an equipped bait must resolve to the matching bait definition;
- durability reaches an explicit empty loadout instead of negative state;
- duplicate currencies/effective-fish entries fail closed;
- string values are rejected where a sequence is required.

## Rejected from kernel

- bait and fishing-spot catalogs;
- FastAPI/Pydantic routes;
- MongoDB/Motor clients;
- wallet and inventory mutation;
- player spot persistence and catch-stat writes.

## Evidence

- `skeleton/testing/test_frontier_bait_policy.py`
- `skeleton/testing/test_frontier_bait_equipment_integration.py`
- `skeleton/testing/test_frontier_bait_benchmark.py`
- `scripts/benchmark_frontier_bait.py`

Benchmark timing remains observational only.
