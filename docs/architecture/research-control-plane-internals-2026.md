
# Research Control Plane Internals — 2026

Status: canonical implementation blueprint for Track AD
Updated: 2026-09-22
Authority: construction contract; production authority remains false

Companions:
- frontier-research-atlas-2026.md
- frontier-research-experiment-protocols-2026.md
- research-evidence-evolution.md
- research-dependency-map-2026.md
- research-execution-program-2026.md
- research-program-scorecard-2026.md

## 0. Objective

Implement a research system that can ingest changing evidence, design and execute experiments, preserve negative results, update research debt, and propose architecture decisions without ever granting itself production authority.

Core law:

~~~text
source
 -> identity/status
 -> evidence
 -> claim
 -> contradiction/debt
 -> protocol
 -> immutable run manifest
 -> result bundle
 -> independent review
 -> ADR proposal
 -> shadow/canary
 -> production promotion

NO DIRECT EDGE:
source -> production
agent result -> production
benchmark score -> production
~~~

## 1. Package layout

Target module tree:

~~~text
skeleton/research/
  __init__.py
  ids.py
  enums.py
  errors.py
  clocks.py

  identity/
    work_identity.py
    artifact_identity.py
    source_identity.py
    resolver.py

  evidence/
    evidence_record.py
    source_attestation.py
    claim.py
    contradiction.py
    lineage.py
    independence.py
    confidence.py

  debt/
    research_debt.py
    transitions.py
    retirement.py

  protocols/
    protocol.py
    manifest.py
    preregistration.py
    validators.py
    registry.py

  runs/
    run_record.py
    result_bundle.py
    raw_artifacts.py
    failure_record.py
    cost_record.py
    environment.py

  evals/
    benchmark_identity.py
    benchmark_custody.py
    evaluator_identity.py
    contamination.py
    saturation.py
    equivalence.py

  scheduler/
    dependency_graph.py
    queue.py
    priority.py
    prerequisites.py
    compute_classes.py
    leases.py

  review/
    reproduction.py
    independent_review.py
    decision.py
    signoff.py

  refresh/
    source_watch.py
    status_diff.py
    freshness.py
    invalidation.py

  agents/
    research_principal.py
    capability_policy.py
    workspace.py
    trajectory.py
    anti_cheat.py

  store/
    repository.py
    sqlite_backend.py
    postgres_backend.py
    blob_backend.py
    migrations.py
    transactions.py

  api/
    service.py
    query.py
    commands.py
    receipts.py

  observability/
    events.py
    metrics.py
    audit.py
    health.py

  cli/
    researchctl.py
~~~

No module may bypass the store/transaction boundary for authoritative mutation.

## 2. Identity primitives

### 2.1 Typed IDs

Never use free-form strings as implicit identities after ingestion.

~~~text
WorkId
EvidenceId
ClaimId
ContradictionId
ResearchDebtId
ProtocolId
ManifestId
RunId
ResultBundleId
BenchmarkId
EvaluatorId
ArtifactId
SourceAttestationId
ReviewId
AdrCandidateId
~~~

Requirements:
- immutable once issued;
- globally unique within repository;
- human-readable prefix where useful;
- canonical lowercase storage form;
- parse/validate at boundaries;
- no identity derived only from mutable title.

### 2.2 Canonical digest

All signed objects use deterministic serialization:

~~~text
canonical_json(object)
 -> UTF-8
 -> sorted keys
 -> normalized numbers
 -> normalized timestamps
 -> no insignificant whitespace
 -> SHA-256 / stronger policy-selected digest
~~~

Digest excludes:
- transport metadata;
- database row IDs;
- local cache timestamps.

Digest includes:
- semantic content;
- referenced artifact IDs;
- declared schema version.

## 3. Work identity graph

One scientific work may have many manifestations.

~~~text
WorkIdentity
  work_id
  canonical_title
  authors[]
  identities[]
    arxiv
    openreview
    doi
    proceedings
    repository
  versions[]
  artifacts[]
  corrections[]
  retractions[]
  replications[]
~~~

Resolution must support:
- exact identifier link;
- author/title fuzzy candidate;
- manual adjudication;
- non-merge decision;
- split decision when a revision becomes materially different.

False merge is considered more damaging than temporary duplication because it corrupts evidence independence.

## 4. Source attestation store

