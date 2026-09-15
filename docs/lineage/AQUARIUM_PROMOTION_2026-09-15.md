# Aquarium Promotion — 2026-09-15

## Source lineage

Aquarium/display policy is mined from one byte-identical implementation:

- `Apeloff1/Lorebuffa/backend/aquarium_routes.py` — `223f65a8b8cb4c60528e6c4cc585a01296178ea0`
- `Apeloff1/Openworld/backend/aquarium_routes.py` — `223f65a8b8cb4c60528e6c4cc585a01296178ea0`

## Targets

- `skeleton/frontier/aquarium_models.py`
- `skeleton/frontier/aquarium_state.py`
- `skeleton/frontier/aquarium.py`

## Promoted policy

- tank and decoration normalization;
- ownership, level, capacity and decoration-limit checks;
- pure multi-currency purchase quotes;
- immutable fish transfer plans;
- immutable tank purchase and theme transitions;
- counted decoration inventory with exact-one placement consumption;
- bounded aquarium positions;
- injected identity and clock for placed decorations.

## Evolution and hardening

The source accepts arbitrary position dictionaries. Frontier positions are typed integer percentages constrained to `0..100`.

The source stores duplicate decoration IDs in a list and places a decoration with MongoDB `$pull`. `$pull` removes every matching value, so placing one decoration can consume all duplicates. Frontier uses counted ownership and decrements exactly one unit.

The source add-fish route removes from the tacklebox with `delete_one({"id": fish_id})`, omitting the user identity used for the preceding lookup. Frontier performs no persistence mutation and returns a `FishTransferPlan`; persistence adapters must apply user-scoped writes at the boundary.

Additional hardening:

- fish size must be finite and nonnegative;
- fish identities cannot be displayed twice;
- placed-decoration identities cannot collide within a tank;
- total displayed-fish count must equal actual tank contents;
- booleans cannot silently coerce to integer quantities;
- theme changes require an explicit allowlist;
- all persisted timestamps entering policy are timezone-aware.

## Rejected from kernel

- tank, decoration and theme catalogs;
- FastAPI/Pydantic request surfaces;
- MongoDB/Motor clients;
- wallet mutation;
- tacklebox persistence;
- visit and like tracking;
- random/global identity generation.

## Evidence

- `skeleton/testing/test_frontier_aquarium_policy.py`

This remains a stacked wave until the wave-14 cooking head converges through the existing frontier gates.
