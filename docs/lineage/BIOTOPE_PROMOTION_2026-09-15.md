# Biotope Progression Promotion — 2026-09-15

## Source lineage

Biotope progression is promoted exactly once from the byte-identical source implementation:

- `Apeloff1/Lorebuffa/backend/biotope_routes.py`
  `b79a167a3b568477e7db1fa95d64fc3949171a7e`
- `Apeloff1/Openworld/backend/biotope_routes.py`
  `b79a167a3b568477e7db1fa95d64fc3949171a7e`

The two repositories therefore provide one lineage source, not two independent frontier primitives.

## Frontier targets

- `skeleton/frontier/biotope.py` — canonical dependency-free progression policy
- `skeleton/frontier/biotope_adapters.py` — event/memory integrity boundary
- `skeleton/testing/test_frontier_biotope_policy.py` — progression, topology, and stage-identity correctness
- `skeleton/testing/test_frontier_biotope_event_memory.py` — persistence-boundary integrity
- `skeleton/testing/test_frontier_biotope_benchmark.py` — observational benchmark correctness
- `scripts/benchmark_frontier_biotope.py` — observational workload

## Promoted policy

The frontier core retains only portable behavior:

- level-gated biotope unlocks;
- explicit boat requirements;
- stage-one seeding when a biotope is unlocked;
- sequential stage progression;
- deterministic unlockable-biotope and unlockable-stage queries;
- active biotope/stage selection;
- per-biotope mastery XP and fish-catch accounting;
- deterministic mastery bonuses for catch rate, rare chance, XP and coins;
- immutable progress snapshots and normalized identifiers.

## Deliberate hardening over source behavior

### Stage topology validation

Stage catalogs fail closed on duplicate stage identifiers, duplicate stage numbers, gaps, or progression that does not begin at stage one. A caller cannot use an ambiguous or malformed stage graph to bypass sequential progression.

### Canonical stage identity binding

Active-stage entry is bound to the supplied canonical stage catalog. The requested `BiotopeStageSpec` must exactly match the catalog entry for its identifier and its target-biotope topology must validate before location state changes. A caller therefore cannot reuse a globally unlocked stage identifier and rebind it to another unlocked biotope to create an inconsistent active stage/biotope pair. The adversarial regression in `test_frontier_biotope_policy.py` covers this cross-biotope identity-rebinding attempt.

### Sequential unlock enforcement

A stage must belong to an unlocked biotope, satisfy its player-level requirement, and follow the preceding stage. Unlockable-stage discovery uses the same policy instead of maintaining a second eligibility implementation.

### Boat gating

Biotopes that declare `required_boat` cannot be unlocked merely because the player level is high enough. The requirement is explicit input to the pure policy and is never inferred from framework state.

### Mastery rollover

The source endpoint checks one mastery threshold per request. The promoted policy drains every crossed threshold so a large but valid XP award cannot leave a stale mastery level with XP already beyond subsequent thresholds.

### Progress integrity boundary

`biotope_adapters.py` binds progress state to the existing frontier `DomainEvent` and memory surfaces without adding a second progression engine. It adds:

- stable subject identity via canonical SHA-256 digest;
- canonical progress payload/digest;
- allowlisted biotope transition topics;
- fail-closed event-state reconstruction;
- exact progress-map coverage for every unlocked biotope;
- mastery XP residue validation (`xp < level * 100`);
- paired active-biotope/active-stage presence;
- event→memory projection with unlock, stage, catch and mastery evidence.

An attacker cannot make malformed progress trustworthy simply by recomputing its digest: the payload is reconstructed and the stronger boundary invariants run before the digest is accepted.

## Rejected from the frontier kernel

- `BIOTOPES` and `BIOTOPE_STAGES` source catalogs;
- fish pools, rare pools and legendary pools;
- descriptions, icons, tips, colors and other presentation content;
- FastAPI routers and Pydantic request models;
- MongoDB/Motor clients and collection access;
- user collection lookups;
- leaderboard queries and persistence;
- database update operators;
- application response envelopes;
- framework-specific HTTP error mapping.

Source repositories remain authoritative for catalogs and application-service persistence.

## Evidence policy

Correctness is gated. Benchmark timing is observational only and must not become a machine-dependent merge threshold.
