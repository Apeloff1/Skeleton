# Frontier Waves 9–11 — Energy, Crafting, Equipment

This supplement records promotions landed after promotion-manifest v11 while the canonical manifest is being reconciled on a stable head. It does not replace the manifest; it prevents source lineage from becoming stale between large full-manifest rewrites.

## Wave 9 — Energy / stamina policy

Compared sources:

- `Apeloff1/Lorebuffa/backend/energy_routes.py` — `cac117f5de074756bdea557b8f419714fb215621`
- `Apeloff1/Openworld/backend/energy_routes.py` — `cd6fd76d71e3a9b3e4e5abf5cc0fc1e5cf584788`

Decision: **promote shared portable policy, not source file**. The blobs differ, so no exact-dedup claim is made.

Targets: `skeleton/frontier/energy.py`, `skeleton/frontier/energy_adapters.py`.

Promoted semantics include max-energy scaling, deterministic regeneration, bounded spend/restore, perfect-catch refunds, ad-limit policy, booster windows, usage accounting, stable energy identity, state digests and event-to-memory recovery. FastAPI, MongoDB, wallets, inventories, ad providers and source catalogs remain outside the kernel.

Evidence: `docs/lineage/ENERGY_PROMOTION_2026-09-15.md`, `skeleton/testing/test_frontier_energy_policy.py`, `skeleton/testing/test_frontier_energy_event_memory.py`, `skeleton/testing/test_frontier_energy_benchmark.py`, `scripts/benchmark_frontier_energy.py`.

## Wave 10 — Crafting / workshop policy

Exact shared source lineage:

- `Apeloff1/Lorebuffa/backend/crafting_routes.py` — `9a9b159588605b8658b8d6043f62622c401dd8ba`
- `Apeloff1/Openworld/backend/crafting_routes.py` — `9a9b159588605b8658b8d6043f62622c401dd8ba`

Decision: **promote once from identical source lineage**.

Targets: `skeleton/frontier/crafting.py`, `skeleton/frontier/crafting_adapters.py`.

Promoted semantics include recipe normalization, unlock/material checks, mutation-free material plans, timed craft jobs, collection and XP progression, speed-up quotes, cancellation refunds and slot-cost policy. A narrow adapter maps explicit crafted energy effects onto the existing `EnergyBoosterSpec` and rejects unrelated or mixed effect shapes.

Evidence: `docs/lineage/CRAFTING_PROMOTION_2026-09-15.md`, `skeleton/testing/test_frontier_crafting_policy.py`, `skeleton/testing/test_frontier_crafting_energy_adapter.py`, `skeleton/testing/test_frontier_crafting_benchmark.py`, `scripts/benchmark_frontier_crafting.py`.

## Wave 11 — Equipment / loadout policy

Exact shared source lineage:

- `Apeloff1/Lorebuffa/backend/equipment_routes.py` — `037724170943e13e237336f0df4631e2a81dd9d3`
- `Apeloff1/Openworld/backend/equipment_routes.py` — `037724170943e13e237336f0df4631e2a81dd9d3`

Decision: **promote once from identical source lineage**.

Target: `skeleton/frontier/equipment.py`.

Promoted semantics include record normalization, ownership/equip invariants, level/funds purchase quotes, universal/exact biotope matching, source-compatible bonus aggregation and recommendation filtering. Equipment catalogs, wallets, user lookups, FastAPI and persistence remain source-owned.

Evidence: `docs/lineage/EQUIPMENT_PROMOTION_2026-09-15.md`, `skeleton/testing/test_frontier_equipment_policy.py`, `skeleton/testing/test_frontier_equipment_benchmark.py`, `scripts/benchmark_frontier_equipment.py`.

## Next exact-dedup candidates already verified

- breeding: `backend/breeding_routes.py` — `8f016084c60b44a4d3d09d16f6e5076722355212` in both source repositories;
- bait: `backend/bait_routes.py` — `9963db63e814d84b6292ecc0cc4fe3c2b2b077e8` in both source repositories.

Cooking is not exact-dedup and requires semantic comparison before any promotion.
