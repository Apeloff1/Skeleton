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
| 05 | Hierarchical resources | P |
| 06 | Predictive backfill | P |
| 07 | Deadline preemption | P |
| 08 | Atomic gang scheduling | P |
| 09 | Work stealing | P |
| 10 | Speculative execution | P |
| 11 | Capability matchmaking | P |
| 12 | Task fusion | P |
| 13 | Dynamic decomposition | P |
| 14 | Starvation prevention | P |
| 15 | Adaptive batching | P |
| 16 | Semantic classification | P |
| 17 | Model-directed worker selection | P |
| 18 | Specialist discovery | P |
| 19 | Reasoning complexity estimation | P |
| 20 | Uncertainty routing | P |
| 21 | Multi-model delegation | P |
| 22 | Adversarial verification | P |
| 23 | Recursive decomposition | P |
| 24 | Parallel hypotheses | P |
| 25 | Historical-success routing | P |
| 26 | Learned cost prediction | P |
| 27 | Context affinity | P |
| 28 | Mission replanning | P |
| 29 | Tool-chain optimization | P |
| 30 | Redundant reasoning elimination | P |
| 31 | CPU/GPU balancing | P |
| 32 | Unified memory | P |
| 33 | NUMA placement | P |
| 34 | GPU topology | P |
| 35 | Thermal scheduling | P |
| 36 | Energy scheduling | P |
| 37 | Bandwidth optimization | P |
| 38 | Model preloading | P |
| 39 | KV affinity | P |
| 40 | Prefill/decode separation | P |
| 41 | Token-level admission | P |
| 42 | Cross-device migration | P |
| 43 | Pressure relief | P |
| 44 | Storage-aware dispatch | P |
| 45 | Heterogeneous accelerators | P |
| 46 | Event-sourced execution | P |
| 47 | Deterministic replay | P |
| 48 | Partitioned journals | P |
| 49 | Distributed lease fencing | P |
| 50 | Idempotent side effects | P |
| 51 | Transactional publication | P |
| 52 | Compensation | P |
| 53 | Deadlock detection | P |
| 54 | Checkpoint recovery | P |
| 55 | Poison quarantine | P |
| 56 | Retry budgets | P |
| 57 | Failure prediction | P |
| 58 | Split brain prevention | P |
| 59 | Journal compaction | P |
| 60 | Version migration | P |
| 61 | Shadow scheduling | P |
| 62 | Counterfactual scheduling | P |
| 63 | Negative capability cache | P |
| 64 | Speculative reservations | P |
| 65 | Dependency collapse | P |
| 66 | Execution locality | P |
| 67 | Failure-domain isolation | P |
| 68 | Uncertainty-sensitive scheduling | P |
| 69 | Semantic deduplication | P |
| 70 | Cross-domain lending | P |
| 71 | Scheduler portfolios | P |
| 72 | Virtual workers | P |

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

## Wave 3: cross-plane resource group admission and race closure

The existing kernel GlobalResourceScheduler already implements plane reserves,
share borrowing, weighted dominant-share fairness, priority aging and two-phase
preemption. Wave 3 preserves those mechanisms and adds bounded atomic
submit-and-reserve groups against that same authority: no partially queued
members when capacity is unavailable; queued incumbent precedence; strict
single-tenant group identity; exact active replay; concurrent contention
serialized; protected reserve checks for every member; no regrant after release.
A preemption acknowledgement race is closed by retaining the existing RLock
from target validation through release. No actual distributed host allocation
or cross-process group persistence is asserted. Local group receipt capacity is
bounded, and exhaustion fails closed; durable versioned receipt migration and
retention policy remain future work.

## Wave 4: existing swarm execution custody and DAG admission

The canonical automation-agent SwarmRuntime now supports validated graph submission,
dependency barriers, explicit terminal dependency propagation, heap-generation
deduplication and bounded compaction. An opt-in fenced mode assigns random attempt
tokens, requires exact live tokens for worker mutations, and retains worker capacity
on expiry or ambiguous failure until trusted reconciliation. Restored fenced
checkpoints hold rather than replay uncertain effects, because a monotonic clock
from another process does not establish physical worker death. Token comparison
and digest binding are not a transport authentication protocol or an independent
proof of result; trusted host-side verification is required before reconciliation.
Legacy callers retain their default non-fenced mode. No external execution
authority or new scheduler is introduced.

Research: https://distributed.dask.org/en/stable/scheduling-state.html
and https://distributed.dask.org/en/stable/work-stealing.html (dependency and
transactional transfer boundaries); https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/
(reserve and permit separation). New partial targets: 46, 47, 50, 53, 54, 58,
59; no event-sourced durable swarm store is claimed, so these remain partial
or open until the exact target-specific evidence exists.