Append-only semantic rule:

~~~text
SourceStatusAttestation(
  work_id,
  source_family,
  exact_identifier,
  exact_version,
  status,
  observed_at,
  decision_status,
  primary_source_ref,
  metadata_digest,
  verifier
)
~~~

Updates create new attestations.

Queries may expose:
- latest status;
- status at historical decision time;
- full transition chain.

Never overwrite:
SUBMISSION -> ACCEPTED
or
PREPRINT -> RETRACTED.

## 5. Evidence record

~~~text
EvidenceRecord
  evidence_id
  work_id?
  evidence_class
  source_attestation_id?
  observed_claim
  population
  model_family
  model_artifact
  data_scope
  hardware_scope
  inference_protocol
  evaluation_scope
  effect
  uncertainty
  methods_complete
  artifact_refs[]
  independence_edges[]
  limitations[]
  created_at
  review_at
~~~

Evidence classes:
- foundational;
- peer_reviewed;
- preprint;
- official_operational;
- local_reproduction;
- local_negative;
- incident;
- formal_proof;
- benchmark;
- source_code;
- standard;
- counterevidence.

Evidence class affects interpretation, never direct authority.

## 6. Claim object

Claims are narrower than documents.

~~~text
Claim
  claim_id
  statement
  scope
  required_conditions[]
  supporting_evidence[]
  opposing_evidence[]
  confidence
  maturity
  current_posture
  architecture_dependencies[]
  expires_at?
  refresh_triggers[]
~~~

One paper can support multiple claims with different confidence.

One claim can have:
- strong mechanism evidence;
- weak scale evidence;
- negative systems evidence.

Do not compress these dimensions into one scalar.

## 7. Contradiction graph

~~~text
Contradiction
  contradiction_id
  claim_a
  claim_b
  type
  suspected_scope_difference[]
  suspected_method_difference[]
  discriminating_protocol_ids[]
  status
  resolution_evidence[]
~~~

Types:
- direct_result_conflict;
- scope_conflict;
- metric_conflict;
- scale_conflict;
- systems_vs_algorithmic;
- semantic_definition_conflict;
- maturity_conflict.

The graph may resolve tension without declaring either source globally wrong.

## 8. Research debt object

~~~text
ResearchDebt
  debt_id
  assumption
  risk_if_wrong
  blocked_decisions[]
  required_evidence
  candidate_protocols[]
  owner
  state
  opened_at
  last_activity_at
  refresh_at
  retirement_scope
  retirement_evidence[]
  reopened_from?
~~~

Transition validation is centralized.

Forbidden transition:
~~~text
OPEN -> RETIRED
~~~
without retirement evidence.

Allowed:
~~~text
OPEN
 -> EXPERIMENT_DESIGNED
 -> RUNNING
 -> EVIDENCE_COLLECTED
 -> CHALLENGED
 -> RETIRED | PARTIALLY_RETIRED | INVALIDATED | DEFERRED
~~~

## 9. Protocol registry

Protocol definitions are immutable by version.

~~~text
ExperimentProtocol
  protocol_id
  version
  question
  hypothesis
  null_hypothesis
  controls[]
  baselines[]
  variables[]
  held_constant[]
  workloads[]
  metrics[]
  tuning_budget
  seed_policy
  hardware_requirements
  stop_rule
  failure_rule
  falsification_rule
  debt_targets[]
  expected_artifacts[]
  protocol_digest
~~~

Editing a protocol after seeing results creates a new version.

## 10. Experiment manifest

The manifest is the executable frozen instance of a protocol.

~~~text
ExperimentManifest
  manifest_id
  protocol_id
  protocol_version
  code_commit
  code_tree_digest
  config_digest
  data_manifest
  model_artifact_ids[]
  evaluator_ids[]
  benchmark_ids[]
  hardware_request
  software_environment
  seed_set
  tuning_budget
  cost_ceiling
  wall_clock_ceiling
  blind_eval_access_policy
  network_policy
  artifact_destinations
  abort_conditions[]
  created_by
  approved_by?
  created_at
  manifest_digest
~~~

No run starts without a valid manifest.

## 11. Run state machine

~~~text
QUEUED
 -> LEASED
 -> PREPARING
 -> RUNNING
 -> CHECKPOINTING*
 -> ANALYZING
 -> RESULT_PENDING_REVIEW
 -> COMPLETED

