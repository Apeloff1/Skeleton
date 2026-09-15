# Lucky-wheel policy promotion — 2026-09-15

## Source lineage

The lucky-wheel policy is mined from the same byte-identical shared rewards blob used for season-pass promotion:

- `Apeloff1/Lorebuffa/backend/rewards_routes.py`
- `Apeloff1/Openworld/backend/rewards_routes.py`
- shared blob: `27df9034118b9c5960668a231aed6d75385f8a9e`

## Frontier targets

- `skeleton/frontier/lucky_wheel.py`
- `skeleton/testing/test_frontier_lucky_wheel_policy.py`

## Promoted policy

- canonical nine-slot source reward table and probability mass;
- daily free/ad spin budgets;
- gem spin cost;
- deterministic weighted selection from an injected draw;
- pure spin authorization;
- wallet-neutral gem debit and reward projections.

## Hardening over source behavior

### Spin-type allowlist

The source only branches for `free`, `ad`, and `gem`, but does not reject any other value. An unknown `spin_type` therefore bypasses free/ad quota consumption and gem debit while still receiving a reward. The frontier policy rejects every spin type outside the explicit allowlist.

### Ad-verification boundary

The source consumes an ad spin solely from a caller-supplied `spin_type=ad`. The frontier policy additionally requires `ad_verified=True`, leaving proof-of-view verification to the application/provider boundary.

### Probability integrity

Wheel configurations reject duplicate slot ids, unsupported rewards/rarities, non-finite probabilities and probability mass that does not sum to one. Selection fails closed instead of preserving the source fallback to slot zero.

### Injected randomness

The domain kernel does not import or own a global RNG. Callers provide one finite draw in `[0, 1)`, making selection replayable and testable while allowing production code to choose an appropriate randomness source.

### Transactional plans

Gem spins preflight the available balance and return the required debit. Rewards are projected separately as currency increments, inventory increments or energy increments. Persistence boundaries can therefore apply debit, budget and reward atomically instead of the policy directly mutating several collections.

## Rejected from the kernel

- Python global `random` ownership;
- FastAPI routes;
- Motor/MongoDB state and spin-history persistence;
- ad-provider integration;
- direct wallet, energy, bait or item mutation;
- date rollover storage.

## Evidence

The focused tests cover exact source budgets/mass, malformed probability/identity rejection, deterministic draw selection, unknown-spin bypass rejection, free/ad quota behavior, verified ad completion, gem balance preflight, and typed reward projections.
