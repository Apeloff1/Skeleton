# Jeeves Hyperdispatcher competitive campaign — wave 1

Status: source implementation, review only; not deployment or measured superiority.
Canonical owners: existing intelligence admission/pressure, engine coordinator,
automation secretary and native inference admission. No second runtime, queue DB,
provider, worker credential or cross-plane authority has been added.

Wave 1: existing shared-pressure ledger gains opt-in atomic ranked promotion and
logical gang promotion. Pure deterministic ranking, exact rational tenant share,
priority aging with protected lanes, deadline slack, critical path, data affinity,
resource vectors, bounded placement search and conservative backfill proposals.
A worker must receive exact queue tickets through the existing trusted authority.
Legacy callers do not automatically switch to ranked or gang admission; physical
allocation, execution, cancellation and outcome custody remain with their owners.
A promotion receipt lost in transit requires checking the current operation lease;
do not blindly retry an unknown side effect. Fresh lease IDs fence new ranked/gang
attempts; legacy lease paths still need a separate compatibility migration.

## Competitive research register

Primary research sources (independent implementation, no copied code):
- Temporal: https://docs.temporal.io/tasks — event history, task polling, heartbeats.
- Ray: https://docs.ray.io/en/latest/ray-core/scheduling/placement-group.html — atomic placement groups.
- Ray: https://docs.ray.io/en/latest/ray-core/scheduling/ — locality and resource selection.
- Kueue: https://kueue.sigs.k8s.io/docs/concepts/preemption/ — fair-share and quota borrowing.
- vLLM: https://docs.vllm.ai/en/latest/design/arch_overview/ — token-budget dispatch.

Additional research targets (not yet independently verified in this wave):
Celery, Volcano, Slurm, HTCondor, LangGraph, AutoGen, Hatchet, Airflow, Argo,
Dask, NATS JetStream, Kafka, SGLang, RabbitMQ, Prefect, Dagster, Luigi, Dramatiq,
RQ, BullMQ, Conductor OSS, Kestra, CrewAI, OpenHands, Open MPI, Flink, Kubernetes,
Apache Mesos (historical); additionally Dapr, Nomad, Taskiq, Huey, Kubernetes
scheduler framework, Apache Spark, Redis Streams, ONNX Runtime, Triton Inference
Server, text-generation-inference, llama.cpp, OpenTelemetry, OpenFGA and OPA.

## Acceptance inventory

Each target requires source, canonical wiring, focused regression, fault injection
where applicable, exact-head checks, and matched performance evidence where claimed.
"P" means partial implementation in this source wave, not completed.

