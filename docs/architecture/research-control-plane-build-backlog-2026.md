
# Research Control Plane Build Backlog — 2026

Status: implementation-ready backlog for Track AD
Updated: 2026-09-22
Parent: research-control-plane-internals-2026.md

## 0. Rules

Every backlog item has:
- stable ID;
- milestone;
- dependency;
- artifact;
- acceptance test;
- failure condition.

No checkbox is considered complete from prose alone.

## M0 — Core contracts, identity, store, migrations

### RCB001 — Research package scaffold
Create `skeleton/research/` and all top-level subpackages declared in the internals manual.

Acceptance:
- import smoke succeeds;
- package has no side effects;
- no network calls on import.

### RCB002 — Typed identifier primitives
Implement typed IDs for work/evidence/claim/debt/protocol/manifest/run/result/benchmark/evaluator/artifact/review.

Acceptance:
- invalid prefixes rejected;
- round-trip serialization;
- equality/hash stable.

### RCB003 — Canonical serialization
Implement deterministic canonical JSON for signed/digested research objects.

Acceptance:
- dictionary insertion order cannot change digest;
- equivalent timestamps normalize identically;
- schema version participates in digest.

### RCB004 — Research enums
Implement source status, evidence class, debt state, run state, result state, reproduction class, compute class.

Acceptance:
- unknown enum values fail closed on authoritative writes;
- historical unknown values can be read through migration compatibility layer.

### RCB005 — Error taxonomy
Create typed errors:
- validation;
- conflict;
- stale lease;
- budget exceeded;
- artifact mismatch;
- blind-eval violation;
- forbidden transition;
- external unknown outcome.

Acceptance:
- command layer maps errors deterministically.

### RCB006 — Development SQLite backend
Implement development/test relational store.

Acceptance:
- all M0 aggregates persist;
- restart preserves state;
- transaction rollback proven.

### RCB007 — Postgres backend contract
Define production-capable relational backend interface and initial implementation.

Acceptance:
- backend parity contract with SQLite;
- transaction/isolation semantics documented.

### RCB008 — Blob store interface
Implement content-addressed artifact store abstraction.

Acceptance:
- digest verified on put/get;
- duplicate content de-duplicates safely;
- partial upload never appears complete.

### RCB009 — Migration framework
Version research schema.

Acceptance:
- up migration;
- rollback where supported;
- historical fixture migration test;
- failed migration leaves recoverable state.

### RCB010 — Aggregate versioning
Add optimistic concurrency version to mutable aggregates.

Acceptance:
- stale update receives conflict;
- caller sees current version.

### RCB011 — Outbox
Implement transactional event outbox.

Acceptance:
- DB mutation and event cannot diverge;
- consumer replay idempotent.

### RCB012 — Audit envelope
Every authoritative command records actor, time, object, previous/new version, digest.

Acceptance:
- mutation without audit record is impossible.

## M1 — Source identity, attestations, evidence graph

### RCB013 — WorkIdentity model
Implement work identity with multiple source manifestations.

Acceptance:
- arXiv/OpenReview/DOI/code links can coexist;
- titles are not unique keys.

### RCB014 — Exact identifier resolver
Resolve canonical source identifiers.

Acceptance:
- malformed IDs rejected;
- exact ID collision surfaced.

### RCB015 — Candidate fuzzy resolver
Generate but do not auto-commit fuzzy matches.

Acceptance:
- candidate confidence is advisory;
- manual reject supported.

### RCB016 — False-merge recovery
Split incorrectly merged WorkIdentity records while preserving lineage.

Acceptance:
- evidence reassignment auditable;
- no evidence silently lost.

### RCB017 — SourceStatusAttestation
Append-only status/version observation.

Acceptance:
- SUBMISSION→ACCEPTED creates new row;
- historical query returns old status.

### RCB018 — Source adapter base contract
Define adapter interface for discover/resolve/metadata/version/status/artifact/correction.

Acceptance:
- adapter cannot mutate claim/debt tables.

### RCB019 — arXiv adapter
Metadata + version/status retrieval.

Acceptance:
- version change receipt;
- identifier exactness.

### RCB020 — OpenReview adapter
Forum/revision/decision/withdrawal retrieval.

Acceptance:
- submitted/accepted/withdrawn preserved distinctly.

