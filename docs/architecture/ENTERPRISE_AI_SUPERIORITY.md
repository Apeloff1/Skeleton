# Enterprise AI Superiority Standard

Machine authority: `machine/enterprise_ai_superiority.json`

This standard changes the meaning of completion for Skeleton AI.

A volume is not complete because a class exists, tests pass, or a feature can be
demonstrated. A production AI volume is complete only when it is operationally
safe, recoverable, observable, governable, and competitive against a declared
baseline. A volume described as **superior** must have reproducible evidence
that it dominates that baseline without paying for the win by weakening a
non-compensable property.

## 1. The five maturity levels

1. **designed** — ownership, contracts, comparator, target metrics, budgets,
   failure behavior and qualification evidence are specified.
2. **implemented** — canonical runtime behavior exists and focused correctness
   tests pass.
3. **hardened** — negative, adversarial, concurrency, saturation and recovery
   behavior is executable and tested.
4. **enterprise_qualified** — exact-head SLO, security, privacy, tenant,
   recovery, operability and rollback evidence passes.
5. **superior** — enterprise-qualified plus a reproducible comparator study
   proves the declared dominance rule.

These are different axes from the legacy implementation status. Existing
`implemented`, `hardened` or `verified` state never automatically upgrades
the enterprise grade.

## 2. What "outperform" means

Outperformance is not synonymous with benchmark speed.

A standard AI layer may be easy to build because it delegates hidden failure,
security and recovery costs to operators. Skeleton wins only when the complete
system outcome is better.

A dedicated superiority profile therefore declares:

- the conventional baseline being beaten;
- the primary user/operator/system outcome;
- at least three measurable dominance targets;
- hard gates that cannot be traded away;
- the exact evidence required to promote.

For an intelligence layer, at least one win must represent quality/correctness
or task success. For serving/control layers, a primary win may instead be a
strict reliability, recovery, throughput, utilization or operational result.
Security/privacy/authority regressions are never acceptable tradeoffs.

## 3. Non-compensable properties

No amount of quality, latency or cost improvement can compensate for:

- a critical security regression;
- cross-tenant or cross-user disclosure;
- an unauthorized privileged side effect;
- loss of an acknowledged authoritative write;
- unbounded retry, recursion, delegation or background execution;
- secret material escaping its declared boundary;
- weaker privacy/residency policy during fallback;
- production behavior with no tested rollback/reference path when rollback is
  applicable;
- an enterprise/superiority claim without exact-head evidence.

An inapplicable hard gate requires a machine-readable rationale. Silence does
not mean "not applicable."

## 4. Comparison discipline

Candidate and baseline comparisons bind the identities of:

- source/git head;
- baseline artifact/head;
- policy and contract versions;
- workload/evaluation dataset;
- model/provider/inference settings;
- hardware/runtime/environment;
- scorer/evaluator;
- cost/resource budget;
- raw results;
- verifier and verdict.

If those identities are not comparable, the benchmark does not establish
superiority.

Use paired deterministic comparisons where possible. Stochastic comparisons
must report uncertainty. Median-only speed wins are insufficient: tail latency,
saturation, recovery and fault behavior matter.

## 5. Standard AI layers Skeleton is explicitly designed to beat

The dedicated profiles cover the critical production path.

### Execution and state

The baseline is a conventional async AI service with process-local task state,
best-effort cancellation and loosely separated cache/authority state.

Skeleton targets durable operation identity, cancellation propagation, zero
orphan privileged work, deterministic state ownership, RPO-zero semantics for
acknowledged operations and verified restore.

### Inference and routing

The baseline is a single-provider inference wrapper plus static fallback.

Skeleton targets a better latency/throughput frontier while preserving semantic
correctness, plus route decisions that jointly optimize capability, quality,
privacy, reliability, latency and cost. Fallback may never weaken privacy or
residency.

### Context

The baseline is flat prompt concatenation followed by token-limit truncation.

Skeleton targets materially higher task utility per token while preserving
policy and provenance. Untrusted retrieved/tool/memory content can never evict
mandatory policy.

### Memory

The baseline is embedding-backed conversational memory with heuristic writes.

Skeleton targets scoped durable memory with contradiction handling, current
truth/freshness checks, lifecycle propagation, deterministic recovery and zero
cross-user/tenant leakage.

### Retrieval

The baseline is single-stage vector RAG with post-filter authorization.

Skeleton targets authorization-before-ranking, hybrid/temporal/graph/code
retrieval, materially higher answer-support recall, high evidence precision and
explicit freshness/provenance.

### Cognition and planning

The baseline is a single prompt or unverified linear plan.

Skeleton targets bounded strategy selection, calibrated abstention,
evidence-backed verification, DAG planning, static validation, recovery-aware
replanning and materially better task completion at a fixed model/tool budget.

