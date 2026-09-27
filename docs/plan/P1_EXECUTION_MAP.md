# P1 Trustworthy Autonomous Production Execution Map

Machine authority: [`machine/ai_p1_execution_map.json`](../../machine/ai_p1_execution_map.json)  
Task DAG: [`machine/ai_p1_task_backlog.json`](../../machine/ai_p1_task_backlog.json)

Map version: **1.1.0**  
Baseline merge: `6aacc56676f5a77e9f68d3a1a7b691a7039e9662` (PR #2091)  
Breadth freeze: **VOL-000..420; no new top-level volume without ADR**  
Primary P1 frontier: **107 volumes**  
Explicitly deferred: **314 volumes**  
Executable P1 tasks: **44**

## 1. What P1 means

P0 established and closed the functional runtime/construction spine. The original three canonical P1 construction gaps—feedback promotion, provider redundancy, and the release/SLO loop—are also already closed and remain prerequisites.

P1 is therefore **not another bootstrap phase**. It is the first deep maturity program over the closed functional core. Its job is to make the system measurably trustworthy under quality pressure, autonomous action, product reconstruction, controlled learning, release/recovery, distributed saturation, and independent promotion.

P1 completion **does not** mean all 421 masterplan volumes are implemented. It means the bounded 107-volume frontier satisfies its lane maturity floors with exact-head, independently verifiable evidence while the remaining 314 volumes remain explicitly visible as later work.

### Non-negotiable P1 laws

- P1 is promotion, integration and evidence work; target-plan file existence is not completion evidence.
- Every primary volume has exactly one P1 lane owner.
- Supporting volumes may be referenced by multiple lanes but do not transfer primary ownership.
- A lane may prototype ahead only when its declared dependencies are satisfied; maturity promotion may not bypass dependencies.
- No lane may reopen a closed P0/P1 construction gap to make progress appear available.
- Production promotion requires independent verification, rollback/recovery evidence and signed accountability.
- Security, privacy, authority, durability and evidence invariants dominate throughput and feature breadth.
- New top-level masterplan volumes remain prohibited without the existing ADR breadth-freeze exception.

### P1 non-goals

- claiming all 421 masterplan volumes are implemented
- building native training infrastructure solely to satisfy P1
- adding new top-level masterplan volumes
- allowing experimental or research candidates direct production authority
- replacing current runtime truth with planning metadata

## 2. Baseline contradiction P1 resolves

The repository now has two truthful but different views:

1. The functional construction contract is terminal: canonical runtime planes are present and canonical construction gaps are closed.
2. The long-range masterplan still carries 421 specified/unverified volumes and an older atomic AIQ/accountability view that is intentionally stricter than "code exists."

P1 resolves this by promoting **bounded slices of implemented reality into signed maturity evidence**. It must never solve the discrepancy by bulk-marking volumes complete.

## 3. Phase map

| Phase | Name | Lanes | Purpose |
| --- | --- | --- | --- |
| P1-PH0 | Evidence Reconciliation | P1-L0 | Make promotion evidence and scope authority trustworthy before deepening runtime maturity. |
| P1-PH1 | Core Quality, Safe Autonomy & Product Truth | P1-L1, P1-L2, P1-L3 | Deepen intelligence quality and autonomous safety while product surfaces remain projections of durable truth. |
| P1-PH2 | Controlled Learning | P1-L4 | Build reproducible, adversarial, isolated candidate improvement without direct production mutation. |
| P1-PH3 | Release & Distributed Hardening | P1-L5, P1-L6 | Prove reversible release/recovery and predictable distributed execution under resource/cost pressure. |
| P1-PH4 | Terminal Qualification | P1-L7 | Aggregate exact-head lane evidence into one independent promotion decision. |

## 4. Lane summary

| Lane | Domain | Depends on | Primary volumes | Target maturity | Tasks |
| --- | --- | --- | ---: | --- | ---: |
| P1-L0 | Evidence, Accountability & Promotion Spine | — | 13 | verified | 6 |
| P1-L1 | Core Intelligence Quality & Convergence | P1-L0 | 18 | hardened | 6 |
| P1-L2 | Safe Autonomous Action & Human Control | P1-L0 | 27 | hardened | 6 |
| P1-L3 | Product Truth & Operator Surfaces | P1-L0 | 7 | verified | 5 |
| P1-L4 | Controlled Learning, Evaluation & Failure Knowledge | P1-L0, P1-L1, P1-L2, P1-L3 | 8 | hardened | 6 |
| P1-L5 | Release, Installation, Recovery & Operational Qualification | P1-L2, P1-L3, P1-L4 | 14 | production | 6 |
| P1-L6 | Distributed Runtime, Capacity & Economics | P1-L1, P1-L2, P1-L3 | 20 | hardened | 6 |
| P1-L7 | Terminal P1 Trustworthy-Production Promotion | P1-L0, P1-L1, P1-L2, P1-L3, P1-L4, P1-L5, P1-L6 | 0 | production | 3 |

## 5. Detailed lane plans

### P1-L0 — Evidence, Accountability & Promotion Spine

**Objective.** Turn exact-head CI, observability, evaluation, verification, provenance, risk/gap ledgers and scope control into one promotion authority before later P1 lanes make production claims.

**Dependency position.** Root P1 lane. 

**Primary volume ownership (13).** VOL-000, VOL-034, VOL-035, VOL-036, VOL-037, VOL-038, VOL-056, VOL-057, VOL-059, VOL-078, VOL-079, VOL-080, VOL-420

**Supporting volumes.** VOL-025, VOL-026, VOL-027, VOL-028, VOL-084

**Work-package lineage.** WP-W00, WP-W01, WP-W18, WP-W21, WP-W22, WP-W23, WP-W24, WP-W26, WP-W27, WP-W28 via MBW-00, MBW-05, MBW-06.

**Target maturity.** `verified`.

#### Implementation slices

- unify operation/event/trace/evidence identity across runtime and CI receipts
- materialize verifier and evaluation registries with risk-tier routing
- bind gap and risk records to executable evidence and expiration/review rules
- make required-gate authority and cancellation/skip semantics fail closed
- bind reproducibility bundles to qualifying evidence
- enforce architecture breadth freeze and ADR exception handling in validators

#### Quantitative / structural gates

- 100% of P1 maturity claims bind exact git/config/environment/verifier identity
- 100% of critical/high P1 risks bind executable evidence or signed accepted-risk disposition
- 0 required promotion gates may be silently skipped, cancelled or path-filtered away
- 0 top-level volumes beyond VOL-420 without a machine-linked ADR exception

#### Required evidence modes

- contract
- negative_test
- mutation
- reproducibility
- independent_verification

#### Fault families

- stale-evidence
- missing-required-gate
- cancelled-or-skipped-gate
- risk-without-evidence
- scope-freeze-bypass

#### Acceptance

- every P1 promotion claim has exact-head evidence identity
- every critical/high P1 risk maps to executable evidence or signed accepted-risk disposition
- verification result is independent of generator confidence for high-impact cases
- required CI gates cannot silently disappear through skip/cancel/path-filter drift
- scope freeze remains validator-enforced

#### Stop conditions

- aggregate green status hides a known critical unresolved risk
- evidence cannot be tied to an exact commit/config/environment
- a target-plan claim is used as runtime truth

#### Task DAG

| Task | Status | Depends on | Volume refs | Promotion effect |
| --- | --- | --- | --- | --- |
| P1-EVID-01 — Canonical evidence identity | ready | — | VOL-034, VOL-038, VOL-078 | maturity_candidate |
| P1-EVID-02 — Maturity reconciliation engine | blocked | P1-EVID-01 | VOL-000, VOL-056, VOL-080 | maturity_candidate |
| P1-EVID-03 — Required-gate authority map | blocked | P1-EVID-01 | VOL-059, VOL-037 | maturity_candidate |
| P1-EVID-04 — Risk/gap evidence binding | blocked | P1-EVID-01, P1-EVID-03 | VOL-036, VOL-056, VOL-057 | maturity_candidate |
| P1-EVID-05 — Reproducibility bundle | blocked | P1-EVID-01, P1-EVID-03 | VOL-035, VOL-038, VOL-078, VOL-079 | maturity_candidate |
| P1-EVID-06 — Scope-freeze and ADR enforcement | blocked | P1-EVID-02 | VOL-000, VOL-420 | maturity_candidate |


### P1-L1 — Core Intelligence Quality & Convergence

**Objective.** Turn the already-functional inference/context/memory/retrieval/reasoning stack into a measured quality system with explicit trust, freshness, cost, stopping and verification semantics.

**Dependency position.** Depends on P1-L0. May overlap with P1-L2, P1-L3 when task dependencies are satisfied.

**Primary volume ownership (18).** VOL-008, VOL-009, VOL-010, VOL-011, VOL-012, VOL-013, VOL-014, VOL-248, VOL-251, VOL-252, VOL-253, VOL-254, VOL-255, VOL-361, VOL-362, VOL-363, VOL-369, VOL-370

**Supporting volumes.** VOL-005, VOL-007, VOL-034, VOL-035, VOL-037, VOL-139, VOL-159, VOL-216, VOL-241, VOL-242, VOL-243, VOL-244, VOL-245, VOL-246, VOL-247, VOL-354, VOL-355, VOL-356, VOL-357, VOL-358, VOL-359, VOL-364, VOL-365, VOL-366, VOL-367, VOL-368, VOL-371, VOL-372

**Work-package lineage.** WP-W05, WP-W06, WP-W07, WP-W08, WP-W09, WP-W10, WP-W11, WP-W12, WP-W17, WP-W18 via MBW-02, MBW-03, MBW-04, MBW-06.

**Target maturity.** `hardened`.

#### Implementation slices

- bind model routing decisions to quality/privacy/cost/latency evidence and deterministic no-route/fallback semantics
- measure context utility while preserving trust hierarchy, source identity and immutable policy under compression
- make memory/retrieval/knowledge quality, freshness, conflict and provenance decisions explicit and testable
- materialize reasoning/search strategy selection, value-of-information and stopping policies under bounded budgets
- build answer/artifact quality pipelines and reasoning regression suites independent of self-confidence
- bind plan verification/static analysis to preconditions, postconditions, evidence and executable failure semantics

#### Quantitative / structural gates

- 0 instruction-authority elevation from retrieved/tool/model-generated content
- 100% of production route decisions bind capability/privacy/budget/deadline reasons
- 100% of promoted quality baselines are versioned and reproducible
- 0 high-impact finalizations rely on model self-confidence alone

#### Required evidence modes

- quality_eval
- retrieval_eval
- context_adversarial
- property
- replay
- calibration

#### Fault families

- stale-or-conflicting-memory
- poisoned-retrieval
- context-budget-pressure
- wrong-scope-evidence
- nonterminating-search
- plan-invalidity

#### Acceptance

- routing/context/memory/retrieval decisions emit reproducible receipts linked to quality and policy constraints
- untrusted or stale context cannot escalate instruction authority or silently override fresher evidence
- reasoning/search loops terminate under explicit budget and stopping policy
- answer/artifact quality regression is versioned and blocks promotion when declared thresholds regress
- plan verification detects invalid dependencies, missing pre/postconditions and unsupported high-impact claims

#### Stop conditions

- quality optimization can widen privacy/authority or bypass budget ceilings
- retrieval/memory freshness or provenance is unavailable for a production decision
- reasoning strategy selection becomes an unbounded self-referential loop
- generator confidence is accepted as verification evidence

#### Task DAG

| Task | Status | Depends on | Volume refs | Promotion effect |
| --- | --- | --- | --- | --- |
| P1-INTEL-01 — Quality measurement and routing/context receipt spine | blocked | P1-EVID-01 | VOL-008, VOL-009, VOL-034 | maturity_candidate |
| P1-INTEL-02 — Memory, retrieval and knowledge quality authority | blocked | P1-INTEL-01, P1-EVID-05 | VOL-010, VOL-011, VOL-012, VOL-361, VOL-362, VOL-363 | maturity_candidate |
| P1-INTEL-03 — Reasoning, search and stopping policy registry | blocked | P1-INTEL-01 | VOL-013, VOL-248, VOL-251, VOL-252, VOL-253 | maturity_candidate |
| P1-INTEL-04 — Answer and artifact quality pipeline | blocked | P1-INTEL-02, P1-INTEL-03 | VOL-254, VOL-255, VOL-369 | maturity_candidate |
| P1-INTEL-05 — Plan verifier and static analysis | blocked | P1-INTEL-03, P1-EVID-04 | VOL-014, VOL-370, VOL-371, VOL-372 | maturity_candidate |
| P1-INTEL-06 — Core intelligence qualification bundle | blocked | P1-INTEL-02, P1-INTEL-04, P1-INTEL-05 | VOL-362, VOL-369, VOL-370 | maturity_candidate |


### P1-L2 — Safe Autonomous Action & Human Control

**Objective.** Make long-running tool and agent execution mechanically bounded by authority, sandbox, delegation, reversibility, human override and independent verification rather than role text or model intent.

**Dependency position.** Depends on P1-L0. May overlap with P1-L1, P1-L3 when task dependencies are satisfied.

**Primary volume ownership (27).** VOL-015, VOL-016, VOL-017, VOL-018, VOL-025, VOL-028, VOL-084, VOL-164, VOL-165, VOL-168, VOL-170, VOL-201, VOL-202, VOL-205, VOL-207, VOL-208, VOL-256, VOL-257, VOL-258, VOL-259, VOL-318, VOL-320, VOL-321, VOL-322, VOL-323, VOL-324, VOL-325

**Supporting volumes.** VOL-026, VOL-027, VOL-036, VOL-037, VOL-160, VOL-161, VOL-162, VOL-163, VOL-166, VOL-167, VOL-169, VOL-171, VOL-172, VOL-173, VOL-174, VOL-175, VOL-176, VOL-177, VOL-200, VOL-203, VOL-204, VOL-206, VOL-209, VOL-303, VOL-304, VOL-305, VOL-306, VOL-307, VOL-308, VOL-309, VOL-310, VOL-311, VOL-312, VOL-313, VOL-314, VOL-315, VOL-316, VOL-317, VOL-319, VOL-326, VOL-327, VOL-328, VOL-373, VOL-374, VOL-375, VOL-376, VOL-377, VOL-378, VOL-379, VOL-380

**Work-package lineage.** WP-W13, WP-W14, WP-W15, WP-W16, WP-W17, WP-W20 via MBW-03, MBW-04.

**Target maturity.** `hardened`.

#### Implementation slices

- normalize privileged tool execution onto one authority/admission/idempotency/sandbox/postcondition/receipt transaction
- materialize agent identity, handoff, delegation budgets and stale-lease/fencing constraints
- make autonomy levels, escalation/de-escalation and interrupt semantics explicit state transitions
- bind human approvals/overrides to exact arguments, authority, expiry and durable receipts
- classify reversibility, blast radius and changeset budgets before side effects
- turn goal drift, specification gaming and adversarial review into promotion-blocking evidence

#### Quantitative / structural gates

- 0 child-authority widening
- 0 committed external effects without durable receipts
- 100% of destructive/high-impact actions have reversibility/blast-radius classification
- 100% of human approvals bind exact operation/arguments/expiry
- 0 stale lease holders may commit

#### Required evidence modes

- authority_negative_test
- sandbox
- fault_injection
- replay
- adversarial
- human_control

#### Fault families

- authority-escalation
- approval-expiry
- stale-lease
- duplicate-side-effect
- sandbox-escape
- goal-drift
- specification-gaming

#### Acceptance

- child/agent authority is mechanically a subset of parent authority
- no external side effect occurs without an authorized, bounded, durable execution receipt
- stale leases, expired approvals and digest-mismatched approvals cannot commit
- human interrupt/de-escalation preserves durable state and prevents orphaned execution
- high-blast-radius or irreversible actions require explicit policy and independent verification

#### Stop conditions

- agent role or model text grants authority
- tool execution can bypass sandbox/admission/idempotency or postcondition verification
- autonomy can silently escalate after uncertainty or failure
- human override is UI-only and not bound to durable execution state

#### Task DAG

| Task | Status | Depends on | Volume refs | Promotion effect |
| --- | --- | --- | --- | --- |
| P1-AUTO-01 — Canonical privileged tool transaction and sandbox | blocked | P1-EVID-03 | VOL-015, VOL-164, VOL-165 | maturity_candidate |
| P1-AUTO-02 — Agent identity, handoff and delegation budgets | blocked | P1-AUTO-01 | VOL-016, VOL-017, VOL-201, VOL-202, VOL-205 | maturity_candidate |
| P1-AUTO-03 — Autonomy levels and de-escalation state machine | blocked | P1-AUTO-02, P1-INTEL-03 | VOL-018, VOL-318, VOL-320 | maturity_candidate |
| P1-AUTO-04 — Human override, interrupt and approval receipts | blocked | P1-AUTO-03 | VOL-084, VOL-256, VOL-321, VOL-322 | maturity_candidate |
| P1-AUTO-05 — Blast radius, reversibility and adversarial alignment | blocked | P1-AUTO-03, P1-EVID-04 | VOL-025, VOL-168, VOL-170, VOL-207, VOL-208, VOL-257, VOL-258, VOL-259, VOL-323, VOL-324, VOL-325 | maturity_candidate |
| P1-AUTO-06 — Safe autonomy qualification bundle | blocked | P1-AUTO-04, P1-AUTO-05 | VOL-028, VOL-208 | maturity_candidate |


### P1-L3 — Product Truth & Operator Surfaces

**Objective.** Expose durable runtime truth through API, streaming, web/desktop and long-running-work UX without creating presentation-layer authority.

**Dependency position.** Depends on P1-L0. May overlap with P1-L1, P1-L2 when task dependencies are satisfied.

**Primary volume ownership (7).** VOL-040, VOL-041, VOL-042, VOL-043, VOL-044, VOL-045, VOL-046

**Supporting volumes.** VOL-034, VOL-039, VOL-084, VOL-321, VOL-331

**Work-package lineage.** WP-W21, WP-W22, WP-W23, WP-W24 via MBW-05.

**Target maturity.** `verified`.

#### Implementation slices

- bind API schema/version compatibility to release gates
- make stream cursor/replay/resync and terminal finality canonical across clients
- define canonical product projection and workspace bindings
- materialize pause/resume/cancel/human-override semantics
- prove tenant identity and storage classification propagation through web/desktop surfaces

#### Quantitative / structural gates

- 0 UI authority over durable terminal state
- 100% terminal client state reconstructable from durable truth
- 100% stream-gap detection triggers authoritative resync

#### Required evidence modes

- api_contract
- reconnect_test
- tenant_isolation
- platform_test
- accessibility

#### Fault families

- duplicate-event
- out-of-order-event
- stream-gap
- cancel-complete-race
- refresh-during-operation
- tenant-misbinding

#### Acceptance

- UI state is projection-only and reconstructs from durable operation/event state
- refresh/reconnect/out-of-order/duplicate events reconcile deterministically
- cancel-complete races preserve terminal finality
- desktop and web permission/storage boundaries are explicitly tested
- tenant binding survives every API/stream/product hop

#### Stop conditions

- frontend optimistic state can override durable terminal state
- stream gaps cannot trigger authoritative resync
- desktop or web introduces provider credentials or new runtime authority

#### Task DAG

| Task | Status | Depends on | Volume refs | Promotion effect |
| --- | --- | --- | --- | --- |
| P1-PROD-01 — API schema and compatibility registry | blocked | P1-EVID-03 | VOL-041 | maturity_candidate |
| P1-PROD-02 — Streaming projection authority | blocked | P1-PROD-01, P1-EVID-01 | VOL-040, VOL-042, VOL-044 | maturity_candidate |
| P1-PROD-03 — Workspace and product projection contract | blocked | P1-PROD-02 | VOL-042, VOL-045 | maturity_candidate |
| P1-PROD-04 — Operator controls projection | blocked | P1-PROD-03, P1-AUTO-04 | VOL-045 | maturity_candidate |
| P1-PROD-05 — Web/desktop tenant and storage boundary | blocked | P1-PROD-01, P1-PROD-02, P1-AUTO-01 | VOL-043, VOL-044, VOL-046 | maturity_candidate |


### P1-L4 — Controlled Learning, Evaluation & Failure Knowledge

**Objective.** Convert feedback, research and experiments into bounded candidates whose improvement claims survive reproducible, adversarial and champion/challenger evaluation before release.

**Dependency position.** Depends on P1-L0, P1-L1, P1-L2, P1-L3. 

**Primary volume ownership (8).** VOL-023, VOL-024, VOL-077, VOL-082, VOL-083, VOL-414, VOL-415, VOL-419

**Supporting volumes.** VOL-001, VOL-035, VOL-036, VOL-037, VOL-038, VOL-410, VOL-416, VOL-417, VOL-418, VOL-324, VOL-369

**Work-package lineage.** WP-W18, WP-W26, WP-W27, WP-W28 via MBW-06.

**Target maturity.** `hardened`.

#### Implementation slices

- materialize experiment and benchmark registries with contamination metadata
- standardize candidate artifact, champion/challenger and shadow-comparison records
- bind specification-gaming and reasoning regressions to promotion gates
- preserve negative results, failed experiments and incidents as reusable regression knowledge
- keep learning signals, research branches and experimental features unable to mutate production directly

#### Quantitative / structural gates

- 0 candidate self-promotion
- 0 external shadow side effects
- 100% promoted benchmarks version/config/budget/provenance bound
- 100% rejected candidates retain decision evidence

#### Required evidence modes

- benchmark
- contamination_audit
- shadow
- champion_challenger
- adversarial
- reproducibility

#### Fault families

- benchmark-leakage
- specification-gaming
- candidate-self-promotion
- shadow-side-effect
- privacy-ineligible-shadow
- failed-experiment-loss

#### Acceptance

- candidate and evaluator cannot self-promote
- benchmark claims include version/environment/budget/provenance
- shadow traffic is side-effect isolated and privacy/eligibility bounded
- promotion compares quality, safety, robustness, cost and rollback evidence
- failure knowledge produces concrete regression/risk links

#### Stop conditions

- feedback directly mutates production behavior
- benchmark leakage or reward gaming is unresolved
- candidate comparison omits cost/security/rollback dimensions

#### Task DAG

| Task | Status | Depends on | Volume refs | Promotion effect |
| --- | --- | --- | --- | --- |
| P1-LEARN-01 — Experiment registry | blocked | P1-EVID-01, P1-INTEL-01 | VOL-077 | maturity_candidate |
| P1-LEARN-02 — Benchmark registry and contamination controls | blocked | P1-LEARN-01, P1-EVID-05, P1-INTEL-06 | VOL-082, VOL-035 | maturity_candidate |
| P1-LEARN-03 — Candidate and champion/challenger registry | blocked | P1-LEARN-01, P1-LEARN-02 | VOL-023, VOL-415 | maturity_candidate |
| P1-LEARN-04 — Shadow traffic isolation | blocked | P1-LEARN-03, P1-AUTO-05, P1-PROD-02 | VOL-414 | maturity_candidate |
| P1-LEARN-05 — Specification and reasoning regression corpus | blocked | P1-LEARN-02, P1-EVID-04 | VOL-324, VOL-369, VOL-083 | maturity_candidate |
| P1-LEARN-06 — Failure knowledge pipeline | blocked | P1-LEARN-05 | VOL-419, VOL-024 | maturity_candidate |


### P1-L5 — Release, Installation, Recovery & Operational Qualification

**Objective.** Prove install/update/repair/uninstall, deployment, backup/restore, disaster recovery, incident response and artifact provenance as one reversible release lifecycle.

**Dependency position.** Depends on P1-L2, P1-L3, P1-L4. May overlap with P1-L6 when task dependencies are satisfied.

**Primary volume ownership (14).** VOL-047, VOL-048, VOL-049, VOL-050, VOL-060, VOL-061, VOL-062, VOL-063, VOL-064, VOL-065, VOL-066, VOL-075, VOL-076, VOL-409

**Supporting volumes.** VOL-038, VOL-056, VOL-057, VOL-059, VOL-078, VOL-079, VOL-088

**Work-package lineage.** WP-W25, WP-W29, WP-W30 via MBW-07.

**Target maturity.** `production`.

#### Implementation slices

- bind installer/updater artifacts to release digest, SBOM/provenance and ownership manifests
- prove interrupted install/update/repair checkpoints and clean-machine recovery
- bind schema/data migrations to backward-readable rollback windows
- make backup coverage and restore dependency order machine-verifiable
- connect incident/postmortem outputs back into gap, risk and failure-knowledge ledgers
- generate attribution/notices from provenance for release bundles

#### Quantitative / structural gates

- 100% release artifacts bind provenance/SBOM/config/test evidence
- 100% declared backup authorities participate in restore drills
- 0 production promotion without tested rollback/recovery path

#### Required evidence modes

- clean_machine
- migration
- rollback
- restore_drill
- incident
- provenance

#### Fault families

- interrupted-install
- interrupted-update
- rollback-read-incompatibility
- backup-corruption
- partial-restore
- incident-recurrence

#### Acceptance

- clean-machine install/update/repair/uninstall is reproducible
- rollback can read durable state produced by the upgraded version within the declared window
- backup restore is exercised, not merely configured
- release bundle binds artifacts, config, SBOM, provenance, tests and rollback evidence
- incident actions feed back into accountable work

#### Stop conditions

- release depends on undocumented machine state
- rollback cannot read post-upgrade durable state
- backup exists without a successful restore drill

#### Task DAG

| Task | Status | Depends on | Volume refs | Promotion effect |
| --- | --- | --- | --- | --- |
| P1-REL-01 — Release evidence bundle | blocked | P1-EVID-05, P1-PROD-05, P1-LEARN-03, P1-AUTO-06 | VOL-060, VOL-075, VOL-076 | maturity_candidate |
| P1-REL-02 — Installer/update/repair lifecycle | blocked | P1-REL-01 | VOL-047, VOL-048, VOL-049, VOL-050 | maturity_candidate |
| P1-REL-03 — Migration and rollback compatibility | blocked | P1-REL-01, P1-REL-02 | VOL-048, VOL-061, VOL-063, VOL-062 | maturity_candidate |
| P1-REL-04 — Backup and restore qualification | blocked | P1-REL-03 | VOL-064, VOL-065 | maturity_candidate |
| P1-REL-05 — Disaster recovery and incident feedback | blocked | P1-REL-04, P1-LEARN-06 | VOL-065, VOL-066 | maturity_candidate |
| P1-REL-06 — Attribution and release notices | blocked | P1-REL-01 | VOL-409 | maturity_candidate |


### P1-L6 — Distributed Runtime, Capacity & Economics

**Objective.** Make distributed execution predictable under saturation, partition, failover and cost pressure with explicit resource topology, quotas, budgets and worker trust.

**Dependency position.** Depends on P1-L1, P1-L2, P1-L3. May overlap with P1-L5 when task dependencies are satisfied.

**Primary volume ownership (20).** VOL-029, VOL-030, VOL-031, VOL-067, VOL-068, VOL-069, VOL-381, VOL-382, VOL-385, VOL-386, VOL-390, VOL-391, VOL-392, VOL-397, VOL-398, VOL-399, VOL-403, VOL-404, VOL-405, VOL-406

**Supporting volumes.** VOL-007, VOL-008, VOL-034, VOL-349, VOL-368, VOL-394

**Work-package lineage.** WP-W25, WP-W29, WP-W30 via MBW-07.

**Target maturity.** `hardened`.

#### Implementation slices

- materialize remote execution envelope, worker registry, leases/fencing and attestation
- bind model placement/warming/batching/autoscaling to topology and capacity telemetry
- define canonical load profiles and saturation/load-shedding drills
- unify budget reservation/charge/reconciliation with routing and quota decisions
- backtest demand/capacity/cost forecasts and anomaly detection
- make cost/latency/quality tradeoffs evidence-bearing rather than implicit

#### Quantitative / structural gates

- 0 stale/unattested worker commits
- 100% budget reservations reconcile idempotently
- load shedding is bounded and policy-declared at measured saturation
- cost optimization never widens privacy/quality hard constraints

#### Required evidence modes

- load
- soak
- partition
- failover
- capacity
- cost_reconciliation

#### Fault families

- stale-worker
- network-partition
- capacity-exhaustion
- queue-congestion
- budget-race
- autoscaling-oscillation

#### Acceptance

- stale or unattested workers cannot commit
- capacity exhaustion degrades by declared load-shedding policy rather than collapse
- autoscaling/batching respect latency and cost budgets
- budget ledger is idempotent and reconcilable
- network/topology changes do not bypass fencing or data-boundary policy

#### Stop conditions

- distributed placement has no fencing or hard resource limits
- cost optimization can silently violate quality/privacy constraints
- capacity plans lack measured saturation evidence

#### Task DAG

| Task | Status | Depends on | Volume refs | Promotion effect |
| --- | --- | --- | --- | --- |
| P1-DIST-01 — Remote execution and worker trust | blocked | P1-EVID-03, P1-PROD-05, P1-AUTO-06 | VOL-030, VOL-398, VOL-399 | maturity_candidate |
| P1-DIST-02 — Topology-aware model placement and warming | blocked | P1-DIST-01 | VOL-031, VOL-381, VOL-382, VOL-385, VOL-392, VOL-397 | maturity_candidate |
| P1-DIST-03 — Batching and autoscaling controller | blocked | P1-DIST-02 | VOL-386, VOL-390 | maturity_candidate |
| P1-DIST-04 — Load and capacity qualification | blocked | P1-DIST-03 | VOL-067, VOL-068, VOL-391, VOL-029 | maturity_candidate |
| P1-DIST-05 — Quota and budget accounting ledger | blocked | P1-DIST-01, P1-EVID-01 | VOL-069, VOL-403, VOL-404 | maturity_candidate |
| P1-DIST-06 — Forecasting and cost anomaly loop | blocked | P1-DIST-04, P1-DIST-05 | VOL-405, VOL-406 | maturity_candidate |


### P1-L7 — Terminal P1 Trustworthy-Production Promotion

**Objective.** Assemble lane evidence into one exact-head, independently verified production-promotion decision without converting unresolved work into checkbox completion.

**Dependency position.** Depends on P1-L0, P1-L1, P1-L2, P1-L3, P1-L4, P1-L5, P1-L6. 

**Primary volume ownership (0).** None; terminal aggregation only.

**Supporting volumes.** VOL-034, VOL-035, VOL-036, VOL-037, VOL-038, VOL-060, VOL-065, VOL-066, VOL-067, VOL-068, VOL-069, VOL-078, VOL-079, VOL-080

**Work-package lineage.** WP-W25, WP-W29, WP-W30 via MBW-07.

**Target maturity.** `production`.

#### Implementation slices

- generate one exact-head P1 evidence bundle across all lanes
- verify target maturity and signed accountability for every primary volume
- run clean-machine, recovery, saturation, adversarial and rollback journeys
- assert all original P0 and P1 construction gaps remain closed
- publish residual non-P1 masterplan work explicitly rather than hiding it

#### Quantitative / structural gates

- 100% lane evidence exact-head
- 0 open canonical P0/P1 construction gaps
- 0 unresolved critical/high blockers without signed accepted-risk disposition
- 100% primary P1 volumes meet lane maturity floor before promotion

#### Required evidence modes

- exact_head_bundle
- independent_verification
- clean_machine
- recovery
- load
- adversarial

#### Fault families

- stale-evidence
- reopened-canonical-gap
- unsigned-promotion
- residual-critical-blocker
- release-recovery-failure

#### Acceptance

- all 64 primary P1 frontier volumes meet their lane maturity floor
- all lane gates are exact-head and independently verifiable
- no critical/high blocker lacks passing evidence or signed accepted-risk disposition
- clean-machine release, rollback, disaster recovery and capacity-failure journeys pass
- remaining 357 masterplan volumes are still represented honestly as later work

#### Stop conditions

- any original P0/P1 construction gap reopens
- any lane evidence is stale relative to the promotion head
- production label depends on planned tests or unsigned evidence

#### Task DAG

| Task | Status | Depends on | Volume refs | Promotion effect |
| --- | --- | --- | --- | --- |
| P1-PROM-01 — Aggregate exact-head P1 evidence | blocked | P1-EVID-06, P1-PROD-04, P1-PROD-05, P1-LEARN-04, P1-LEARN-06, P1-REL-05, P1-REL-06, P1-DIST-06, P1-INTEL-06, P1-AUTO-06 | — | terminal_candidate |
| P1-PROM-02 — Terminal failure-journey qualification | blocked | P1-PROM-01 | — | terminal_candidate |
| P1-PROM-03 — Independent signed P1 promotion decision | blocked | P1-PROM-02 | — | terminal_candidate |

## 6. Task execution contract

Every P1 task carries lane ownership, work-package lineage, exact volume scope, explicit dependencies, implementation paths, test targets, evidence modes, multiple acceptance checks, known failure modes, rollback/recovery behavior, a planned accountability identity, and an explicit maturity effect.

A task becoming `done` does **not** itself promote a masterplan volume. It only makes the task eligible to contribute evidence to a separate signed maturity decision.

The only initially ready task is `P1-EVID-01`. All other tasks are blocked by the DAG until their prerequisites are complete.

## 7. Critical path

```text
P1-L0 evidence authority
  -> P1-L1 core intelligence quality
  -> P1-L2 safe autonomy / human control
  -> P1-L3 product truth

Product truth + intelligence + autonomy
  -> P1-L4 controlled learning
  -> P1-L5 release / recovery
  -> P1-L6 distributed capacity / economics
  -> P1-L7 terminal promotion

Task anchors:
P1-EVID-01
  -> P1-INTEL-01 ... P1-INTEL-06
  -> P1-AUTO-01 ... P1-AUTO-06
  -> P1-PROD-02
  -> P1-LEARN-04 shadow traffic
  -> release/distributed qualification
  -> P1-PROM-01 -> P1-PROM-02 -> P1-PROM-03
```

## 8. Evidence and promotion semantics

P1 evidence must be exact-head, configuration/environment/verifier-bound, reproducible where applicable, attributable to task/lane/accountability identity, independently verifiable for high-impact maturity promotion, and unable to self-sign its own promotion.

Merged code, planned tests, documentation, model confidence, or a green aggregate status hiding a known blocker are never sufficient by themselves.

## 9. Maturity floors

- Evidence spine: **verified**
- Core intelligence: **hardened**
- Safe autonomy: **hardened**
- Product truth: **verified**
- Controlled learning: **hardened**
- Release/recovery: **production**
- Distributed capacity/economics: **hardened**
- Terminal promotion: **production decision**, independently signed or explicitly rejected

## 10. Global failure-journey program

- restart/crash
- partial commit
- duplicate/reordered delivery
- provider outage/failover
- policy denial/revocation
- stream disconnect/resync
- rollback/migration incompatibility
- capacity exhaustion/backpressure
- network partition/stale lease
- benchmark leakage/specification gaming
- malicious or stale evidence
- stale or conflicting memory/retrieval evidence
- authority escalation or expired approval
- goal drift/specification gaming
- duplicate external side effect
- human interrupt during autonomous execution

## 11. Explicit deferred scope

P1 deliberately leaves **314 volumes** outside primary ownership.

Rule: Deferred volumes remain visible target work. They are not P1 blockers unless a P1 task explicitly references them as supporting scope or discovers a hard dependency requiring formal map amendment.

### P1+-NATIVE-MODEL-MULTIMODAL

Native training, broad multimodal pipelines and specialist model R&D beyond the P1 production spine.

Examples: VOL-006, VOL-020, VOL-143, VOL-153.

### P1+-ENTERPRISE-EDGE-PROFILES

Air-gapped, edge, enterprise federation/admin and specialized deployment profiles.

Examples: VOL-229, VOL-230, VOL-231, VOL-232, VOL-233.

### P1+-REPOSITORY-SDK-GENERATION

Broader repository compiler, SDK generation and consolidation automation after P1 operational truth is hardened.

Examples: VOL-264, VOL-340, VOL-341, VOL-342, VOL-347.

### P1+-ADVANCED-FORMAL-RESEARCH

Advanced formal/control/causal research not required to prove the bounded P1 production frontier.

Examples: VOL-200, VOL-249, VOL-250, VOL-284, VOL-339.

### P1+-HARDWARE-FARM-OPTIMIZATION

Deep GPU/cache/topology/farm optimization beyond the P1 distributed capacity minimum.

Examples: VOL-383, VOL-387, VOL-393, VOL-400, VOL-401.


The complete deferred set is machine-enforced as the exact complement of the 107 primary volumes.

## 12. Operating cadence

1. choose the highest-priority ready task whose dependencies are satisfied;
2. materialize its accountability record/start event before `in_progress`;
3. implement the smallest coherent contract slice;
4. add focused positive/negative/fault coverage;
5. collect exact-head evidence;
6. move to `evidence_pending`;
7. obtain independent verification;
8. mark task done;
9. separately evaluate affected volume maturity;
10. only then unlock dependent tasks.

## 13. First implementation wave

The first deep P1 pass should concentrate on:

- `P1-EVID-01` canonical evidence identity;
- `P1-EVID-03` required-gate authority map;
- `P1-INTEL-01` quality/routing/context receipt spine;
- `P1-AUTO-01` canonical privileged tool transaction/sandbox.

These create the proof, quality and authority substrate for later P1 lanes.

## 14. Terminal definition

P1 is terminal only when:

- P1 Terminal Closure Gate remains green
- Masterplan Completion Gate remains green
- P1 Execution Map Gate validates the exact promotion head
- core intelligence and safe-autonomy qualification bundles are independently verified
- App Assembly, Backend Quality, Merge Readiness and CI/CD are green on the promotion head
- Workflow Input Security, Secret scanning, Malware Gate and dependency/provenance policies are green
- ARM64 and supported platform/install paths are validated
- all P1 lane-specific evidence is bound into the signed accountability graph

Additionally, every primary volume must be touched by at least one executable task, all critical/high blockers must carry passing evidence or signed accepted-risk disposition, the original P0/P1 construction gaps remain closed, and deferred volumes remain explicitly represented as later work.

A failed terminal review is a valid outcome: the system remains unpromoted and the rejection becomes durable evidence for the next repair cycle.
