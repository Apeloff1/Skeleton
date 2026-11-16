# Alternative dispatcher adoption — 36 targets

Independent source implementations. P means partial source implementation only; no deployment or measured competitive advantage. Existing canonical runtime, quota, persistence and executor owners remain authoritative. This register is separate from the 72-target primary campaign.

## Research verified against project documentation

- Orleans placement and activation collection: https://learn.microsoft.com/en-us/dotnet/orleans/grains/grain-placement ; https://learn.microsoft.com/en-us/dotnet/orleans/host/configuration-guide/activation-collection
- Pekko passivation and sharding: https://pekko.apache.org/docs/pekko/current/typed/cluster-sharding.html
- Inngest flow control: https://www.inngest.com/docs/durable-execution/flow-control
- Trigger.dev multiple concurrency limits: https://trigger.dev/changelog/multiple-concurrency-limits
- DBOS queues: https://docs.dbos.dev/architecture
- River transactional uniqueness: https://github.com/riverqueue/river
- YuniKorn hierarchy: https://yunikorn.apache.org/docs/get_started/core_features/
- Flux allocation hierarchy: https://flux-framework.readthedocs.io/en/latest/tables/comparison-table.html
- Parsl and TaskVine executors: https://parsl.readthedocs.io/en/stable/userguide/configuration/executors/index.html
- Knative zero scaling: https://knative.dev/docs/serving/autoscaling/scale-to-zero/
- KEDA polling/cooldown: https://keda.sh/docs/2.21/reference/scaledobject-spec/

Further research queue (not yet verified): Restate, Oban, pg-boss, Faktory, Asynq, Sidekiq, HPX, StarPU, PaRSEC, Legion, Charm++, oneTBB, RADICAL-Pilot, Balsam, OpenPBS, Taskflow, OpenFaaS, Apache Pulsar. Their names in the inventory indicate research leads, not verified feature claims.

## Adoption inventory

| ID | Target | Inspiration | Source status |
|---|---|---|---|
| A01 | Overlapping concurrency ceilings | Trigger.dev / Inngest | P |
| A02 | Aggregate global quota | Trigger.dev / YuniKorn | P |
| A03 | Shared dependency or service quota | Inngest | P |
| A04 | Atomic multi-ceiling transitions | Trigger.dev | P |
| A05 | Policy-preserving restore accounting | DBOS / River | P |
| A06 | Keyed singleton ownership | Inngest / Restate | P |
| A07 | Quiet-window debounce | Inngest | P |
| A08 | Maximum-wait coalescing | Inngest | P |
| A09 | Rate-shaped dequeue | DBOS | P |
| A10 | Non-discarding throttle | Inngest | P |
| A11 | Event correlation wakeup | Restate / Inngest | P |
| A12 | Durable timers and waits | Restate / DBOS | P |
| A13 | Atomic outcome plus enqueue | River | P |
| A14 | Transactional unique job identity | River / Oban | P |
| A15 | Versioned activation identity | Orleans | P |
| A16 | Idle actor passivation | Pekko / Orleans | P |
| A17 | Memory-sensitive passivation | Orleans | P |
| A18 | Communication affinity graph | Orleans | P |
| A19 | Bounded migration rounds | Orleans | P |
| A20 | Activation balance and anti-thrash | Orleans | P |
| A21 | Scale-to-zero safety | Knative | P |
| A22 | Cooldown and warm retention | KEDA / Knative | P |
| A23 | Stale scaler metric hold | KEDA | P |
| A24 | Service-rate-based scale demand | KEDA / Parsl | P |
| A25 | Uncertain execution capacity floor | Jeeves extension | P |
| A26 | Hierarchical allocation subleases | Flux / Parsl | P |
| A27 | Nested allocation reclamation | Flux | P |
| A28 | Data-affinity task scheduling | TaskVine / StarPU | P |
| A29 | Shared artifact transfer amortization | TaskVine | P |
| A30 | Versioned environment reuse | TaskVine | P |
| A31 | Data-ready execution barriers | StarPU / PaRSEC | P |
| A32 | Compute-transfer overlap planning | StarPU / Legion | P |
| A33 | Weighted resident shard split | Pekko / Orleans | P |
| A34 | Bounded membership migration | Pekko | P |
| A35 | Measured dispatch policy comparison | HPX / Taskflow | P |
| A36 | End-to-end mixed-workload qualification | All alternatives | P |

## Wave A1: overlapping quota ceilings

The existing QuotaLedger now enforces host-configured aggregate ceilings over
explicit tenant sets or globally. All applicable quota projections are evaluated
under the same existing lock before publication. Aggregate usage includes queued,
leased and payload custody and is updated by every existing reservation/release,
including unknown-effect holds. Configuration changes cannot strand current
usage outside the new ceiling; an empty ingress fork preserves aggregate policy
for recovery reconstruction. No new database or remote authority.

Policies are trusted host configuration, not information inferred from task
payload. The current archive does not independently persist or hash policy
configuration; the recovery host must supply matching policy. Shared service
ceilings are explicit tenant groupings, not per-operation keys.

## Wave A2: activation identities and elastic lifecycle

The existing runtime assigns a fresh registration token per worker activation;
restored activation identities rotate and cannot reuse old stop evidence.
The existing autoscale policy accounts for uncertain slots and does not recommend
removing occupied capacity. The new service-rate elastic recommendation reduces
backlog using bounded changes, freshness checks, warm retention, cooldown and
explicit scale-to-zero readiness. A root idle-retirement proposal excludes queued
demand, held capacity, delegated descendants and protected identities. The existing
worker registry removes an idle logical worker only after a trusted stop verifier
and exact generation revalidation. No external process is stopped or started
by these methods. Zero-ready is a trusted host assertion, not a live probe.