### RCB021 — Proceedings adapter family
ACL/PMLR/NeurIPS/CVF-style official publication sources.

Acceptance:
- publication identity bound to venue version.

### RCB022 — Bibliographic adapter family
Crossref/OpenAlex/DBLP/Semantic Scholar as discovery/metadata sources.

Acceptance:
- secondary graph never upgrades review status by itself.

### RCB023 — Artifact adapter family
GitHub/Hugging Face/Zenodo-style code/model/data artifacts.

Acceptance:
- exact commit/revision recorded.

### RCB024 — Correction/retraction watcher
Publisher/venue correction signal ingestion.

Acceptance:
- affected claims marked review_due, not deleted.

### RCB025 — EvidenceRecord model
Persist scoped evidence with methods/population/hardware/eval fields.

Acceptance:
- missing scope fields explicit;
- unknown != null-is-success.

### RCB026 — Claim model
Persist narrow claim plus support/opposition.

Acceptance:
- one evidence item can support multiple claims;
- claim scope explicit.

### RCB027 — Contradiction model
Open typed contradiction edges.

Acceptance:
- conflicting evidence cannot be silently averaged.

### RCB028 — Independence graph
Track shared lab/model/data/code/benchmark/evaluator/provider.

Acceptance:
- connected-components query;
- raw count and independent-cluster count differ when correlated.

### RCB029 — Claim expiry
Implement review_at and invalidation triggers.

Acceptance:
- stale claim retained but cannot justify new promotion silently.

### RCB030 — Research decision snapshot
Freeze exact evidence state used by consequential ADR proposal.

Acceptance:
- historical reconstruction exact.

## M2 — Protocols, manifests, runs, result bundles

### RCB031 — Protocol registry
Load/version RXP001–RXP062.

Acceptance:
- duplicate protocol version rejected;
- digest stable.

### RCB032 — Protocol validator
Validate required metrics/controls/baselines/falsification/stop/debt targets.

Acceptance:
- incomplete consequential protocol fails freeze.

### RCB033 — Preregistration object
Freeze primary metric, baseline, thresholds, analysis plan.

Acceptance:
- post-result edits require new exploratory version.

### RCB034 — ExperimentManifest model
Bind protocol/code/config/data/model/evaluator/hardware/seed/budget.

Acceptance:
- manifest digest immutable;
- missing identity blocks launch.

### RCB035 — Environment manifest
Capture OS/runtime/dependencies/drivers/device info.

Acceptance:
- exact environment attached to result.

### RCB036 — Data manifest binding
Bind dataset versions/digests/splits/lineage.

Acceptance:
- changed data changes manifest digest.

### RCB037 — Evaluator binding
Bind evaluator identity/version/prompt/scorer.

Acceptance:
- evaluator drift invalidates comparison cache.

### RCB038 — Benchmark binding
Bind benchmark version/custody/access class.

Acceptance:
- blind benchmark cannot be attached to research-agent-readable workspace.

### RCB039 — Run state machine
Implement state transitions.

Acceptance:
- invalid transition rejected;
- every transition receipt-backed.

### RCB040 — Run lease
Lease active run to worker with epoch.

Acceptance:
- expired/stale worker cannot finalize.

### RCB041 — Run cancellation
Cooperative cancel then bounded escalation.

Acceptance:
- cancellation state deterministic;
- partial outputs remain non-authoritative.

### RCB042 — Checkpoint manifest
Atomic checkpoint publication.

Acceptance:
- missing part blocks checkpoint availability.

### RCB043 — RNG/data cursor capture
Record reproducibility-critical cursor and randomness state.

Acceptance:
- resumed deterministic fixture matches uninterrupted fixture.

### RCB044 — FailureRecord
Persist failure category separately from scientific result.

Acceptance:
- infrastructure failure cannot become NULL_RESULT automatically.

### RCB045 — ComputeCost
Capture accelerator/CPU/storage/network/API/human dimensions.

Acceptance:
- lifecycle cost query works per run/result/protocol/domain.

### RCB046 — Result bundle
Create complete result object.

Acceptance:
- validity and scientific_state separate;
- raw artifacts referenced by digest.

### RCB047 — Baseline parity review
Structured parity checklist.

Acceptance:
- result can be marked INVALID_BASELINE.

