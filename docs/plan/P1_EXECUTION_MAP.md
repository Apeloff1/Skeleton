# P1 Production Promotion Execution Map

Status: **active planning authority for the post-P0 production-promotion phase**

Machine contract: [`machine/ai_p1_execution_map.json`](../../machine/ai_p1_execution_map.json)

Validator: [`scripts/check_ai_p1_execution_map.py`](../../scripts/check_ai_p1_execution_map.py)

The P1 phase begins from an important fact: the functional AI closure program is already terminal at the construction-gap level. The fourteen P0 construction gaps are closed, and the three canonical P1 gaps—feedback promotion, provider redundancy, and release/SLO control—are also closed. P1 therefore must not be represented as “finish the last three gaps.” Its job is broader and stricter: promote a bounded subset of the masterplan from specified target architecture into an integrated, measured, failure-tested, release-qualified production system.

The masterplan contains 421 breadth-frozen volumes. P1 deliberately does **not** claim all 421. It owns a 64-volume primary promotion frontier and leaves 357 volumes explicitly deferred. This is the anti-inflation rule for the phase: P1 is complete only when its bounded frontier reaches its declared maturity floors with exact-head evidence; P1 completion is not equivalent to total masterplan completion.

## P1 objective

P1 converts “the core works and its canonical gaps are closed” into “the system can be measured, operated, evolved, installed, recovered, distributed and promoted without losing authority or evidence.”

The phase has six lanes:

| Lane | Purpose | Primary volumes | Maturity floor |
| --- | --- | ---: | --- |
| P1-L0 | Evidence, accountability and promotion spine | 13 | verified |
| P1-L1 | Product truth and operator surfaces | 7 | verified |
| P1-L2 | Controlled learning, evaluation and failure knowledge | 10 | hardened |
| P1-L3 | Release, installation, recovery and operations | 14 | production |
| P1-L4 | Distributed runtime, capacity and economics | 20 | hardened |
| P1-L5 | Terminal P1 production promotion | 0 | production decision |

Primary-volume ownership is exclusive. Supporting-volume references may overlap because security, provenance, observability, governance and human control are cross-cutting dependencies rather than duplicated ownership.

## Dependency graph

```text
P1-L0  Evidence / accountability spine
  ├──> P1-L1  Product truth & operator surfaces ──┐
  └──> P1-L2  Controlled learning & evaluation ──┤
                                                   ├──> P1-L3  Release / recovery ───────┐
                                                   └──> P1-L4  Distributed capacity ────┤
                                                                                         └──> P1-L5 Terminal promotion
```

P1-L1 and P1-L2 are intentionally parallel after the evidence spine is stable. P1-L3 and P1-L4 are intentionally parallel after product/evaluation dependencies are available. P1-L5 is not an implementation lane; it is the aggregation and independent-promotion decision.

## Entry contract

P1 work may advance only while all of the following remain true:

1. all fourteen canonical P0 construction gaps remain closed;
2. all three canonical P1 construction gaps remain closed;
3. the exact implementation head passes the P1 Terminal Closure Gate;
4. the exact implementation head passes the Masterplan Completion Gate;
5. the masterplan breadth freeze remains at VOL-420;
6. current runtime truth remains authoritative where implementation and target plan differ.

A reopened P0/P1 construction gap is not “new P1 work.” It is a regression and blocks promotion until repaired.

## P1-L0 — Evidence, accountability and promotion spine

**Primary volumes:** VOL-000, 034, 035, 036, 037, 038, 056, 057, 059, 078, 079, 080, 420.

This lane exists because the larger masterplan currently has a major semantic mismatch: many capabilities are implemented in the repository while their 421 volume records remain `specified/unverified`. P1-L0 establishes the machinery required to promote those records honestly instead of editing status fields by hand.

The lane unifies exact-head identity, traces, evaluations, verifier receipts, provenance, gap/risk records, CI authority and reproducibility. It also makes scope freeze executable. The important output is not another dashboard; it is one evidence graph capable of answering “what exact code/config/environment/test proves this maturity claim?”

