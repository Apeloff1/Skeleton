# Limited-Time Gameplay Event Promotion — 2026-09-15

## Source lineage

Limited-time/seasonal gameplay-event policy is promoted once from the exact-shared source:

- `Apeloff1/Lorebuffa/backend/event_routes.py`
  `6e7d62f7c5310374a3dad9cfdf22c1c28efc0cba`
- `Apeloff1/Openworld/backend/event_routes.py`
  `6e7d62f7c5310374a3dad9cfdf22c1c28efc0cba`

Skeleton already owns the canonical durable `DomainEvent` / `EventBus` transport.
This wave deliberately does not create another event transport.

## Frontier targets

- `skeleton/frontier/gameplay_events.py` — pure gameplay scheduling/progress/reward policy
- `skeleton/frontier/gameplay_event_adapters.py` — canonical DomainEvent/memory integrity boundary
- stable collision-free exports in `skeleton/frontier/gameplay.py`

## Promoted policy

- deterministic season selection from an injected date/datetime;
- explicit event duration windows using half-open `[start, end)` semantics;
- daily time restrictions including wraparound windows such as 20:00–06:00;
- immutable event participation state;
- additive nonnegative points, fish-catch and challenge progress;
- single-shot challenge completion;
- source reward normalization into event-token deltas plus the existing canonical `AchievementRewardPlan` for external rewards;
- deterministic next-milestone selection;
- wallet-neutral, idempotent milestone claim plans;
- validated event multipliers;
- canonical gameplay-event identity, specification digest, progress digest, DomainEvent projection and memory projection.

## Deliberate hardening over source behavior

### No duplicate event transport

The source calls these records “events”, but they are gameplay content rather than transport primitives. Frontier exports them only as `GameplayEvent*` policy and adapts transitions onto the existing `DomainEvent` surface. `EventBus` remains the sole durable event transport.

### Negative-delta rejection

The source accepts arbitrary integer progress deltas. Frontier rejects negative point, fish and challenge deltas so callers cannot roll counters backward or create reward-state ambiguity.

### Single-shot challenge rewards

A completed challenge is carried in immutable state and cannot award its reward again when later progress updates arrive.

### Milestone claim integrity

Milestones must be defined by the supplied event specification, reached by current points and not previously claimed. Claiming returns a plan rather than mutating user wallets, titles or inventory.

### Reward boundary reuse

Coins, gems, XP, titles, items and exclusive identifiers are normalized through the existing canonical achievement reward planner. Event tokens remain local to gameplay-event progress. No second wallet mutation implementation is promoted.

### Full spec/progress rehydration

The event/memory adapter serializes and rehydrates both the immutable event specification and participant progress before accepting SHA-256 digests. Boundary semantics additionally require:

- completed challenges exist in the specification and have reached their target;
- claimed milestones exist in the specification and do not exceed current points;
- no unknown challenge/milestone identifiers;
- valid finite positive multipliers;
- normalized identifiers and timezone-aware timestamps.

An attacker therefore cannot mark an unreached challenge/milestone complete merely by recomputing the outer digest.

### Time-window correctness

Event windows are half-open to avoid double-active boundary instants. Hour restrictions explicitly handle midnight wraparound and reject equal start/end hours rather than interpreting an ambiguous 24-hour window.

## Rejected from the frontier kernel

- source seasonal/special event catalogs as package-owned content;
- special-fish catalogs;
- event shop catalogs and purchase persistence;
- FastAPI routers and Pydantic request models;
- MongoDB/Motor clients and active-event/player-progress collections;
- direct user wallet mutation;
- player-title mutation;
- tacklebox/exclusive-fish persistence;
- inventory mutation;
- leaderboard queries and username enrichment;
- admin custom-event persistence;
- a duplicate `DomainEvent` or `EventBus` implementation.

Source repositories remain authoritative for content catalogs and application persistence.

## Evidence

- `skeleton/testing/test_frontier_gameplay_events_policy.py`
- `skeleton/testing/test_frontier_gameplay_event_memory.py`
- `skeleton/testing/test_frontier_gameplay_events_facade.py`
- `skeleton/testing/test_frontier_gameplay_events_benchmark.py`
- `scripts/benchmark_frontier_gameplay_events.py`

Correctness is gated. Benchmark latency remains observational only.