failure exits:
 PREPARING -> INVALID_ENVIRONMENT
 RUNNING -> FAILED
 RUNNING -> ABORTED
 RUNNING -> RESOURCE_EXHAUSTED
 RUNNING -> SAFETY_ABORT
 ANALYZING -> INVALID_MEASUREMENT
 any active -> CANCELLED
~~~

State transitions are idempotent and receipt-backed.

## 12. Run leases and fencing

Research runners are distributed writers.

Every lease contains:
- run_id;
- lease_epoch;
- worker_identity;
- issued_at;
- expires_at.

Mutation requires current lease epoch.

A stale worker cannot:
- append final result;
- close run;
- write authoritative checkpoint metadata;
- consume additional budget.

## 13. Checkpoint contract

Checkpoint identity includes:
- model state;
- optimizer state;
- scheduler state;
- RNG state;
- data cursor;
- dataloader sharding;
- precision/scaler state;
- topology where semantically material;
- code/config identity.

Checkpoint completeness uses manifest-atomic publication:

~~~text
upload parts
 -> verify digests
 -> publish checkpoint manifest
 -> atomically mark available
~~~

Partial parts are not valid checkpoints.

## 14. Raw artifact store

Large outputs stay out of relational rows.

Artifact metadata:

~~~text
RawArtifact
  artifact_id
  kind
  content_digest
  size
  media_type
  storage_uri
  created_at
  producer_run_id
  schema_version?
  encryption_class
  retention_class
~~~

Kinds:
- logs;
- metrics parquet/jsonl;
- checkpoint;
- generated dataset;
- profiler trace;
- evaluator outputs;
- analysis notebook export;
- plot source data.

## 15. Failure record

Failures are first-class.

~~~text
FailureRecord
  run_id
  stage
  failure_class
  observed_at
  exception_type?
  message_redacted
  exit_code?
  resource_state
  last_checkpoint?
  retryable
  retry_reason
  diagnostic_artifacts[]
~~~

Failure classes distinguish:
- invalid method;
- infrastructure;
- OOM;
- numerical divergence;
- timeout;
- dependency outage;
- safety abort;
- evaluator failure;
- data corruption.

Do not convert infrastructure failure into scientific negative evidence.

## 16. Result bundle

~~~text
ExperimentResultBundle
  result_id
  manifest_id
  protocol_digest
  code_commit
  artifact_ids[]
  failed_run_ids[]
  primary_metrics
  secondary_metrics
  uncertainty
  subgroup_results
  cost
  baseline_parity
  deviations[]
  validity_state
  scientific_state
  scope
  evidence_ids[]
  debt_changes[]
  question_changes[]
  created_at
  reviewed_at?
  signatures[]
~~~

Validity and scientific result are separate.

Example:

~~~text
validity_state = VALID
scientific_state = NULL_RESULT
~~~

versus:

~~~text
validity_state = INVALID_BASELINE
scientific_state = UNINTERPRETABLE
~~~

## 17. Cost accounting

Cost is multidimensional:

~~~text
ComputeCost
  accelerator_seconds
  cpu_seconds
  peak_memory
  storage_byte_seconds
  network_bytes
  model_api_tokens
  evaluator_tokens
  tool_calls
  human_review_minutes
  energy_estimate?
  currency_cost?
~~~

Generated-data and verifier compute are separate line items.

## 18. Benchmark registry

~~~text
BenchmarkIdentity
  benchmark_id
  name
  version
  release_date
  source
  public_private
  task_population
  scorer
  scorer_version
  answer_access_policy
  known_contamination
  saturation_state
  anchor_set?
  retired_at?
~~~

Benchmark version changes invalidate cached comparison assumptions.

## 19. Benchmark custody

Blind data access goes through capability checks.

Events:
- answer viewed;
- answer exported;
- evaluator invoked;
- hidden set queried;
- derived label created.

Research agents cannot hold direct blind-answer capability.

## 20. Evaluator registry

~~~text
EvaluatorIdentity
  evaluator_id
  kind
  artifact
  prompt
  version
  calibration_record
  known_failure_modes[]
  independence_edges[]
  deterministic
~~~

Kinds:
- deterministic checker;
- unit test;
- theorem prover;
- learned judge;
- human panel;
- external service.