## Wave 5: durable promotion identity, queue drainage and attempt fencing

The existing SQLite pressure schema receives an additive receipt table, with
FULL synchronous connections, exact owner/scope/request/kind/manifest identity,
same-transaction lease publication, restart-visible replay, terminal tombstones
and a finite per-scope receipt ceiling. A request whose promotion committed
but response was lost returns the same still-live lease IDs. A completed,
expired or partially released group is never regranted under that request ID.
Unknown physical effects still require reconciliation by the executor; receipt
replay is not permission to rerun the task.

All new queue and lease generations use collision-resistant random identifiers,
including the legacy direct APIs. Existing live rows remain readable and
retries of currently live rows remain stable. Queue saturation now blocks NEW
normal admission but no longer blocks eligible queued work from draining when
execution capacity is free. Replacement policy checks tenant-level existing
usage as well as global totals. Receipt retention intentionally fails closed;
no unbounded or unsafe TTL deletion and no production-scale retention claim.

Partial target IDs additionally grounded: 46 (committed receipt log, not full event
sourcing), 47 (exact promotion replay), 50 (no regrant on known committed
identity, not external exactly-once effect), 51 (atomic lease/receipt publication),
54 (checkpoint restore holds), 58 (single DB fencing, not distributed consensus),
59 (bounded swarm heap compaction only, journal compaction remains open).

## Wave 6: hardened runtime, exact leasing and checkpoint convergence

The existing thread-safe HardenedSwarmRuntime, exact-lease helper, fencing helper,
snapshot validator, restore validator, invariant audit, rollback and broker
boundaries now reconcile graph admission and opt-in fenced attempts. Restored
queue-generation index is preserved, exact dispatch cannot bypass dependencies,
version-2 snapshots preserve uncertain slots, and version-1 remains readable.
Retention cannot discard unknown effects or referenced dependencies. The existing
broker deliberately denies fenced mode until authenticated completion and tenant
quota reconciliation can safely represent uncertain physical effects.

Wave 6 historical measurement: 26/72 adoption targets had partial source implementations
(IDs 01,02,03,04,06,08,09,11,14,26,39,41,47,49,50,51,54,55,56,58,60,61,62,66,68,71).
At wave 6 none was claimed fully qualified. Event sourcing, distributed deadlock detection,
and journal compaction are not achieved by receipts, DAG cycle checks or heap
compaction; these remain open in the primary register.

## Qualification and rollback

Run the focused test file, existing shared pressure tests, and every AGENTS.md
architecture/enterprise validator, mirror/source parity and exact-head CI.
Include contending processes, crash after commit before receipt, busy database,
clock jumps, cross-tenant denial, stale ticket and lease rejection, actual physical
workers, and pressure tests. No physical capacity or latency claim from this wave.
Logical group slots are not Ray-style distributed physical allocation. Ranking
currently scans a bounded authorized set; scale qualification and indexed next
selection are follow-up work. Roll back the whole reviewed commit; the new pressure receipt table is additive; preserve receipt tombstones and do not activate legacy writers that could reopen already committed identities. Existing queue rows and callers remain compatible.

## Wave 7: CI closure repairs and authenticated host broker boundary

The previous exact head ran 31 focused tests, 30 passing; first-import dependency
failure was a missing Pydantic install. Workflow now installs the existing
project and the already used qualification dependencies, declares concurrency,
and removes trailing EOF whitespace. Inherited live AI mapping counts and
admission-root ownership are reconciled without changing any validator or hold.

The hardened runtime may now be used through an explicitly configured
host verifier at the existing SwarmBroker boundary. Verified outcome and
reconciliation methods bind worker, task, attempt token, action and evidence
digest, then recheck ownership under lock. Legacy ingress/completion calls
still reject fenced execution; tenant broker construction/rebind also rejects
it until quota/accounting and transport authorization are qualified. This is
a host integration interface, not a deployed transport credential scheme.
The legacy control plane now leases the exact selected task rather than the
unrelated highest-priority task from its worker queue.

## Wave 8: heterogeneous hardware and inference batching proposals

Ray Serve dynamic batching and model multiplexing inspire token-, memory- and
padding-budget microbatch proposals, with separate tenant/model/tokenizer/adapter/
policy/precision/phase identities, hard deadlines and protected priority lanes.
For native inference this is a planning kernel only, not actual fused device
execution. Device ranking filters generation-tagged observations by RAM, VRAM,
unified memory, compute, I/O, bandwidth, thermal and power headroom; affinity,
cache locality and estimated energy rank eligible devices. Capacity must be
revalidated by its physical owner, and aliased memory remains an owner concern.
Kubernetes-style queueing hints inspire scoped negative capability observation
invalidation; deterministic two-choice sampling is available for eligible pools.