The first implementation sequence is:

1. assign one durable evidence identity to operation, trace, test, verifier and promotion receipts;
2. materialize evaluator/verifier registries and risk-tier routing;
3. bind every blocking gap/risk to executable evidence or explicit accepted-risk disposition;
4. make required-gate maps fail closed on skipped/cancelled/missing checks;
5. bind reproducibility bundles to qualifying evidence;
6. enforce the VOL-420 breadth freeze and ADR exception path mechanically.

**P1-L0 exit:** a maturity promotion can be independently reproduced from its receipt set, and no critical/high risk can disappear behind an aggregate green status.

## P1-L1 — Product truth and operator surfaces

**Primary volumes:** VOL-040 through VOL-046.

This lane makes the already-closed runtime legible and controllable without allowing the presentation layer to become a second source of truth. Streaming, API, web, desktop, long-running UX and tenancy all become projections of durable operation state.

The core design rule is: a page refresh, reconnect, second client, or desktop restart must reconstruct the same authoritative operation and conversation state. Optimistic UI may improve responsiveness, but it cannot invent terminal results, permissions, costs, evidence, or progress.

Implementation emphasis:

- stable API schemas and compatibility gates;
- durable stream cursor, replay-gap detection and resync;
- canonical product/workspace projection contracts;
- evidence-backed progress and blocker display;
- pause/resume/cancel/human-override semantics;
- tenant identity and storage classification through every product hop;
- platform-specific desktop permission tests.

**P1-L1 exit:** users and operators can observe, reconnect to and control long-running AI work without contradicting durable runtime truth.

## P1-L2 — Controlled learning, evaluation and failure knowledge

**Primary volumes:** VOL-023, 024, 077, 082, 083, 324, 369, 414, 415 and 419.

The original feedback-promotion gap is closed, but P1 needs the larger controlled-evolution system around it. This lane turns feedback and research into candidates, not authority. Every candidate must survive reproducible evaluation, contamination checks, adversarial tests, champion/challenger comparison, shadow isolation and rollback qualification.

This lane also makes failure knowledge a first-class asset. Incidents, rejected designs, failed experiments and adversarial counterexamples should become structured regression material rather than disappearing into old logs or pull-request discussions.

Implementation emphasis:

- experiment and benchmark registries;
- contamination and benchmark-lineage metadata;
- candidate artifact schema;
- shadow traffic with side-effect and privacy isolation;
- champion/challenger state and promotion history;
- reasoning/specification-gaming regression corpora;
- negative-result and incident ingestion;
- research/experimental branch promotion criteria.

**P1-L2 exit:** no learning signal, candidate, research branch or evaluator can directly promote itself to production.

## P1-L3 — Release, installation, recovery and operational qualification

**Primary volumes:** VOL-047 through 050, VOL-060 through 066, VOL-075, 076 and 409.

P1-L3 joins installation and operations into one reversible lifecycle. A release is not qualified because CI built an artifact; it is qualified when a clean machine can install it, an existing machine can update it, interrupted operations can recover, durable data remains readable through rollback, backups can restore, and the release bundle ties every artifact to provenance and test evidence.

Implementation emphasis:

- installer/updater ownership manifests and interruption checkpoints;
- artifact digests tied to SBOM/provenance/attribution;
- migration compatibility and rollback windows;
- deployment/environment/config digests;
- backup coverage manifests and restore-order drills;
- disaster-recovery dependency graph;
- incident/postmortem feedback into gap/risk/failure ledgers;
- repair and residual-cleanup paths.

**P1-L3 exit:** clean-machine install, update, repair, rollback, backup/restore and incident paths are demonstrated on exact release evidence.

## P1-L4 — Distributed runtime, capacity and economics

**Primary volumes:** VOL-029, 030, 031, 067, 068, 069, 381, 382, 385, 386, 390, 391, 392, 397, 398, 399, 403, 404, 405 and 406.

This lane turns “the engine works” into “the engine behaves predictably when resources, providers or networks stop being ideal.” It is deliberately tied to cost and capacity because unbounded scale is not reliability.