Learned evaluator output is evidence, not truth.

## 21. Independence graph

Edges:
- same_lab;
- same_authors;
- same_code;
- same_base_model;
- same_training_data;
- same_benchmark;
- same_evaluator;
- same_provider;
- same_synthetic_teacher;
- direct_derivative.

Graph queries return:
- raw support count;
- connected components;
- strongest independent clusters;
- hidden monoculture warnings.

## 22. Scheduler

Scheduler receives only declared state.

Input:
- protocols ready;
- open debt;
- blocked decisions;
- prerequisites;
- compute class;
- resource availability;
- freshness deadline;
- reviewer capacity;
- risk.

Output:
~~~text
ResearchWorkOrder
  protocol
  manifest_template
  expected_blocker
  compute_class
  priority_explanation
  prerequisites
  abort_rule
~~~

The scheduler never decides scientific truth.

## 23. Priority model

Use a vector, not one opaque score:

~~~text
decision_value
information_gain
blocker_clearance
freshness_urgency
reuse_value
compute_cost
human_cost
risk
dependency_readiness
~~~

If scalar ordering is required for queue mechanics, retain all components and formula version.

## 24. Compute-class enforcement

C0:
- no accelerator reservation.

C1:
- bounded workstation/small accelerator.

C2:
- controlled small-model grid.

C3:
- medium scale confirmation.

C4:
- systems/fleet experiment.

C5:
- frontier-scale expensive run.

C5 requires:
- explicit ADR/question;
- prior cheaper evidence;
- signed decision-value review;
- hard budget;
- kill criteria;
- independent reviewer.

## 25. Source adapters

Adapter boundary:

~~~text
discover(query)
resolve(identifier)
fetch_metadata(identity)
fetch_versions(identity)
fetch_status(identity)
fetch_artifacts(identity)
fetch_corrections(identity)
~~~

Adapters return untrusted normalized records.

They cannot:
- mutate claims;
- retire debt;
- set confidence;
- promote architecture.

## 26. Source ingestion security

Before parsing/execution:
- byte-size cap;
- MIME validation;
- decompression ratio cap;
- archive path safety;
- malware scan;
- secret scan;
- parser sandbox;
- no ambient credentials;
- network egress policy;
- dependency quarantine.

Downloaded repository code is data until explicitly promoted to an execution sandbox.

## 27. Freshness worker

Freshness worker emits only changes.

~~~text
SourceChangeReceipt
  work_id
  old_attestation
  new_observation
  change_type
  observed_at
  affected_claims[]
  requires_review
~~~

Change types:
- new_version;
- accepted;
- rejected;
- withdrawn;
- correction;
- retraction;
- code_release;
- data_release;
- replication;
- counterevidence_candidate.

No automatic conclusion rewrite.

## 28. Invalidation engine

Material changes propagate as review tasks.

Examples:
- evaluator version changed -> results using evaluator marked review_due;
- benchmark contaminated -> dependent claims marked review_due;
- model family changed -> monitorability evidence expired;
- precision/compression changed -> interpretability evidence expired;
- source retracted -> dependent claims recomputed.

Invalidation never erases lineage.

## 29. Research-agent principal

Research agents receive explicit principal identity.

~~~text
ResearchPrincipal
  principal_id
  model_artifact
  provider
  policy_version
  workspace
  capabilities[]
  cost_budget
  experiment_budget
  blind_eval_access = false
~~~

Every tool call is attributed.

## 30. Research-agent capability tiers

Tier R0:
- read public evidence.

Tier R1:
- edit sandbox files;
- run C0/C1 analysis.

Tier R2:
- launch approved C2 manifests.

Tier R3:
- propose C3+ manifests.

Never automatically allowed:
- production mutation;
- secret access beyond explicit task;
- blind promotion answers;
- self-signoff;
- debt retirement;
- ADR acceptance.

## 31. Anti-cheating boundary

Research agent cannot:
- modify scorer after seeing result;
- inspect hidden expected output;
- rewrite protocol silently;
- filter failures without declaration;
- use benchmark answer cache;
- mark own result independent;
- alter baseline to create a win.

Anti-cheat events become durable audit evidence.

## 32. Independent review

Review object:

~~~text
IndependentReview
  review_id
  result_id
  reviewer_principal
  independence_statement
  artifact_verification
  method_review
  baseline_review
  statistics_review
  conclusion
  objections[]
  signed_at
~~~

Possible review states:
- ACCEPT;
- ACCEPT_SCOPED;
- REQUEST_REPRODUCTION;
- INVALID;
- CHALLENGE;
- REJECT_CONCLUSION.

## 33. ADR proposal bridge

Research system can create an ADR proposal only when:
- result valid;
- scope known;
- debt change known;
- contradictions updated;
- dependencies enumerated;
- rollback/migration implications listed.

It cannot accept the ADR.

## 34. Transaction boundaries

One logical mutation per transaction:
- add attestation;
- add evidence;
- add result;
- transition debt;
- record review.

Cross-object state changes use:
- transaction;
- or outbox/event pattern with idempotent consumers.

Never partially retire debt while failing to persist supporting result ID.

## 35. Event model

Suggested event envelope:

~~~text
ResearchEvent
  event_id
  event_type
  aggregate_type
  aggregate_id
  aggregate_version
  occurred_at
  actor
  payload_digest
  previous_event?
~~~

Important events:
- source_attested;
- claim_created;
- contradiction_opened;
- debt_opened;
- protocol_versioned;
- manifest_frozen;
- run_started;
- run_failed;
- result_created;
- review_signed;
- debt_retired;
- claim_expired;
- adr_proposed.

## 36. Concurrency rules

Optimistic concurrency:
- aggregate version compare-and-swap.

Pessimistic/lease control for:
- active run ownership;
- budget reservation;
- artifact finalization.

Conflict behavior:
- fail closed;
- return current version;
- require caller retry from fresh state.

## 37. Idempotency

Commands with external side effects require idempotency keys.

Examples:
- launch run;
- reserve compute;
- upload artifact;
- invoke paid evaluator;
- publish result.

Duplicate request returns original receipt.

## 38. Unknown outcome reconciliation

If launcher times out after submitting a job:
- do not blindly resubmit;
- query provider by idempotency key;
- reconcile resource/job identity;
- only retry when absence is established.

## 39. Storage planes

Relational:
- identities;
- claims;
- debt;
- manifests;
- state machines;
- reviews.

Object/blob:
- logs;
- checkpoints;
- large metrics;
- raw outputs.

Append-only audit:
- event stream;
- signed receipts.

Search index:
- derived, rebuildable;
- never authoritative.

## 40. Database constraints

Examples:
- unique protocol_id + version;
- unique manifest digest;
- one authoritative result bundle per completed manifest version unless explicitly multi-run aggregate;
- debt retirement requires non-empty evidence reference;
- foreign keys for result→manifest→protocol;
- no claim promotion state without review.

## 41. Migration policy

Schema migrations are:
- versioned;
- reversible when practical;
- tested against historical fixtures;
- safe for partial rollout.

Evidence meaning cannot silently change during migration.

If enum semantics change, preserve old value plus translation.

## 42. Query API

Read endpoints:

~~~text
GET /research/claims/{id}
GET /research/debt
GET /research/protocols/{id}
GET /research/runs/{id}
GET /research/results/{id}
GET /research/sources/{work_id}
GET /research/dependencies/{decision}
GET /research/scorecard
~~~

Queries expose lineage and scope, not only current value.

## 43. Command API

Mutating commands:

~~~text
POST /research/sources/attest
POST /research/evidence
POST /research/debt
POST /research/protocols/{id}/versions
POST /research/manifests
POST /research/runs
POST /research/runs/{id}/cancel
POST /research/results
POST /research/reviews
POST /research/adr-proposals
~~~

Each returns a durable receipt.

## 44. CLI

Examples:

~~~text
researchctl source resolve <id>
researchctl source refresh <work>
researchctl debt list --state open
researchctl protocol show RXP013
researchctl manifest freeze RXP013 --config ...
researchctl run launch <manifest>
researchctl run tail <run>
researchctl result inspect <result>
researchctl review sign <result>
researchctl graph blockers <decision>
researchctl scorecard
~~~

CLI is a client of the same command/query API; it does not bypass policy.

## 45. Audit views

Mandatory:
- who changed research state;
- what evidence justified it;
- old/new state;
- artifact digest;
- exact time;
- authorization.

Audit log is tamper-evident and read-only to ordinary research workers.