### Tools and actions

The baseline is model-direct tool calling with schema validation.

Skeleton treats tools as privileged transactions. It targets zero unauthorized
execution, zero retry-induced duplicate side effects, verified postconditions,
idempotency/compensation semantics and durable receipts.

### Agents and autonomy

The baseline is an ephemeral agent loop with heuristic delegation and stopping.

Skeleton targets durable checkpoints, leases/fencing, mechanical authority
subsetting, bounded fan-out/retries, process-failure recovery and materially
higher long-horizon completion.

### Multimodal intelligence

The baseline is provider-native multimodal prompting with weak cross-modal
provenance.

Skeleton targets typed modalities, source identity, cross-modal retrieval,
malformed-media bounds and resistance to hidden instructions embedded in
documents/images/audio/video.

### Code and repository intelligence

The baseline is text search plus patch/test.

Skeleton targets graph-aware ownership/impact analysis, leased mutation,
transactional workspace behavior, independent review, lower regression rate,
higher verified repair success and complete patch provenance.

### Safety, cybersecurity, privacy and governance

The baseline is prompt-level safety plus conventional web/API controls.

Skeleton targets independent policy enforcement, zero-trust execution,
tenant-safe data paths, secret isolation, end-to-end data lifecycle, revocable
delegation and replayable privileged decisions.

### Reliability and distributed execution

The baseline is retry/circuit-breaker horizontal scaling.

Skeleton targets bounded retry amplification, semantic-aware unknown outcomes,
fenced worker ownership, topology-aware scheduling, explicit load shedding and
fault-campaign evidence.

### Observability and evaluation

The baseline is traces/metrics plus an aggregate task benchmark.

Skeleton targets reconstructable operation graphs spanning model, retrieval,
tools, state, cost and evidence; contamination-aware reproducible evaluation;
adversarial coverage; and promotion decisions that cannot self-verify.

### Product, streaming and tenancy

The baseline is request/response chat UX and tenant filtering.

Skeleton targets resumable operation state machines, sequence-aware streaming,
reconnect, cancellation, accessibility, tenant isolation across caches/vector
stores/tools/telemetry and quota isolation under noisy-neighbor load.

### Advanced serving

The baseline is generic multi-worker model serving using framework-default
batching/caching/resource behavior.

Skeleton targets topology-aware model placement, admission-reserved GPU memory,
safe warming/eviction, continuous batching, KV/prefix reuse, speculative
inference, forecast-aware autoscaling and strictly profile-gated acceleration.

### Economics, rights and lifecycle

The baseline is token-cost reporting and manual release governance.

Skeleton targets pre-admission budgets, operation/tenant cost attribution,
forecasting, anomaly detection, machine-readable rights/attribution, evidence-
gated model/provider migration, shadow traffic, champion/challenger promotion
and deterministic rollback.

## 6. Enterprise scorecard

Every volume inherits the complete scorecard:

- functional correctness and task quality;
- security and abuse resistance;
- privacy, governance and tenant isolation;
- latency and tail latency;
- throughput and saturation;
- cost and resource efficiency;
- reliability and safe degradation;
- recovery, replay and rollback;
- observability and auditability;
- compatibility and migration;
- operator control and supportability.

A volume may not optimize only the metric that makes it look good.

## 7. Fault qualification

Enterprise qualification includes the applicable fault campaign:

- dependency unavailable;
- dependency slow or partial;
- process crash before/after durable commit;
- duplicate/replayed request;
- cancellation during expensive work;
- saturation/backpressure;
- stale worker/evidence;
- malformed, oversized or untrusted input;
- credential/policy/tenant mismatch;
- rollback/reference fallback.

The campaign should inject failures at architectural boundaries, not just mock
a return code inside the happy path.

## 8. Promotion and expiration

Enterprise evidence is exact-head evidence.

A profile that changes governed source, comparator policy, scorer, security
boundary or acceptance rule becomes stale and must be requalified. Promotion is
not a permanent badge.

A candidate may be:

- functionally implemented and still not enterprise-qualified;
- enterprise-qualified and still not superior;
- superior for one workload/environment and unqualified for another declared
  operating envelope.

The machine policy is authoritative about which statement is valid.

## 9. Complete-enterprise-AI claim

Skeleton may be described as a complete enterprise AI only when:

1. every production-path volume satisfies the common enterprise contract;
2. every dedicated critical profile is at least `enterprise_qualified`;
3. each dedicated profile required for competitive superiority reaches
   `superior`;
4. the end-to-end golden journeys pass with production-like identity,
   authorization, state, provider, retrieval, tool, artifact, streaming,
   recovery and rollback behavior;
5. no open critical security/privacy/tenant/state-loss gap remains;
6. exact-head release evidence is current.

Until then the honest status is **enterprise construction in progress**.