## Wave A3: rate-shaped dequeue and event coordination

The existing verified tenant broker uses an optional host-configured start-rate
policy before publishing an attempt. Excess work stays queued with intact
quota; every process-local start-credit bucket begins empty, including restore,
and backward clock samples grant no credit. Failed attempts conservatively
spend credit. This is not a globally coordinated distributed rate limiter.
The event-coordination helper proposes bounded keyed windows, exact replay
identity, non-discarding quiet-window coalescence with hard maximum wait,
singleton eligibility against active or uncertain ownership, and generation-
bound event/timeout wake proposals. It does not claim durable singleton locks,
timer delivery, transactional event ingestion or actual wake publication.

## Wave A4: communication affinity and content-bound scheduling

The bounded affinity planner evaluates the observed communication graph,
permits only idle and movable activations from the same tenant, policy
and generation, and calculates marginal locality gain after migration
cost. It retains destination headroom, enforces byte/move limits and
cooldown, and updates the simulated graph after each accepted move.
The artifact planner groups exact destination/content/environment/policy
identities, avoids transfer duplication and reserves bytes against finite
destination and round budgets. Missing inputs hold their consumers until
a fresh verified resident observation exists. Transfer and migration
remain advisory; no physical movement, cache publication or execution
is performed. A15 activation generation, A16 idle passivation and A21–25
lifecycle work remain subject to host integration and qualification.

## Wave A5: nested allocation authority and affinity repair

The existing global resource scheduler owns bounded, attempt-tokened nested
subleases. Children consume their parent's allocation, not a second physical
reservation. Root release cannot bypass descendants; root preemption marks
the subtree revoking, and trusted stop verification releases descendant
allocations leaf-first. Completed sublease IDs remain tombstones. Cancelling
root preemption leaves already requested child stops conservatively revoking.
The host must reserve only the undelegated remainder for direct work. No
distributed persistence or physical stop protocol is implied.
The wave-A4 exact-head test failure (dictionary mutated during affinity scan)
is repaired by nonmutating lookup. Existing regression kept intact.

## Wave A6: durable unique job admission and verified follow-up publication

The existing SwarmDurableBridge can acknowledge a unique job only after
checkpoint/readback, using the canonical tenant/task identity. It also
publishes a reconciled uncertain parent and a bounded, exact-manifest
authorized batch of dependent follow-up jobs in one recovery archive.
Children are admitted while the parent dependency barrier still holds.
Any ambiguous mutation or storage acknowledgment retires the in-memory
broker generation; restore from the actual durable archive. The host must
hold the existing exclusive run-writer lease and must not bypass the
verified owner. No external side-effect transaction or automatic replay
of a completed continuation is claimed. Uncertain write acknowledgment
requires recovery and inspection, not blind repetition.

## Wave A7: memory pressure passivation, weighted shards and overlapped pipelines

Root retirement proposals can prioritize independently observed reclaimable
bytes per estimated reload time while honoring freshness, exact activation
identity, occupied capacity and minimum retained slots. The existing verified
stop boundary remains authoritative. Weighted rendezvous placement is stable
across membership order and includes bounded resident-state redistribution
with distinct tenant/generation, byte/step budget and uncredited source release.
The copy/compute pipeline proposes separate transfer and execution intervals
only when a distinct copy engine has been verified; staging remains charged
through work completion and deadlines/horizon remain enforced. None of these
proposals moves bytes, activates workers, or claims actual GPU performance.

## Wave A8: measured policy replay and mixed-workload source qualification

The existing shadow scheduler can measure local policy-computation elapsed
nanoseconds over the same pinned workload and rotate policy order across
repetitions; raw samples, median, p95, trace identity and replay outcomes
are retained. Wall-clock computation is distinct from simulated work.
The integration test exercises real SQLite persistence, shared tenant
quota, virtual worker partitions, ranked durable leasing, uncertain
restart custody and atomic continuation publication. The verifier in
this test is a fixture, not external effect authentication. No external
competitor measurement, physical native execution, throughput advantage
or product-wide qualification is claimed.

All 36 alternative targets have a partial source implementation or
qualification harness. A35/A36 remain measurement and qualification
work, not completed competitor benchmarks. Original 72-target source
register remains unchanged. Combined 108/108 partial source coverage;
independent competitive qualification remains 0/108.

## Wave A9: authoritative event wait gates and singleton custody

The existing verified tenant broker derives singleton scope from the tenant
and host-provided key; both heap and exact leasing honor the gate, with
one occupied slot per scope and unknown effects retaining ownership.
The runtime reconstructs the singleton occupancy index on restore and
rejects conflicting holders. A wait intent binds a digest; the durable
bridge authenticates its receipt through a trusted verifier, opens only
the exact wait, and checkpoints/readbacks before permitting dispatch.
Ambiguous publication retires the owner. New gate-bearing runtime
snapshots use version 3: older readers fail closed rather than silently
ignore gates. Versions 1/2 remain readable and the existing delta archive
can carry version-3 snapshots. The existing exclusive run-writer and
authenticated event or clock receipt producer remain prerequisites; no
external timer daemon, cluster-global singleton, or independent evidence
transport is claimed. Regression fixtures cover both lease paths,
tenant isolation, uncertain restart, real SQLite reopen, and failed wake.
Prior wave A8 exact head passed 89 focused tests and 183 architecture
mappings; that is not a substitute for A9 exact-head qualification.
