# Biotope Achievement Adapter Promotion — 2026-09-15

## Source lineage

Biotope achievement definitions/signals are mined from one exact-shared source:

- `Apeloff1/Lorebuffa/backend/biotope_achievements_routes.py`
  `5a06312eebf8bb21fef28b1010dfc3ccff6b6500`
- `Apeloff1/Openworld/backend/biotope_achievements_routes.py`
  `5a06312eebf8bb21fef28b1010dfc3ccff6b6500`

Skeleton already owns the canonical achievement state machine, reward planner,
event projection, and memory projection. This wave therefore does **not** promote
a second achievement subsystem.

## Frontier target

- `skeleton/frontier/biotope_achievement_adapters.py`

It adapts source-shaped biotope achievement definitions and explicit gameplay
signals to `skeleton.frontier.achievements`.

## Promoted semantics

- nested source `rewards` normalization into canonical achievement rewards;
- `count` and trophy `size` thresholds normalized to one positive canonical target;
- source `biotope` and complex `each` semantics retained as validated metadata;
- per-biotope, per-stage and per-rarity catch statistics;
- trophy size represented as max-style state rather than an additive counter;
- explicit species-group signals for requirements such as bass/trout/sturgeon;
- cross-biotope `biotopes_fished` and `biotopes_mastered` signals derived from
  canonical `BiotopeProgress`;
- canonical `AchievementState`, `qualifies`, `unlock_qualified`, claim planning,
  `achievement_event`, and memory projection are reused unchanged.

## Source defects deliberately repaired

### Freshwater lake stat mismatch

The source catch recorder increments `freshwater_lake_catches`, while its lake
achievement definitions require `lake_catches`. The adapter maps canonical
`freshwater_lake` to source-compatible achievement alias `lake` so the definitions
can actually qualify.

### Lossy fish-ID prefix inference

The source derives a species counter from `fish.id.split("_")[0]`. That can map
multiword species to unrelated counters and couples qualification to the full fish
catalog. Frontier callers provide explicit normalized `species_groups` instead;
there is no string-prefix guessing.

### Ignored `each` requirement

`world_angler` declares `count=4, each=100`, but the source generic checker only
compares the scalar stat to `count` and ignores `each`. The frontier adapter derives
`biotopes_mastered` from canonical per-biotope catch counts using the validated
`each` threshold, so all four biotopes must actually meet 100 catches.

### Trophy semantics

Size requirements are tracked as a maximum measurement (`lake_trophy`) instead of
being accumulated as if centimeters were a catch count.

## Rejected from the frontier kernel

- `ALL_BIOTOPE_FISH` and `FISH_BY_BIOTOPE` registries;
- saltwater/lake/brackish/river fish databases;
- source achievement catalog constants as package-owned content;
- FastAPI routers and Pydantic request models;
- MongoDB/Motor clients and persistence;
- wallet XP/coin/gem mutation;
- player-title persistence;
- claim database updates;
- leaderboard/statistics endpoints;
- fish-ID prefix heuristics;
- a duplicate achievement state machine;
- a duplicate achievement event or memory model.

Source repositories remain authoritative for catalogs and application-service
persistence.

## Evidence

- `skeleton/testing/test_frontier_biotope_achievement_adapters.py`
- `skeleton/testing/test_frontier_biotope_achievement_benchmark.py`
- `scripts/benchmark_frontier_biotope_achievements.py`

Correctness is gated. Benchmark latency is observational only.