Research: https://docs.ray.io/en/latest/serve/advanced-guides/dyn-req-batch.html
https://docs.ray.io/en/latest/serve/model-multiplexing.html
https://docs.ray.io/en/latest/serve/llm/architecture/routing-policies.html
https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/

New partial source targets: 15, 31, 32, 33, 35, 36, 37, 40, 44, 45, 63.
Physical allocation, measured GPU batching, true shared memory custody, device
migration, generation invalidation wiring and scale benchmarks remain open.

Current campaign measurement: 37/72 partial source targets. The wave-7
intermediate exact head passed all 33 focused tests and the 183-mapping
architecture validator. The separate integration source-object audit identified
inherited stale source pins; the four verified mismatches for Jeeves, Learning,
School and Provenance are corrected against their actual Git trees. No historical
audit record or validator has been changed. Final-head CI remains required.

## Wave 9: verified tenant custody and checkpoint accounting

The existing tenant broker now supports an explicit verified host mode. Admission
reserves a finite identity retention slot and validates same-tenant dependencies;
dispatch charges tenant leased quota before exact task publication. Unknown
effects retain the worker slot and tenant leased quota. Reconciliation verifies
the same attempt and reserves queued quota before a retry can be published.
Wrong-tenant requests and changed replay identity are rejected. The tenant
checkpoint classifies uncertain tasks as active and rebuilds leased accounting;
legacy HTTP/broker calls cannot silently enter verified mode. This is a tested
candidate interface for a trusted host, not external transport activation.

## Wave 10: cognitive specialist and independent review proposals

A source-bound routing kernel filters explicitly approved models by tenant,
policy, task class, required capability, freshness, complexity proxy,
token/deadline/cost budget and independently supplied historical results.
It favors exact context affinity after a conservative shrunk evidence score.
High uncertainty requires a budgeted producer/reviewer pair with distinct
model family and failure domain; insufficient evidence or resources hold.
Consensus compares exact result digests and independent evidence identities;
contradiction or insufficient independence blocks the proposal. Neither a
self-reported confidence nor agreement constitutes independent truth.
These are advisory interfaces for the canonical cognitive execution owner,
not autonomous model selection, actual inference or publication authority.

Research: Ray model multiplexing and request routing (model/replica identity),
https://docs.ray.io/en/latest/serve/model-multiplexing.html and
https://docs.ray.io/en/latest/serve/llm/architecture/routing-policies.html.
Newly partial targets 18, 19, 20, 21, 22, 24, 25, 27. Task classification
requires an actual classifier; model-directed selection requires integration.
Prior wave 9 exact-head focused CI: 40 passed; 183-mapping validator passed.

## Wave 11: deterministic graph optimization and recovery proposals

Pure source/context/policy/input-bound computations can be proposed for
common-subexpression elimination, retaining predecessor order and tenant
boundaries. Rewritten dependency references are explicit, not implicitly
published. Semantic label resemblance is a bounded, scoped review hint
only. Compensations run in reverse topological proposal order with an
explicit owner-approved inverse and committed receipt; unknown outcomes
block the whole recovery proposal. Strongly connected wait-for components
identify potential deadlocks in one generation; no worker is killed.
Read-only is not synonymous with pure: speculative hedges are restricted
to pure tasks and distinct failure domains with full duplicate reservation
and deadline capacity, never writes or unknown-effect tasks.

New partial targets: 10, 28, 30, 52, 53, 64, 65, 67, 69.
No live graph rewrite, speculative execution, compensation execution or
distributed deadlock resolution is enabled by these proposal functions.

## Wave 12: existing tenant authority and durable dispatch publication

The ranked scheduler now drives exact leasing through the verified tenant broker,
not merely an advisory ranking. It validates the explicitly authorized candidate
set against registered tenant, priority, dependency state and quota, honors
protected priority and weighted active shares, and retains supervisor eligibility.
The existing recovery manager captures tenant/runtime state under aligned locks;
fenced state requires paired tenant custody. The durable bridge can issue a
ranked attempt only after the existing run store commits and reads back its
archive. Storage failure or ambiguous acknowledgement retires that broker
generation and retains uncertain worker/tenant slots without returning a token.
Full history-ring rollback preserves evicted records on failed capture.
The caller must already hold the canonical run-writer lease. No remote cluster,
external exactly-once effect or production durable store benchmark is claimed.

Current source register: 54/72 partially implemented targets, not 54 completed.
New live integration strengthens previously partial targets 1, 2, 4, 14, 49,
51 and 54. Remaining source gaps and all competitive qualification remain open.

