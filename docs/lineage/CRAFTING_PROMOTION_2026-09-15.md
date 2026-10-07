# Frontier Crafting Promotion — 2026-09-15

## Decision

Promote the portable crafting/workshop policy once from the exact shared
Lorebuffa/Openworld source lineage and keep all recipe/material catalogs,
FastAPI/MongoDB handlers, wallet mutations and inventory persistence in the
source applications.

## Exact shared source

| Repository | Path | Blob |
| --- | --- | --- |
| `Apeloff1/Lorebuffa` | `backend/crafting_routes.py` | `9a9b159588605b8658b8d6043f62622c401dd8ba` |
| `Apeloff1/Openworld` | `backend/crafting_routes.py` | `9a9b159588605b8658b8d6043f62622c401dd8ba` |

This is one source lineage, not two separate promotions.

## Promoted policy

- recipe, ingredient and output normalization;
- level or explicit-unlock eligibility;
- material shortfall and can-craft checks;
- mutation-free material consumption plans;
- deterministic start/complete timestamps with injected UTC time;
- workshop slot occupancy and completion refresh;
- collection planning with output, XP and total-crafted accounting;
- crafting XP threshold policy (`level * 100`);
- deterministic multi-level XP carry-forward;
- source-compatible speed-up cost quote;
- instant-completion planning without wallet mutation;
- cancellation recipe binding and integer-floor 50% material refund;
- crafting-slot cost curve (`100 * current slots`) and maximum-slot policy.

## Hardening beyond the source routes

The promoted policy rejects:

- boolean-as-integer slot/quantity confusion;
- empty or non-normalized IDs;
- duplicate recipe ingredients;
- naive timestamps and reversed job times;
- workshop state whose slot count disagrees with `max_slots`;
- collection before completion;
- cancellation after completion;
- cancellation with a recipe different from the active job;
- negative inventory quantities.

Unlike the source endpoint, XP carry-forward can cross more than one crafting
level deterministically in a single collection operation.

## Cross-contract seam

`skeleton/frontier/crafting_adapters.py` contains one deliberately narrow
adapter: `energy_booster_from_craft_output`.

It maps only explicit canonical energy effect shapes to the existing
`EnergyBoosterSpec`:

- `{energy_restore}`;
- `{infinite_duration_minutes}`;
- `{regen_multiplier, duration_minutes}`.

XP, luck, inventory-capacity, mixed, unknown or empty effects fail closed. The
crafted quantity remains an inventory concern; the adapter describes the effect
of consuming one output item. No second booster, inventory or effect system is
introduced.

## Rejected from the frontier kernel

- source recipe/material catalogs;
- FastAPI request/response routes;
- Motor/MongoDB clients;
- direct material/inventory mutation;
- wallet/gem deduction;
- reward persistence;
- background timers;
- source user lookups.

## Evidence

- `skeleton/testing/test_frontier_crafting_policy.py`
- `skeleton/testing/test_frontier_crafting_energy_adapter.py`
- `skeleton/testing/test_frontier_crafting_benchmark.py`
- `scripts/benchmark_frontier_crafting.py`

Benchmark timing is observational. Correctness invariants are asserted without
machine-dependent latency thresholds.