## 46. Observability

Metrics:
- open debt by age;
- run states;
- failure class;
- invalid experiment rate;
- reproduction rate;
- source freshness;
- reviewer backlog;
- cost by protocol/domain;
- artifact upload failures;
- benchmark access;
- lease conflicts.

Alerts focus on control-plane integrity, not scientific conclusions.

## 47. Safe mode

Research safe mode disables:
- new expensive launches;
- source code execution;
- generated training-data promotion;
- automated ADR proposals.

Still allows:
- read/query;
- incident inspection;
- cancellation;
- artifact verification;
- source-status refresh.

## 48. Backup and restore

Restore proof must preserve:
- identities;
- evidence lineage;
- debt states;
- manifests;
- result→artifact links;
- signatures;
- event ordering.

After restore:
- reconcile external compute jobs;
- verify object-store references;
- invalidate lost ephemeral leases;
- never replay irreversible external side effects blindly.

## 49. Deletion and retention

Research artifacts may contain sensitive or licensed data.

Each artifact declares retention class.

Deletion must:
- tombstone authoritative metadata;
- propagate to derived indexes/caches;
- preserve lawful audit metadata where permitted;
- not leave generated training datasets orphaned.

Weight-level unlearning remains separate from storage deletion.

## 50. Research graph snapshots

For consequential ADRs create immutable snapshot:

~~~text
ResearchDecisionSnapshot
  snapshot_id
  claims[]
  evidence[]
  contradictions[]
  debt[]
  results[]
  source_attestations[]
  generated_at
  digest
~~~

Future reviewers can reconstruct what was known at decision time.

## 51. Deterministic replay target

Control-plane replay should reproduce:
- state transitions;
- debt status;
- claim posture;
- dependency graph;
- scorecard counts.

It need not rerun training to replay metadata state.

## 52. Test strategy

### Unit
- ID parsing;
- state transitions;
- digests;
- enum/schema validation;
- priority components.

### Property
- idempotency;
- no invalid debt transitions;
- stale lease rejection;
- canonical digest stability.

### Integration
- protocol -> manifest -> run -> result -> review;
- source status update -> invalidation;
- benchmark correction -> claim refresh.

### Fault injection
- DB disconnect;
- object store timeout;
- duplicate command;
- lost worker;
- delayed event;
- partial artifact upload;
- clock skew;
- stale lease;
- evaluator outage.

### Adversarial
- malicious source archive;
- scorer manipulation;
- hidden-answer access attempt;
- benchmark poisoning;
- forged result bundle;
- replayed signature;
- agent self-review attempt.

## 53. Minimum viable implementation sequence

M0:
- IDs/enums/errors;
- SQLite development store;
- protocol/result/debt schemas;
- migrations.

M1:
- source identity/status;
- evidence/claim graph;
- query API.

M2:
- manifest freeze;
- run state machine;
- artifact store;
- result bundles.

M3:
- scheduler;
- leases;
- cost accounting;
- cancellation/reconciliation.

M4:
- benchmark/evaluator registry;
- blind custody;
- contamination/saturation metadata.

M5:
- independent review;
- ADR proposal bridge;
- signoff.

M6:
- refresh/invalidation workers;
- scorecard;
- dependency graph.

M7:
- sandboxed research-agent principal;
- anti-cheat;
- C0/C1 autonomous execution.

M8:
- C2+ launch integration only after prior gates.

## 54. Exit criteria

The research control plane is minimally operational when it can demonstrate:

1. one source changing status without losing history;
2. one open debt linked to one protocol;
3. one frozen manifest;
4. one successful and one failed run;
5. one result bundle retaining the failure;
6. one independent review;
7. one debt transition;
8. one claim refresh after new counterevidence;
9. one benchmark-access audit;
10. one idempotent launch reconciliation;
11. one restore drill;
12. no path from research agent to production authority.

## 55. Planning checkpoint

~~~text
checkpoint_id: PLAN-20260922-RESEARCH-CONTROL-PLANE-INTERNALS
created_at: 2026-09-22
package_target: skeleton/research
implementation_milestones: M0..M8
production_authority_granted: false
authoritative_mutations_transactional: true
research_agent_self_signoff_forbidden: true
blind_eval_access_for_research_agent: false
unknown_external_outcomes_reconciled_before_retry: true
~~~