### RCB048 — Multiple-comparison ledger
Store attempted configs/search budget.

Acceptance:
- architecture search cannot hide trial count.

### RCB049 — Failed-run inclusion
Aggregate result references failed/diverged runs.

Acceptance:
- no silent denominator drop.

### RCB050 — Result reconstruction
Re-run analysis code from result bundle.

Acceptance:
- reported primary metrics reproduce bit-for-bit or declared tolerance.

## M3 — Scheduler, budgets, reconciliation

### RCB051 — Dependency graph
Encode protocol prerequisites and blocked decisions.

Acceptance:
- scheduler refuses unmet prerequisite.

### RCB052 — Work order
Generate ResearchWorkOrder.

Acceptance:
- explains priority and blocker expected to clear.

### RCB053 — Compute class
Enforce C0–C5 limits.

Acceptance:
- C5 requires signed decision-value review.

### RCB054 — Budget reservation
Reserve compute/currency/API/human-review envelope.

Acceptance:
- concurrent launches cannot overspend one budget.

### RCB055 — Budget fencing
Tie spend authority to run lease.

Acceptance:
- stale worker cannot consume new budget.

### RCB056 — Idempotent launch
Launch with durable idempotency key.

Acceptance:
- duplicate client request returns same external job.

### RCB057 — Unknown-outcome reconciler
On timeout, query external provider before retry.

Acceptance:
- no double launch under injected response loss.

### RCB058 — External job map
Persist provider job ID ↔ RunId.

Acceptance:
- orphan detector can reconcile.

### RCB059 — Orphan recovery
Detect worker/job mismatch.

Acceptance:
- recover, cancel, or mark unknown with evidence.

### RCB060 — Scheduler fairness
Prevent one domain/agent from monopolizing queue.

Acceptance:
- starvation test.

### RCB061 — Freshness priority input
Boost due source/status/benchmark revalidation.

Acceptance:
- freshness never bypasses safety prerequisite.

### RCB062 — Reviewer capacity input
Do not create unreviewable experiment flood.

Acceptance:
- configurable WIP limit.

## M4 — Evaluation registry and custody

### RCB063 — Benchmark registry
Implement identity/version/release/population/scorer/status.

### RCB064 — Benchmark custody ledger
Record hidden answer accesses and exports.

Acceptance:
- unauthorized access blocked and audited.

### RCB065 — Evaluator registry
Implement deterministic/learned/human/formal evaluator types.

### RCB066 — Evaluator calibration record
Store calibration population and metrics.

### RCB067 — Contamination record
Store exact/near/semantic exposure evidence.

### RCB068 — Saturation state
Healthy/narrowing/saturated/contaminated/unstable/retired.

### RCB069 — Anchor set
Support fixed anchors for dynamic benchmarks.

### RCB070 — Equivalence region
Define operational no-material-difference bands.

### RCB071 — Metric sensitivity
Run declared alternate metrics.

### RCB072 — Blind promotion boundary
Separate research selection eval from promotion holdout.

Acceptance:
- research principal cannot query hidden answers.

## M5 — Review, signoff, ADR bridge

### RCB073 — ReproductionRecord
Capture sanity/paper-scale/transfer/systems/adversarial/negative/independent.

### RCB074 — IndependentReview
Structured reviewer object.

### RCB075 — Reviewer independence check
Detect obvious same-agent/same-run conflicts.

### RCB076 — Review signature
Sign result review digest.

### RCB077 — Debt transition proposal
Result may propose debt transition.

Acceptance:
- proposal != committed transition.

### RCB078 — Debt transition reviewer
Apply evidence-backed transition transactionally.

### RCB079 — ADR candidate
Generate ADR proposal with evidence/debt/contradictions/rollback implications.

### RCB080 — No self-accept
Research system cannot accept ADR.

### RCB081 — Challenge workflow
Reviewer can reopen contradiction/debt.

### RCB082 — Reproduction request
Review can require stronger reproduction class before decision.

## M6 — Freshness, invalidation, scorecard

### RCB083 — Source freshness worker
Check source versions/status within SLA.

### RCB084 — Source change receipt
Persist old/new observation.

### RCB085 — Claim invalidation
Material source change marks claims review_due.

### RCB086 — Benchmark invalidation
Correction/contamination invalidates dependent evidence.

