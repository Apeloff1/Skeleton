# SOTA Absorb Engine

## Mission
Build an orthogonal knowledge-absorption plane that can ingest, validate, compress, and promote high-value information without putting ingestion work on the live inference path.

## Design principles
- **Orthogonal execution:** ingestion, verification, compaction, and promotion run independently from inference.
- **Append-only intake:** every observation is durably journaled before expensive processing.
- **Multi-lane processing:** fast-path normalization and deep semantic/adversarial analysis execute concurrently.
- **Information gain over volume:** prioritize novelty, relevance, evidence quality, and expected utility per unit compute.
- **Adversarial promotion:** candidate knowledge must survive contradiction, poisoning, freshness, and provenance checks before becoming queryable truth.
- **Immutable snapshots:** serving reads promoted manifests, never mutable in-flight state.
- **Rollback by construction:** every promotion yields a versioned manifest that can be atomically reverted.
- **Backpressure aware:** intake can shed, defer, or downgrade low-value work before it harms serving SLOs.

## Plane architecture

```text
Sources
  -> Durable Intake Journal
      -> Fast Lane: normalize -> fingerprint -> exact/near dedupe -> metadata
      -> Deep Lane: entities -> semantic graph -> temporal/causal links -> novelty
      -> Red Team Lane: contradiction -> poisoning -> freshness -> provenance
          -> Fusion + Confidence Calibration
              -> Memory Tiers
                  L0 Raw Events
                  L1 Parsed Observations
                  L2 Verified Facts
                  L3 Knowledge Graph
                  L4 Distilled Concepts
                  L5 Operational Models
                      -> Promotion Gate
                          -> Immutable Knowledge Manifest
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

The score is deliberately compute-normalized: more bytes are not better unless they add usable information.

## Promotion contract
A candidate is promotable only when all mandatory gates pass:
1. provenance attached;
2. contradiction score below threshold or explicitly reconciled;
3. poisoning/risk score below threshold;
4. confidence above the tier-specific threshold;
5. freshness policy satisfied;
6. semantic duplicate ratio below the compaction limit;
7. promotion manifest can be reproduced from journal offsets.

## Concurrency model
Use independently scalable worker pools keyed by stage. The controller should expose target concurrency, lag, rejection rate, dedupe rate, promotion rate, and estimated information gain per second. Autoscaling decisions should use queue lag *and* marginal information gain, not queue depth alone.

## Serving isolation
Serving consumes only immutable `knowledge-manifest-vN` snapshots. Promotion is an atomic pointer swap. No request thread is allowed to block on ingestion, embedding, graph construction, verification, or compaction.

## Failure behavior
- Intake journal unavailable: fail closed for durable absorption, preserve serving.
- Deep lane unavailable: continue fast normalization, mark candidates unverified.
- Red-team lane unavailable: block promotion, not intake.
- Snapshot publish failure: retain previous manifest.
- Corrupt candidate: quarantine with provenance and reason.
- Excessive lag: degrade low-priority semantic work before high-value evidence.

## Metrics
- ingest_events_total
- ingest_bytes_total
- journal_lag_seconds
- exact_dedupe_ratio
- semantic_dedupe_ratio
- candidate_information_gain
- adversarial_rejection_ratio
- promotion_success_ratio
- promotion_latency_seconds
- knowledge_gain_per_compute_second
- serving_snapshot_age_seconds
- rollback_total

## Next evolution
The subsystem is designed to support speculative parallel parsing, adaptive stage routing, semantic cache reuse, graph-aware retrieval synthesis, source-reliability learning, replay-based evaluators, and learned scheduling without changing the serving boundary.