| ID | Target | Source status |
|---|---|---|
| 01 | Dynamic priority | P |
| 02 | Earliest deadline first | P |
| 03 | Critical path scheduling | P |
| 04 | Weighted fair queuing | P |
| 05 | Hierarchical resources | Open |
| 06 | Predictive backfill | P |
| 07 | Deadline preemption | Open |
| 08 | Atomic gang scheduling | P |
| 09 | Work stealing | Open |
| 10 | Speculative execution | Open |
| 11 | Capability matchmaking | P |
| 12 | Task fusion | Open |
| 13 | Dynamic decomposition | Open |
| 14 | Starvation prevention | P |
| 15 | Adaptive batching | Open |
| 16 | Semantic classification | Open |
| 17 | Model-directed worker selection | Open |
| 18 | Specialist discovery | Open |
| 19 | Reasoning complexity estimation | Open |
| 20 | Uncertainty routing | Open |
| 21 | Multi-model delegation | Open |
| 22 | Adversarial verification | Open |
| 23 | Recursive decomposition | Open |
| 24 | Parallel hypotheses | Open |
| 25 | Historical-success routing | Open |
| 26 | Learned cost prediction | Open |
| 27 | Context affinity | Open |
| 28 | Mission replanning | Open |
| 29 | Tool-chain optimization | Open |
| 30 | Redundant reasoning elimination | Open |
| 31 | CPU/GPU balancing | Open |
| 32 | Unified memory | Open |
| 33 | NUMA placement | Open |
| 34 | GPU topology | Open |
| 35 | Thermal scheduling | Open |
| 36 | Energy scheduling | Open |
| 37 | Bandwidth optimization | Open |
| 38 | Model preloading | Open |
| 39 | KV affinity | Open |
| 40 | Prefill/decode separation | Open |
| 41 | Token-level admission | Open |
| 42 | Cross-device migration | Open |
| 43 | Pressure relief | Open |
| 44 | Storage-aware dispatch | Open |
| 45 | Heterogeneous accelerators | Open |
| 46 | Event-sourced execution | Open |
| 47 | Deterministic replay | Open |
| 48 | Partitioned journals | Open |
| 49 | Distributed lease fencing | P |
| 50 | Idempotent side effects | Open |
| 51 | Transactional publication | Open |
| 52 | Compensation | Open |
| 53 | Deadlock detection | Open |
| 54 | Checkpoint recovery | Open |
| 55 | Poison quarantine | Open |
| 56 | Retry budgets | Open |
| 57 | Failure prediction | Open |
| 58 | Split brain prevention | Open |
| 59 | Journal compaction | Open |
| 60 | Version migration | Open |
| 61 | Shadow scheduling | Open |
| 62 | Counterfactual scheduling | Open |
| 63 | Negative capability cache | Open |
| 64 | Speculative reservations | Open |
| 65 | Dependency collapse | Open |
| 66 | Execution locality | P |
| 67 | Failure-domain isolation | Open |
| 68 | Uncertainty-sensitive scheduling | P |
| 69 | Semantic deduplication | Open |
| 70 | Cross-domain lending | Open |
| 71 | Scheduler portfolios | Open |
| 72 | Virtual workers | Open |

## Wave 2: advisory routing and counterfactual evaluation

SGLang-inspired cache vs queue-aware routing uses exact model/tokenizer and tenant
identity, fresh generation-tagged worker observations and full token reservations.
Dask-inspired work stealing proposals reject running work and unprofitable moves.
NATS-style bounded failure handling differentiates proven no-effect retries from
unknown side effects, which always require reconciliation. An empirical duration
estimator gives conservative order-statistic predictions, and a finite discrete
event simulation compares FIFO, priority, shortest, fair aging and deadline
policies by deadline misses and waiting distributions. Source traces are hashed;
they are not observed production benchmarks or automatic policy promotion.

Research:
- https://distributed.dask.org/en/stable/work-stealing.html
- https://github.com/nats-io/nats.docs/blob/master/nats-concepts/jetstream/consumers.md
- https://github.com/sgl-project/sglang/blob/main/sgl-model-gateway/src/policies/cache_aware.rs

Additional partial source targets: 09 (stealing proposal), 26 (empirical
duration prediction), 39 (cache-aware routing), 41 (token reservation proposal),
55 (quarantine decision), 56 (retry budget), 61 and 62 (shadow/counterfactual),
68 (uncertainty margin), 71 (portfolio comparison). Actual worker transfer,
inference cache proof, broker persistence, learned production routing, durable
acknowledgment and policy activation remain open.

## Qualification and rollback

Run the focused test file, existing shared pressure tests, and every AGENTS.md
architecture/enterprise validator, mirror/source parity and exact-head CI.
Include contending processes, crash after commit before receipt, busy database,
clock jumps, cross-tenant denial, stale ticket and lease rejection, actual physical
workers, and pressure tests. No physical capacity or latency claim from this wave.
Logical group slots are not Ray-style distributed physical allocation. Ranking
currently scans a bounded authorized set; scale qualification and indexed next
selection are follow-up work. Roll back the whole reviewed commit; no schema
migration was introduced. Existing queue rows and callers remain compatible.
