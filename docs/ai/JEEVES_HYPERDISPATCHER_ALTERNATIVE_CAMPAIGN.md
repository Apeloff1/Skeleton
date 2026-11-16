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
| A06 | Keyed singleton ownership | Inngest / Restate | Open |
| A07 | Quiet-window debounce | Inngest | Open |
| A08 | Maximum-wait coalescing | Inngest | Open |
| A09 | Rate-shaped dequeue | DBOS | Open |
| A10 | Non-discarding throttle | Inngest | Open |
| A11 | Event correlation wakeup | Restate / Inngest | Open |
| A12 | Durable timers and waits | Restate / DBOS | Open |
| A13 | Atomic outcome plus enqueue | River | Open |
| A14 | Transactional unique job identity | River / Oban | Open |
| A15 | Versioned activation identity | Orleans | Open |
| A16 | Idle actor passivation | Pekko / Orleans | Open |
| A17 | Memory-sensitive passivation | Orleans | Open |
| A18 | Communication affinity graph | Orleans | Open |
| A19 | Bounded migration rounds | Orleans | Open |
| A20 | Activation balance and anti-thrash | Orleans | Open |
| A21 | Scale-to-zero safety | Knative | Open |
| A22 | Cooldown and warm retention | KEDA / Knative | Open |
| A23 | Stale scaler metric hold | KEDA | Open |
| A24 | Service-rate-based scale demand | KEDA / Parsl | Open |
| A25 | Uncertain execution capacity floor | Jeeves extension | Open |
| A26 | Hierarchical allocation subleases | Flux / Parsl | Open |
| A27 | Nested allocation reclamation | Flux | Open |
| A28 | Data-affinity task scheduling | TaskVine / StarPU | Open |
| A29 | Shared artifact transfer amortization | TaskVine | Open |
| A30 | Versioned environment reuse | TaskVine | Open |
| A31 | Data-ready execution barriers | StarPU / PaRSEC | Open |
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
