# Frontier Equipment Promotion — 2026-09-15

## Decision

Promote the portable equipment/loadout policy once from the exact shared
Lorebuffa/Openworld source lineage. Keep source equipment catalogs, FastAPI,
MongoDB, wallet mutation and persistent player inventory outside the frontier
kernel.

## Exact shared source

| Repository | Path | Blob |
| --- | --- | --- |
| `Apeloff1/Lorebuffa` | `backend/equipment_routes.py` | `037724170943e13e237336f0df4631e2a81dd9d3` |
| `Apeloff1/Openworld` | `backend/equipment_routes.py` | `037724170943e13e237336f0df4631e2a81dd9d3` |

This is one source lineage and one promotion.

## Promoted policy

- equipment record normalization for rod, line and bobber categories;
- finite numeric stat/bonus validation;
- non-negative currency cost normalization;
- universal/exact biotope matching;
- immutable ownership/equipped loadout state;
- level/ownership/funds purchase quote;
- mutation-free ownership application;
- equip-only-if-owned policy;
- source-compatible rod/line/bobber bonus aggregation;
- optional universal-item inclusion in recommendation filtering;
- duplicate equipment identity rejection in recommendation inputs.

The bonus aggregator intentionally preserves source key semantics instead of
silently redesigning balance behavior. For example, rod bonus keys containing
the selected biotope or the word `bonus` multiply catch rate; rare/legendary,
distance and fighting/power keys also feed their respective projections.

## Hardening beyond source routes

The promoted boundary rejects:

- unknown equipment categories;
- empty/non-normalized identities;
- boolean-as-number values;
- NaN or infinite stats/bonuses;
- non-positive bonus multipliers;
- negative balances/costs;
- equipped items that are not owned;
- duplicate recommendation identities;
- category-confused bonus aggregation.

Purchase quotes do not mutate balances. Purchase/equip functions do not touch a
wallet, database or provider. External services decide when to apply the
returned state after completing their own transaction boundary.

## Rejected from frontier kernel

- source rod/line/bobber catalogs;
- FastAPI routes and Pydantic request models;
- Motor/MongoDB clients;
- wallet/currency deduction;
- persistent equipment inventory;
- user database lookups;
- source database singletons.

## Evidence

- `skeleton/testing/test_frontier_equipment_policy.py`
- `skeleton/testing/test_frontier_equipment_benchmark.py`
- `scripts/benchmark_frontier_equipment.py`

Benchmark timing is observational only; correctness invariants are asserted
without machine-dependent latency gates.
