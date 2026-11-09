# Guild policy promotion — 2026-09-15

## Source lineage

The guild/team subsystem was mined from an exact-shared source blob:

- `Apeloff1/Lorebuffa/backend/guild_routes.py` — `02bfb09c1c1b57b919aa0128c3ecf5f2eb94e41f`
- `Apeloff1/Openworld/backend/guild_routes.py` — `02bfb09c1c1b57b919aa0128c3ecf5f2eb94e41f`

The identical blob establishes one lineage surface, so it is promoted once rather
than copied twice.

## Promoted policy

`Skeleton/skeleton/frontier/guild.py` retains only portable domain semantics:

- immutable membership and exactly-one-leader invariants;
- source-compatible rank authority for application approval, kicking,
  promotion and leadership transfer;
- contribution accounting and contribution-point conversion;
- guild XP progression, level-derived capacity and level perks;
- bounded guild challenges with two-sided stake escrow and deterministic
  progress/payout plans.

## Hardening/evolution

The source implementation mixed persistence mutations with policy and had a few
important gaps. The promoted kernel deliberately tightens them:

1. Member count and capacity are derived from canonical member state and level,
   rather than trusting a separately mutable `member_count` field.
2. Exactly one member must have `rank=leader`, and that identity must match
   `leader_id`.
3. The source rank table's contribution thresholds are enforced during
   promotion instead of remaining dead configuration.
4. Contribution types are allow-listed; arbitrary treasury field injection is
   rejected.
5. Large contributions drain every crossed XP threshold in one pure transition,
   instead of leaving a guild temporarily above its next-level threshold.
6. Challenge duration is bounded to seven days and challenge types are
   allow-listed.
7. Challenge acceptance preflights both treasuries before returning either
   debit, eliminating one-sided stake mutation at the policy boundary.
8. Accepted challenges are explicitly marked as escrow-funded before progress
   can be recorded.
9. `biggest_fish` challenges use max semantics instead of additive progress.
10. Challenge completion returns a payout plan; the frontier kernel never
    mutates a wallet/persistence provider directly.

## Deliberately left source-owned

- FastAPI routes and Pydantic request models
- Motor/MongoDB clients and collections
- guild search/leaderboard queries
- guild chat storage and pagination
- usernames, icons, banners and presentation metadata
- application persistence and notification delivery
- wallet/resource persistence

## Evidence

- `skeleton/testing/test_frontier_guild_policy.py`
- Frontier Contracts workflow compiles `skeleton/frontier` and runs all
  `skeleton/testing/test_frontier_*.py` tests on the frontier branch.
