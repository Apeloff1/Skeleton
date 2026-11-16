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
| A13 | Atomic outcome plus enqueue | River | Open |
| A14 | Transactional unique job identity | River / Oban | Open |
| A15 | Versioned activation identity | Orleans | P |
| A16 | Idle actor passivation | Pekko / Orleans | P |
| A17 | Memory-sensitive passivation | Orleans | Open |
| A18 | Communication affinity graph | Orleans | P |
| A19 | Bounded migration rounds | Orleans | P |
| A20 | Activation balance and anti-thrash | Orleans | P |
| A21 | Scale-to-zero safety | Knative | P |
| A22 | Cooldown and warm retention | KEDA / Knative | P |
| A23 | Stale scaler metric hold | KEDA | P |
| A24 | Service-rate-based scale demand | KEDA / Parsl | P |
| A25 | Uncertain execution capacity floor | Jeeves extension | P |
| A26 | Hierarchical allocation subleases | Flux / Parsl | Open |
| A27 | Nested allocation reclamation | Flux | Open |
| A28 | Data-affinity task scheduling | TaskVine / StarPU | P |
| A29 | Shared artifact transfer amortization | TaskVine | P |
| A30 | Versioned environment reuse | TaskVine | P |
| A31 | Data-ready execution barriers | StarPU / PaRSEC | P |
| A32 | Compute-transfer overlap planning | StarPU / Legion | Open |
| A33 | Weighted resident shard split | Pekko / Orleans | Open |
| A34 | Bounded membership migration | Pekko | Open |
| A35 | Measured dispatch policy comparison | HPX / Taskflow | Open |
| A36 | End-to-end mixed-workload qualification | All alternatives | Open |

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
