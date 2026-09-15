# Encyclopedia Collection Promotion — 2026-09-15

## Source lineage

Fish collection policy is promoted once from the exact-shared source:

- `Apeloff1/Lorebuffa/backend/encyclopedia_routes.py`
  `e842d3697187503b1e1da2df3563d797777c6bfb`
- `Apeloff1/Openworld/backend/encyclopedia_routes.py`
  `e842d3697187503b1e1da2df3563d797777c6bfb`

The source file also owns a large fish catalog. That catalog is deliberately not
copied into Skeleton.

## Frontier targets

- `skeleton/frontier/encyclopedia.py`
- `skeleton/frontier/encyclopedia_adapters.py`
- stable gameplay facade aliases in `skeleton/frontier/gameplay.py`

## Promoted policy

- immutable discovered-fish identities;
- exact per-fish catch statistics (`caught`, `largest`, `smallest`, `first_caught`);
- first-discovery detection;
- catalog-independent completion percentage;
- source-compatible masking of undiscovered catalog records;
- deterministic total/largest/most-caught summaries;
- rarity aggregation against caller-owned fish→rarity mappings;
- canonical event/memory projection for fish discovery/catch transitions.

## Deliberate hardening over source behavior

### Collection identity consistency

`fish_stats` keys must exactly match `discovered_fish`. Persistence drift where a
fish is listed as discovered without statistics, or statistics exist for an
undiscovered fish, fails closed.

### Replay convergence

The source sets `first_caught` only on the request that first reaches MongoDB.
The promoted policy uses the earliest observed timezone-aware catch timestamp, so
out-of-order event replay converges to the same state.

### Finite positive measurements

Fish sizes must be finite positive numbers. Zero, negatives, booleans, NaN and
infinity cannot enter collection state.

### Deterministic aggregate ties

Largest/most-caught ties are resolved by sorted fish identity rather than source
mapping iteration order. Equivalent state therefore produces equivalent summary
output and digest material.

### Catalog boundary

Completion and rarity aggregation receive caller-owned catalog identities or
rarity mappings. Unknown discovered identities fail closed instead of silently
being omitted from statistics.

### Masking boundary

Undiscovered details are projected without mutating source catalog records.
Unavailable species mask name/description/facts; level-eligible but undiscovered
species retain the name while descriptive details stay hidden, matching source
intent.

### Event/memory integrity

Collection snapshots use canonical SHA-256 state digests and stable subject
identity. Events are allowlisted to `fish_discovered`/`fish_caught`, fully
rehydrate collection state, re-run key/size/time invariants, verify the referenced
fish exists in that state, and only then accept the digest for memory projection.
Recomputing a hash over malformed state is insufficient to bypass validation.

## Rejected from the frontier kernel

- `FISH_DATABASE` catalog content;
- scientific-name, habitat, bait, facts and presentation catalogs as package-owned data;
- FastAPI routers;
- MongoDB/Motor clients and collection persistence;
- user collection lookups;
- application response envelopes;
- search endpoint implementation tied to the source catalog;
- source rarity/habitat enumeration endpoints;
- duplicate journal/logbook primitives.

Source repositories remain authoritative for fish catalog content and persistence.

## Evidence

- `skeleton/testing/test_frontier_encyclopedia_policy.py`
- `skeleton/testing/test_frontier_encyclopedia_event_memory.py`
- `skeleton/testing/test_frontier_encyclopedia_gameplay_facade.py`
- `skeleton/testing/test_frontier_encyclopedia_benchmark.py`
- `scripts/benchmark_frontier_encyclopedia.py`

Correctness is gated. Benchmark latency is observational only.