### RCB087 — Evaluator invalidation
Changed evaluator marks dependent comparisons review_due.

### RCB088 — Model-generation invalidation
Monitorability/calibration evidence expires on material model change.

### RCB089 — Compression invalidation
Interpretability evidence expires after deployment artifact surgery unless revalidated.

### RCB090 — Debt aging dashboard
Age/owner/deadline/blockers.

### RCB091 — Planning/reproduction/readiness dashboard
Three independent views.

### RCB092 — Research scorecard
Expose counts without scalar completion score.

### RCB093 — Information-yield report
Cost vs uncertainty/debt/decision change.

### RCB094 — Freshness alerting
Alert only actionable stale evidence.

## M7 — Research-agent sandbox

### RCB095 — ResearchPrincipal
Authenticated agent principal.

### RCB096 — Capability tiers R0–R3
Explicit allowed actions.

### RCB097 — Workspace
Ephemeral isolated workspace per task/run.

### RCB098 — No ambient credentials
Credentials are task-scoped capabilities.

### RCB099 — Network egress policy
Default-deny or allowlisted research egress.

### RCB100 — Source artifact quarantine
Fetched code/PDF/archive/model remains data until scanned and promoted.

### RCB101 — Anti-cheat monitor
Detect hidden eval/scorer/protocol tampering attempts.

### RCB102 — Agent trajectory log
Durable tool/action trajectory.

### RCB103 — Generated-data lineage
Every generated training/eval artifact traces teacher/prompt/config.

### RCB104 — Self-review prohibition
Agent cannot sign its own independent reproduction.

### RCB105 — C0/C1 autonomous execution
Allow only after sandbox and manifest gates.

### RCB106 — Agent cost/ROI metrics
Track useful accepted work vs oversight/recompute cost.

## M8 — C2+ integration and resilience

### RCB107 — C2 launch approval
Require approved manifest.

### RCB108 — C3 confirmation approval
Require proxy evidence and scale-transfer question.

### RCB109 — C4 systems campaign
Require fault plan and recovery capacity.

### RCB110 — C5 frontier run
Require signed decision value, hard ceiling, abort rule.

### RCB111 — Safe mode
Disable expensive launches and executable ingestion.

### RCB112 — Restore drill
Restore relational/audit/blob references.

### RCB113 — External reconciliation after restore
Reconcile live external jobs before replay.

### RCB114 — Lease invalidation after restore
Old leases invalid.

### RCB115 — Event replay
Reconstruct aggregate state deterministically.

### RCB116 — Blob integrity sweep
Verify all authoritative references resolve/digest.

### RCB117 — Deletion propagation
Tombstone + derived index/cache cleanup.

### RCB118 — Retention enforcement
Artifact classes expire/archive lawfully.

### RCB119 — Disaster exercise
DB outage + object-store partial outage + active run.

### RCB120 — End-to-end authority proof
Demonstrate no path:
research agent -> accepted result -> production mutation
without independent review + ADR + production gates.

## Cross-milestone acceptance suite

### RCB-A01 — Status-history replay
Preprint -> submission -> accepted -> correction remains reconstructable.

### RCB-A02 — Negative result retention
Falsified hypothesis remains queryable and affects debt/claim graph.

### RCB-A03 — Failed-run retention
OOM/divergence is included in experiment history.

### RCB-A04 — Duplicate launch
Lost HTTP response cannot create two paid jobs.

### RCB-A05 — Blind-eval attack
Research agent cannot access hidden promotion answers.

### RCB-A06 — Stale lease attack
Old worker cannot finalize result.

### RCB-A07 — Scorer tamper
Changed evaluator digest invalidates result.

### RCB-A08 — Source retraction
Retraction opens review without deleting old ADR snapshot.

### RCB-A09 — Restore with live job
No duplicate external side effect after restore.

### RCB-A10 — Production authority
Research subsystem has zero direct production mutation permission.

## Backlog checkpoint

~~~text
checkpoint_id: PLAN-20260922-RESEARCH-CONTROL-PLANE-BACKLOG
created_at: 2026-09-22
backlog_ids: RCB001..RCB120
cross_acceptance: RCB-A01..RCB-A10
milestones: M0..M8
production_authority_granted: false
completion_requires_test_evidence: true
~~~
