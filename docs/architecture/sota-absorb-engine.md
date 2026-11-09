# SOTA Absorb Engine

## Mission
Build an orthogonal knowledge-absorption plane that can ingest, validate, compress, contest, retract, and promote high-value information without putting ingestion work on the live inference path.

## Design principles
- **Orthogonal execution:** ingestion, verification, compaction, and promotion run independently from inference.
- **Append-only intake:** every observation is durably journaled before expensive processing.
- **Multi-lane processing:** fast-path normalization and deep semantic/adversarial analysis execute concurrently.
- **Information gain over volume:** prioritize novelty, relevance, evidence quality, and expected utility per unit compute.
- **Independent-source consensus:** repeated evidence from one source cannot manufacture consensus; source influence is de-duplicated per claim.
- **Calibrated provenance:** declared source trust is combined with an online reliability posterior learned from adjudicated outcomes.
- **Retractions are first-class:** invalidated knowledge becomes fail-closed immediately and cannot satisfy the challenge gate.
- **Adversarial promotion:** candidate knowledge must survive contradiction, integrity, freshness, provenance, and challenge checks before becoming queryable truth.
- **Immutable snapshots:** serving reads promoted manifests, never mutable in-flight state.
- **Rollback by construction:** every promotion yields a versioned manifest that can be atomically reverted.
- **Backpressure aware:** intake can defer or downgrade low-value work before it harms serving SLOs.

## Plane architecture

```text
Sources
  -> Durable Intake Journal
      -> Fast Lane: normalize -> fingerprint -> exact/near dedupe -> metadata
      -> Deep Lane: entities -> semantic graph -> temporal/causal links -> novelty
      -> Challenge Lane
           -> claim ledger
           -> independent-source consensus
           -> source reliability calibration
           -> contradiction / integrity / freshness
           -> retraction state
          -> Fusion + Confidence Calibration
              -> Memory Tiers
                  L0 Raw Events
                  L1 Parsed Observations
                  L2 Verified Facts
                  L3 Knowledge Graph
                  L4 Distilled Concepts
                  L5 Operational Models
                      -> Promotion Gate
                          -> Immutable Knowledge Snapshot
                              -> post-promotion RAG sink
                                  -> Serving Plane
```

## Priority model

```text
priority = (
    novelty * 0.25 +
    relevance * 0.20 +
    information_gain * 0.20 +
    evidence_quality * 0.15 +
    urgency * 0.10 +
    downstream_utility * 0.10
) / max(estimated_compute_cost, epsilon)
```

The score is deliberately compute-normalized: more bytes are not better unless they add usable information. High-value, cheap-to-evaluate evidence can overtake low-value bulk ingestion.

## Claim consensus model
Knowledge is represented as claims with source-de-duplicated evidence votes. Each source contributes at most one effective stance for a claim, preventing retry storms or repeated ingestion from amplifying one source into false consensus.

Source reliability uses a conservative Beta posterior. Adjudicated correct/incorrect outcomes update that posterior, and the verifier combines calibrated historical reliability with declared provenance trust. Claims can be active, contested, or retracted.

For high-impact knowledge, the challenge gate requires multiple independent sources, bounded contradiction, and a non-retracted claim. Retractions return zero confidence, maximum contradiction, zero freshness, and maximum integrity risk so they fail closed.

## Promotion contract
A candidate is promotable only when all mandatory gates pass:
1. provenance attached;
2. contradiction score below threshold or explicitly reconciled;
3. integrity/risk score below threshold;
4. confidence above the tier-specific threshold;
5. freshness policy satisfied;
6. duplicate ratio below the compaction limit;
7. high-impact claims satisfy independent-source challenge requirements;
8. claim is not retracted;
9. promotion snapshot can be reproduced from journal offsets.

## Concurrency model
Use independently scalable worker pools keyed by stage. The runtime controller exposes a batch budget based on serving pressure and backlog. Under high serving pressure, absorption drops to its minimum batch; under large backlog and low serving pressure it can burst. CPU/domain processing runs off the request event loop.

Autoscaling decisions should eventually use queue lag *and* marginal information gain, not queue depth alone.

## Serving isolation
`submit()` performs only bounded validation, append-only journaling, cheap novelty inspection, priority calculation, and queueing. It never promotes directly.

Serving consumes only immutable `knowledge-snapshot-vN` state. Promotion is an atomic pointer swap. `RagMemory` receives only entries from a successfully published snapshot; deferred and quarantined observations never enter live retrieval through this path.

No request thread is allowed to block on deep ingestion, semantic analysis, graph construction, adversarial verification, compaction, or snapshot publication.

## Failure behavior
- Intake journal unavailable: fail closed for durable absorption, preserve serving.
- Deep lane unavailable: continue fast normalization, mark candidates unverified.
- Challenge lane unavailable: block high-impact promotion, not intake.
- Snapshot publish failure: retain previous snapshot.
- Corrupt or high-risk candidate: quarantine with provenance and reason.
- Retracted claim: fail closed regardless of prior confidence.
- Excessive serving pressure: reduce absorb batch budget before consuming serving capacity.
- Excessive backlog: burst only when serving pressure is low.

## Metrics
- submitted observations
- journal replay count
- exact duplicate count
- near duplicate count
- processed candidates
- promoted candidates
- deferred candidates
- quarantined candidates
- challenge-routed candidates
- compute spent
- accumulated information gain
- knowledge gain per compute
- snapshot version / digest

Production adapters should additionally export queue lag, lane latency, source-calibration drift, consensus depth, retraction count, promotion latency, serving snapshot age, and rollback count.

## Production adapter boundary
The domain implementation is dependency-light on purpose. The following can be replaced without changing the promotion contract:
- in-memory journal -> Kafka, NATS JetStream, Redis Streams, Postgres WAL/event table, or equivalent durable log;
- token novelty index -> embedding/ANN semantic novelty index;
- synchronous verifier -> verifier ensemble / model-based challenger;
- in-memory snapshots -> object store + transactional manifest pointer;
- in-process runtime -> dedicated worker service / autoscaled consumer group;
- in-memory RAG sink -> canonical vector/graph serving stores.

## Next evolution
The next frontier is not simply more ingestion throughput. It is increasing **verified information gain per unit compute** while reducing epistemic error. The subsystem is ready to evolve toward speculative parallel parsing, learned stage routing, semantic cache reuse, graph-aware retrieval synthesis, temporal decay, claim supersession graphs, replay-based evaluators, canary knowledge snapshots, and learned scheduling without changing the serving boundary.