Implementation emphasis:

- remote execution envelope and worker registry;
- leases, fencing and worker attestation;
- model placement and warming;
- continuous/deadline-aware batching;
- autoscaling against measured load profiles;
- topology-aware placement and network constraints;
- quota hierarchy and admission;
- idempotent budget reservation/charge/reconciliation;
- demand/capacity/cost forecast backtests;
- cost anomaly detection feeding incident/workflow handling;
- saturation, partition and backpressure drills.

**P1-L4 exit:** the distributed system fails predictably under saturation and partition, stale/untrusted workers cannot commit, and cost optimizations cannot silently defeat quality/privacy constraints.

## P1-L5 — Terminal production promotion

P1-L5 owns no primary volumes. That is intentional. Its job is to independently decide whether P1 evidence is sufficient.

The terminal promotion packet must bind the exact head to:

- all lane maturity results;
- signed accountability;
- clean-machine installation;
- rollback and disaster recovery;
- saturation/backpressure/partition behavior;
- adversarial and benchmark evidence;
- security/malware/dependency/provenance gates;
- supported architecture/platform validation;
- the unchanged closure of all original P0 and P1 construction gaps.

A production label is rejected if any required evidence is stale, merely planned, unsigned, or tied to a different commit/configuration.

## Maturity policy

P1 uses the existing masterplan maturity ladder rather than inventing a P1-specific status language:

`specified → scaffolded → implemented → integrated → verified → hardened → production`

The minimum P1 frontier floor is `integrated`, but lane targets are stricter:

- P1-L0: `verified`
- P1-L1: `verified`
- P1-L2: `hardened`
- P1-L3: `production`
- P1-L4: `hardened`

Status promotion must be evidence-derived. File existence, line count, a successful happy path, or prose documentation do not qualify.

## Failure families that P1 must exercise

P1 acceptance explicitly covers restart/crash, partial commit, duplicate/reordered delivery, provider outage/failover, policy denial/revocation, stream disconnect/resync, rollback incompatibility, capacity exhaustion, network partition/stale lease, benchmark leakage/specification gaming, and malicious or stale evidence.

These are not optional “edge tests.” They are the conditions under which production maturity has meaning.

## Parallelism

The phase is designed for controlled parallel work:

- L0 begins first and establishes evidence contracts.
- L1 and L2 may run concurrently after L0 contracts stabilize.
- L3 and L4 may run concurrently after L1/L2 interfaces are stable enough for production qualification.
- L5 waits for all lanes.

Within a lane, independent changes may proceed in parallel only if they do not create competing canonical owners. Changes touching state authority, security/permission semantics, release schemas or evidence identity must be serialized behind the relevant canonical contract.

## Immediate execution tranche

The next implementation tranche after the P1 assurance PR lands should be:

1. **P1-L0 evidence registry:** define the machine record that binds capability/volume, commit, config digest, environment, tests, verifier, risk disposition and maturity decision.
2. **P1-L0 maturity reconciler:** compare `ai_master_plan` volume records with actual implementation/evidence and produce candidate promotions without self-signing them.
3. **P1-L0 required-gate authority map:** make missing/skipped/cancelled required evidence explicit.
4. **P1-L1 projection contract:** bind API/stream/product state to operation/event cursor authority.
5. **P1-L2 benchmark/champion registry:** unify experiments, benchmark lineage, shadow comparisons and promotion history.
6. **P1-L3 release evidence bundle:** tie installer/update/rollback/restore artifacts to the same exact-head evidence identity.
7. **P1-L4 budget/capacity ledger:** join quotas, cost accounting, saturation profiles and forecast evidence.

The first three are deliberately first because every later maturity promotion depends on them.

## What P1 does not mean

P1 does not mean the entire masterplan is complete. It does not require implementing native training, every experimental architecture, every specialized domain, or every future optimization. Those remain represented in the 357-volume deferred set.

P1 also does not permit reopening completed P0/P1 gaps to create artificial progress, replacing runtime truth with target-plan metadata, or adding new top-level volumes to inflate scope.

