# Frontier Energy Promotion — 2026-09-15

## Decision

Promote the portable energy/stamina policy once into `skeleton/frontier/energy.py`
and compose it with the canonical event/memory boundaries in
`skeleton/frontier/energy_adapters.py`.

The source implementations are closely related but are **not the same blob**, so
this is a shared-policy promotion, not an exact-source deduplication claim.

## Compared sources

| Repository | Path | Blob |
| --- | --- | --- |
| `Apeloff1/Lorebuffa` | `backend/energy_routes.py` | `cac117f5de074756bdea557b8f419714fb215621` |
| `Apeloff1/Openworld` | `backend/energy_routes.py` | `cd6fd76d71e3a9b3e4e5abf5cc0fc1e5cf584788` |

Both inspected sources expose the same portable concepts:

- base max energy of 100;
- one energy regenerated per minute;
- +10 maximum energy per ten levels;
- 1.5x VIP base-capacity multiplier;
- perfect-catch refund;
- bounded spend and restore;
- daily ad-restoration limit;
- direct restore boosters;
- timed infinite-energy boosters;
- timed regeneration multipliers;
- usage/restoration accounting.

## Promoted surface

`EnergyPolicy`
: Immutable validated policy values. Non-finite, non-positive or type-confused
configuration fails closed.

`EnergyState`
: Provider-neutral immutable state with canonical UTC timestamps, bounded
current/max energy, booster windows, counters and accounting.

`EnergyBoosterSpec`
: Normalizes one source-shaped booster and requires exactly one effect. Wallet
and inventory mutations are deliberately excluded.

`regenerate_energy`
: Deterministic time-based regeneration with explicit handling for an active
multiplier window and ordinary regeneration after the multiplier expires.

`consume_energy`
: Regenerates first, rejects insufficient balance, and treats active infinite
energy as a zero-spend operation.

`restore_energy`
: Caps restoration at maximum energy and accounts for actual restored units,
rather than requested units that could not fit.

`restore_from_ad`
: Resets the daily counter on a new UTC date, enforces the daily limit, and
returns a mutation-free plan.

`max_energy_for_level` / `sync_max_energy`
: Preserve the source level/VIP capacity rules while preventing state from
remaining above a newly lowered maximum.

`energy_status`
: Produces synchronized current state plus infinite-mode and time-to-full
projection.

## Boundary composition

`energy_event` publishes a canonical `DomainEvent` only after:

- subject identity is normalized;
- action is in the supported transition set;
- `occurred_at` is timezone-aware and not earlier than state time;
- stable subject identity and complete state SHA-256 digests are attached.

`energy_event_to_memory_item` revalidates both digests before the stable
subject-energy identity may be used as the memory upsert key. Tampered current
energy, accounting, timestamps or subject identity therefore fail before
memory side effects.

Repeated at-least-once delivery converges through the existing memory upsert
contract instead of creating a second energy persistence primitive.

## Deliberately rejected from frontier kernel

- FastAPI routers and request models;
- Motor/MongoDB clients and database singletons;
- player wallet mutations;
- booster inventory mutations;
- ad-provider integrations;
- user/VIP database lookups;
- source booster catalogs as authoritative kernel data;
- background timers or schedulers.

Callers inject level/VIP facts, time, booster records and external side effects.

## Hardening beyond source coupling

The source route implementations mix policy and persistence and contain several
behaviors that are unsafe as a reusable kernel primitive. The promoted policy:

- rejects naive timestamps and time reversal;
- rejects boolean-as-integer confusion;
- rejects non-finite numeric multipliers;
- prevents current energy exceeding max energy;
- does not bank regeneration while already full;
- accounts only the energy actually restored when a restore is capped;
- validates ambiguous boosters instead of picking the first matching branch;
- keeps timing deterministic by accepting `now` explicitly.

## Evidence

- `skeleton/testing/test_frontier_energy_policy.py`
- `skeleton/testing/test_frontier_energy_event_memory.py`
- `skeleton/testing/test_frontier_energy_benchmark.py`
- `scripts/benchmark_frontier_energy.py`

Benchmark timing is observational only. Correctness invariants are asserted;
machine-dependent latency thresholds are not CI gates.