## Wave 13: hierarchical resource control and deadline-aware preemption

The canonical global scheduler accepts opt-in tenant ceilings across all
planes, including atomic group reservations and revoking grants. Logical
deadline ticks participate in dispatch priority within the priority class;
infeasible deadlines remain visible and cannot receive a fresh grant.
Same-priority deadline preemption and existing reserve reclamation use
two-phase revocation; repeated requests return outstanding revocations
rather than prematurely freeing capacity or over-revoking additional work.
Cross-plane lending remains capacity-accounted, with reserve reclamation
limited to a plane with an actual reserve deficit. This strengthens the
existing logical owner rather than creating another allocator.

Partial adoption: 05, 07, 70. Actual host resources and stop acknowledgments
are not independently qualified. Wave-12 exact head: 50 focused tests
passed and architecture/mirror validation passed. Merge hold is intentional.
An unrelated inherited archive test selector failed and requires repair.

## Wave 14: constrained semantic classification and recursive expansion

Source-bound taxonomy classification consumes verified labels and abstains
on ambiguous classes. A model-proposed worker must match an independently
bound, tenant/task/policy-scoped eligible set exactly, including its
generation and observation digest. Recursive decomposition validates
approved pure operations, parent budgets, depth, graph topology, leaf
dependencies and conservative service totals. Fusion proposes bounded,
scope-compatible straight-line pure tool chains without fanout; intermediate
observability and executable support must be verified by the owner. These
are proposal validators, not trained semantic classification, autonomous
tool execution or live workflow mutation. New partial targets: 12, 13,
16, 17, 23, 29.

The draft-19 source job's nonexistent archive test selector is replaced
with the existing invalid-custody parametrized cases and source-tamper
nonpublication regression. The original deterministic inspection and
preflight assertions remain.

## Wave 15: topology, migration, predictive preloading and pressure relief

Directed, generation-scoped link observations support bounded shortest
serial transfer-time path selection. A migration proposal requires stopped
execution, matching ABI, checkpoint and stop evidence, verified target
identity, destination plus scratch reservation, and a positive deadline
and service-time benefit. Source authority is retained until target copy
verification/publication and explicit stop/release acknowledgment.
Preload selection ranks authorized same-tenant, same-device forecasts
by expected benefit per reserved byte and obeys separate I/O and memory
budgets. Pressure forecasts use a conservative nonnegative trend,
recent error rates and recovery hysteresis; predicted overload proposes
throttling, speculative-work cancellation and owner-verified idle eviction.

New partial targets: 34, 38, 42, 43, 57. No physical memory migration,
GPU peer transfers, calibrated failure predictor or actual cache action
is yet demonstrated by these proposal functions.

## Wave 16: hierarchical virtual workers in the existing swarm owner

Fenced runtimes may register nested virtual worker partitions to a bounded
depth. Each child consumes its parent's declared free logical capacity,
so root and descendants cannot multiply admitted slots. Child capabilities
are a subset of the parent, active or unresolved children retain capacity,
parent removal fails until descendants are removed, and the supervisor
applies ancestor quarantine. The canonical checkpoint validator reconstructs
delegated capacity from exact parent relations and rejects cycles and
over-allocation. Legacy unfenced mode does not admit virtual workers.
Partial target 72. Physical worker processes, 100k+ fleet qualification,
and authenticated transport remain explicitly unqualified.

## Wave 17: partitioned checkpoint event journal and bounded compaction

The existing recovery owner supports an opt-in version-2 archive with
ordered, hash-chained, tenant-partitioned task upserts/deletions and global
worker deltas. Each event represents a committed checkpoint, not every
intermediate runtime mutation. Replay reconstructs exact normalized states,
validates checkpoint hashes, tenant sidecar binding and canonical
partition changes, and refuses lost or changed retained tenant identities.
When the retention ring rolls forward, its first retained checkpoint becomes
a full replay anchor. Existing v1 archives remain readable; v2 is restricted
to paired fenced tenant custody. Expanded replay stays explicitly bounded.
The existing durable bridge stores the versioned archive using its existing
run-writer lease; no second durable store or tenant-facing data exposure.
Regression source covers roundtrip, corrupt/resealed cross-tenant changes,
anchor compaction and a reopened SQLite run store.

Partial targets 46, 48, 59. Full transition-level event sourcing,
physical partition throughput, independent authenticated archive pinning,
and long-duration compaction benchmarks remain unqualified.

Source register: 72/72 targets have partial source implementations; this is
100% source coverage, not completion of each target. Actual execution
integration and independent competitive qualification remain a separate phase.