## Completion statement

P1 is complete when the 64-volume frontier meets its lane maturity floors, all original functional closure gaps remain closed, terminal production-promotion evidence is exact-head and independently verified, and the remaining 357 volumes are still represented honestly as later work rather than being silently relabeled complete.

## Task-level P1 backlog

The machine backlog [`machine/ai_p1_task_backlog.json`](../../machine/ai_p1_task_backlog.json) expands the six lanes into 32 dependency-ordered tasks. The initial state deliberately exposes only one runnable item: `P1-EVID-01`. Every other task is blocked until its declared evidence/dependency prerequisites are complete.

### P1-L0 — Evidence spine

1. `P1-EVID-01` — canonical evidence identity.
2. `P1-EVID-02` — maturity reconciliation engine.
3. `P1-EVID-03` — required-gate authority map.
4. `P1-EVID-04` — risk/gap evidence binding.
5. `P1-EVID-05` — reproducibility bundle.
6. `P1-EVID-06` — scope-freeze and ADR enforcement.

The critical path begins with evidence identity because every later promotion, release bundle, benchmark comparison and distributed qualification needs a common exact-head receipt model.

### P1-L1 — Product truth

1. `P1-PROD-01` — API schema and compatibility registry.
2. `P1-PROD-02` — streaming projection authority.
3. `P1-PROD-03` — workspace/product projection contract.
4. `P1-PROD-04` — pause/resume/cancel/human override.
5. `P1-PROD-05` — web/desktop tenant and storage boundary.

### P1-L2 — Controlled learning

1. `P1-LEARN-01` — experiment registry.
2. `P1-LEARN-02` — benchmark registry and contamination controls.
3. `P1-LEARN-03` — candidate/champion-challenger registry.
4. `P1-LEARN-04` — shadow-traffic isolation.
5. `P1-LEARN-05` — specification/reasoning regression corpus.
6. `P1-LEARN-06` — failure-knowledge pipeline.

### P1-L3 — Release and recovery

1. `P1-REL-01` — release evidence bundle.
2. `P1-REL-02` — installer/update/repair lifecycle.
3. `P1-REL-03` — migration and rollback compatibility.
4. `P1-REL-04` — backup and restore qualification.
5. `P1-REL-05` — disaster recovery and incident feedback.
6. `P1-REL-06` — attribution and release notices.

### P1-L4 — Distributed capacity and economics

1. `P1-DIST-01` — remote execution and worker trust.
2. `P1-DIST-02` — topology-aware model placement/warming.
3. `P1-DIST-03` — batching and autoscaling controller.
4. `P1-DIST-04` — load and capacity qualification.
5. `P1-DIST-05` — quota and budget accounting ledger.
6. `P1-DIST-06` — forecasting and cost-anomaly loop.

### P1-L5 — Terminal promotion

1. `P1-PROM-01` — aggregate exact-head P1 evidence.
2. `P1-PROM-02` — terminal failure-journey qualification.
3. `P1-PROM-03` — independent signed P1 promotion decision.

The validator requires every task to be an ancestor of `P1-PROM-03`; orphan work is rejected. It also rejects task cycles, tasks that claim volumes outside their lane, and ready/in-progress tasks whose prerequisites are not complete.

## Immediate coding order

The implementation order is therefore not ambiguous:

```text
P1-EVID-01
  ├── P1-EVID-02 ──> P1-EVID-06
  └── P1-EVID-03 ──> P1-EVID-04
          └─────────> P1-EVID-05

After evidence contracts stabilize:
  P1-L1 product truth  ||  P1-L2 controlled learning

After those interfaces stabilize:
  P1-L3 release/recovery  ||  P1-L4 distributed capacity

Finally:
  P1-PROM-01 -> P1-PROM-02 -> P1-PROM-03
```

The first coding task after the planning lane lands is `P1-EVID-01`: define the canonical evidence receipt and exact-head identity contract. It is intentionally small enough to land independently but foundational enough that later work should not invent competing receipt formats.

