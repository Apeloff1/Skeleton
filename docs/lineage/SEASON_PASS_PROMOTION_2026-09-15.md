# Season-pass policy promotion — 2026-09-15

## Source lineage

The season-pass subsystem is promoted once from the byte-identical rewards implementation:

- `Apeloff1/Lorebuffa/backend/rewards_routes.py`
- `Apeloff1/Openworld/backend/rewards_routes.py`
- shared blob: `27df9034118b9c5960668a231aed6d75385f8a9e`

Daily-login streak semantics are already represented by the canonical achievement/daily-reward frontier policy, so they are not duplicated here. Lucky-wheel randomness, database persistence and application routes also remain outside this promotion.

## Frontier targets

- `skeleton/frontier/season_pass.py`
- `skeleton/testing/test_frontier_season_pass_policy.py`

## Promoted policy

The frontier module retains:

- deterministic source tier-XP formula;
- source free/premium tier reward schedule;
- contiguous tier topology validation;
- per-season progress identity;
- multi-tier XP rollover;
- XP-to-next-level calculation;
- free and premium claim idempotency;
- pure currency, inventory and unlock-item reward plans.

## Hardening over source behavior

### Premium entitlement boundary

The source purchase endpoint explicitly simulates a purchase and directly sets `is_premium=True`. The frontier kernel cannot grant a paid entitlement by itself. `activate_premium` requires an external boundary to pass `entitlement_verified=True`; payment/IAP verification remains an application-service responsibility.

### State normalization

Non-max progress cannot persist XP already at or above its current tier threshold. Large XP awards drain every crossed threshold in one transition, so downstream code cannot observe a stale level with already-earned rollover XP.

### Catalog binding

Progress carries a season-pass identity and fails closed if evaluated against a different season catalog. Tier levels must be contiguous and start at one.

### Claim integrity

Claims are represented as immutable state transitions. A tier above the current level cannot be claimed, premium rewards require premium entitlement, and already-claimed track/level pairs fail closed.

### Wallet-neutral reward plans

The policy does not mutate score, gems, bait, item collections or unlocked-item persistence. It returns explicit currency increments, inventory increments, or item unlocks for an application boundary to apply transactionally.

## Rejected from the kernel

- FastAPI and Pydantic request surfaces;
- Motor/MongoDB clients and collections;
- simulated IAP purchase records;
- USD price/payment-method handling;
- direct wallet/inventory mutations;
- current-season database discovery;
- lucky-wheel random sampling and spin persistence;
- duplicate daily-streak policy.

## Evidence

The focused frontier suite covers tier formulas and rewards, malformed tier topology, multi-level rollover, normalized XP state, unreached/duplicate claims, premium entitlement enforcement, premium item claims, season identity binding, and max-level XP behavior.
