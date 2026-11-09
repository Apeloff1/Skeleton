# Adaptive Absorption Fabric v2

## Goal

Increase **verified information absorbed per unit of compute** without allowing
absorption pressure to increase live inference latency or weaken epistemic safety.
The serving plane and absorption plane communicate through durable, one-way
contracts. Serving can emit telemetry; it cannot directly mutate durable knowledge.

The fabric is evolutionary, but its safety constitution is not. Routing weights,
lane budgets, verification *targets above the floor*, shadow allocation,
parallelism, and mutation amplitude may evolve. Provenance floors, contradiction
blocking, poisoning rejection, rollbackability, and serving isolation do not.

## Topology

```text
                               SERVING PLANE
                         immutable snapshot reader
                                  |       |
                                  |       +-- retrieval miss / uncertainty /
                                  |           stale hit / user correction
                                  |                     |
======================== HARD ORTHOGONAL BOUNDARY ========================
                                                        |
                                                durable outbox only
                                                        |
                                                        v
SOURCES --> event log --> normalize --> content identity --> novelty filter
                              |                 |               |
                              +-----------------+---------------+
                                                |
                                      adaptive priority mesh
                                                |
        +---------------+---------------+-------+-------+---------------+
        |               |               |               |               |
      FAST             DEEP        ADVERSARIAL      SPECULATIVE       REFRESH
        |               |               |               |               |
        +---------------+---------------+-------+-------+---------------+
                                                |
                                               GAP
                                                |
                                      claim/evidence compiler
                                                |
                              citation + provenance + independence
                                                |
                                         epistemic gate
                                                |
                                verified / contested / quarantine
                                                |
                                     candidate snapshot builder
                                                |
                             replay + benchmark + canary evaluation
                                                |
                                generational promotion arena
                                                |
                                 hash-rooted immutable snapshot
                                                |
================================ PROMOTION BARRIER ========================
                                                |
                                      serving snapshot pointer
```

## Six absorption lanes

**FAST** handles high-utility, high-confidence, low-risk material with cheap
normalization and deduplication. It is optimized for throughput, not permission to
skip the epistemic gate.

**DEEP** handles high novelty, uncertainty, multi-source synthesis, code/data
relationships, and material requiring richer entity/causal extraction.

**ADVERSARIAL** independently tries to disprove claims, detect source laundering,
find contradictions, identify poisoning, and stress provenance. Risk can force an
adversarial mirror even when another lane remains primary.

**SPECULATIVE** is a quarantine-first hypothesis lane. It may create research
tasks and falsification plans, but it cannot publish authoritative knowledge.

**REFRESH** revisits high-value stale knowledge, temporal validity, changed APIs,
policies, dependencies, and facts with expiry pressure.

**GAP** consumes only one-way serving telemetry such as retrieval misses, stale
hits, high uncertainty, and corrections. A gap task is an absorption request, not
a serving-memory write.

## Generational policy mesh

A production **champion** controls routing. A population of **challengers** receives
deterministically sampled mirrored events. Challengers run in shadow and cannot
publish snapshots or mutate the serving plane.

Each genome controls only evolvable policy:

- information-gain scoring weights;
- cost sensitivity;
- lane thresholds;
- shadow fraction;
- mutation scale;
- worker parallelism;
- a verification target that cannot go below the constitutional floor.

The hard envelope lives outside the genome. This prevents selection pressure from
rewarding a generation for becoming faster by quietly accepting weaker evidence.

### Evolution pressure

Evolution accelerates when there is environmental drift, performance stagnation,
or backlog pressure and slows when regression risk or epistemic uncertainty rises.
Conceptually:

```text
rate = clamp(
  base * (1 + drift + stagnation + backlog_pressure)
       / (1 + regression_risk + epistemic_uncertainty),
  minimum,
  maximum
)
```

The implementation uses weighted terms and increases both mutation amplitude and
the number of simultaneous challengers. The result is a higher evolutionary rate
without relaxing the promotion bar.

## Fitness is a vector, not a vanity score

Every generation is evaluated on a multi-objective vector:

- verified information gain;
- retrieval lift;
- verification rate;
- provenance completeness;
- contradiction catch rate;
- poison rejection rate;
- duplicate suppression;
- freshness;
- confidence calibration;
- cost efficiency;
- latency efficiency;
- serving regression.

Candidates that violate any hard floor are removed before comparison. Remaining
candidates are reduced to a Pareto frontier. The existing measured
`EvolutionPolicy` then decides whether a frontier candidate actually exceeds the
champion by enough to justify adoption.

This two-stage selection is intentional:

1. **constitutional filter** — cannot be traded away;
2. **Pareto filter** — cannot hide a severe weakness inside an average;
3. **measured adoption score** — chooses the best safe improvement.

## Evolution operators

### Bounded mutation

Weights and thresholds receive deterministic bounded perturbations derived from
the parent generation, challenger ordinal, and sequence. This makes experiments
replayable. Mutation amplitude increases with evolution pressure but is capped.
Verification targets are clamped to the hard invariant after every mutation.

### Crossover

Two successful non-archived lineages can be combined. Some parameters are
averaged; others are selected deterministically from one parent. Crossover output
is always a challenger and must repeat the full shadow evaluation path.

### Archive memory

Production deployment should persist failed lineage fingerprints with rejection
reasons. Mutation scheduling can then avoid repeatedly exploring equivalent bad
regions of policy space. This is an anti-loop memory, not authoritative knowledge.

## Claim lifecycle

```text
RAW
  -> NORMALIZED
      -> CLAIMED
          -> VERIFIED -> CANDIDATE -> PROMOTED
          -> CONTESTED -> VERIFIED | QUARANTINED | REVOKED
          -> QUARANTINED

PROMOTED -> CONTESTED | REVOKED
```

`VERIFIED`, `CANDIDATE`, and `PROMOTED` require an attestation. Illegal jumps fail
closed. Promotion therefore has an auditable chain instead of a mutable confidence
flag.

## Existing primitives reused

The fabric deliberately composes existing Skeleton primitives instead of replacing
them:

- `evolution_policy.py` — measured adoption and regression tolerances;
- `epistemic_gate.py` — citation binding, provenance normalization, source
  independence, and truth-verifier integration;
- `truth_verifier.py` — empirical evidence state and methodology-derived quality;
- `knowledge_fabric.py` — durable integrity-attested knowledge surfaces;
- `epistemic_checkpoint.py` — externally pinnable hash-chained state roots;
- `durable_outbox.py` — backpressured, cross-process durable boundary messages;
- source lineage / provenance / claim proof modules — evidence identity and audit.

## Snapshot contract

Serving should consume only immutable snapshot identifiers. A candidate snapshot
contains:

- parent snapshot root;
- generation id;
- sorted claim ids and attestations;
- provenance roots;
- policy/evaluator versions;
- benchmark and replay evidence ids;
- rollback snapshot id;
- deterministic manifest root.

Promotion is staged, replayed, benchmarked, canaried, checkpointed, and then moved
by an atomic pointer. Rollback moves the pointer to the previous immutable root;
it does not attempt to reverse individual memory writes.

## Isolation contract

The most important invariant is architectural rather than statistical:

1. serving never calls `KnowledgeFabric.publish()` as a consequence of a response;
2. serving can only append feedback to a durable outbox;
3. absorption workers consume feedback asynchronously;
4. shadow generations cannot create serving-visible snapshots;
5. only the promotion coordinator may stage an immutable snapshot activation;
6. snapshot activation must reference a rollback root and a pinned epistemic
   checkpoint;
7. overload backpressures absorption instead of stealing serving compute.

## Scheduling and resource control

Workers should use weighted fair queues across lane, domain, age, and value. The
priority signal is approximately expected information gain divided by estimated
compute cost. Global concurrency is split into reservations so a flood of cheap
FAST events cannot starve ADVERSARIAL or GAP work.

Recommended budget model:

```text
reserved adversarial capacity  >= 15%
reserved gap/refresh capacity  >= 10%
champion production capacity   <= 65%
challenger shadow capacity     dynamic, capped by remaining headroom
```

Unused reservations may be borrowed with leases, but they remain revocable when a
protected lane builds backlog.

## High-evolution operating mode

For rapid development, increase *parallel experiments*, not permission to publish:

- 6-12 challengers per champion under strong drift/stagnation;
- deterministic 10-25% event mirroring per challenger;
- bounded mutation amplitude up to roughly 0.35;
- crossover only from safe Pareto lineages;
- short shadow epochs for cheap routing metrics;
- longer evidence windows for promotion metrics;
- instant rejection on invariant breach;
- no reduction in minimum evidence or canary requirements.

This gives the system a high evolutionary clock rate while preserving a slow,
strict epistemic promotion clock.

## Success metric

The north-star measure is not raw bytes or tokens consumed:

```text
verified_information_gain
---------------------------------------------
compute_cost * epistemic_risk * serving_impact
```

Serving impact should remain effectively zero because all expensive acquisition,
verification, competition, and consolidation happens perpendicular to the live
inference path.
