# Masterplan Adversarial Gap Audit

Status: canonical hostile-design review  
Updated: 2026-09-21  
Scope: Skeleton architecture, Tracks Q–AA, training, inference, memory, tools, agents, data, deployment and recovery

## 0. Audit posture

Assume all of the following can happen at once:

- a tool returns malicious or malformed data;
- a worker retries after its lease expired;
- clocks disagree;
- a cache is stale but syntactically valid;
- a database accepts part of a write and the process dies;
- a model artifact is validly formatted but wrong, poisoned, mismatched, or malicious;
- telemetry is delayed, duplicated, dropped, or lying by omission;
- one replica is slow rather than dead;
- a provider changes behavior without changing an endpoint;
- an evaluation set leaks indirectly;
- a rollback binary reads state written by a newer schema;
- a secret appears in a prompt, log, trace, crash dump, generated artifact, or child process;
- a training shard is duplicated, missing, poisoned, reordered, or silently corrupted;
- an operator acts under pressure with incomplete information;
- an agent delegates to another agent with a broader capability surface;
- a retry repeats an irreversible external side effect;
- a long-context request becomes a denial-of-wallet attack;
- a supposedly independent verifier shares the same model, data, or failure mode;
- an upgrade is faster in a microbenchmark and worse in the complete system;
- a backup exists but cannot actually restore;
- a checkpoint exists but does not reconstruct the same training trajectory;
- the monitoring system fails before the monitored system does.

An architecture claim passes this audit only when the failure is **bounded, observable, recoverable, attributable, and testable**.

Severity:

- **P0** — blocks trustworthy construction or invalidates rollback/security/reproducibility claims.
- **P1** — major correctness, reliability, scale, or operational weakness.
- **P2** — frontier-completeness gap; may land after P0/P1 foundations.

---

# 1. Gap heatmap

| ID | Severity | Gap | Why current plan is insufficient |
| --- | --- | --- | --- |
| G001 | P0 | Tokenizer / representation contract | vocabulary changes are mentioned only as surgery; token identity is not a canonical artifact dependency |
| G002 | P0 | Dataset lineage and deterministic mixture reconstruction | W4 is too thin to prove exactly what trained a checkpoint |
| G003 | P0 | Unified model artifact manifest | weights, tokenizer, architecture, quantization, adapters, runtime ABI and evidence are not bound as one identity |
| G004 | P0 | Durable schema/state migration protocol | binary rollback can fail after forward state mutations |
| G005 | P0 | Evaluation firewall and adaptive-overfitting control | contamination is recorded but blind holdout access and repeated-query exhaustion are not governed |
| G006 | P0 | Authenticated principal / tenancy / delegation chain | capability checks without principal identity are incomplete authority |
| G007 | P0 | Execution sandbox / containment | authorization does not contain a compromised tool or generated program |
| G008 | P0 | Supply-chain trust root | provenance exists, but signing, SBOM, build identity, revocation and load-time verification are incomplete |
| G009 | P0 | Authoritative storage consistency contract | "database adapter" does not define transactions, replication, corruption handling, split brain or restore |
| G010 | P0 | Distributed time, leases, fencing and ordering | idempotency alone cannot stop stale workers or reordered mutations |
| G011 | P0 | Secret lifecycle and secret-taint propagation | secret provider is named, but projection, rotation, logging, prompt and artifact leakage are not governed |
| G012 | P0 | Disaster recovery contract | checkpointing is not a declared RPO/RTO restore system |
| G013 | P0 | Control-plane / data-plane isolation | plan mentions protected capacity but not a hard isolation boundary |
| G014 | P0 | Configuration authority and immutable config snapshots | runtime policy can drift independently from the artifact/evidence being evaluated |
| G015 | P0 | Non-idempotent side-effect compensation | some external actions cannot be retried safely with an idempotency key alone |
| G016 | P0 | Privacy deletion / tombstone propagation | memory deletion is not traced through caches, indexes, snapshots, training candidates and derived artifacts |
| G017 | P0 | Training-data poisoning / backdoor lane | retrieval poisoning is tested; training poisoning and malicious synthetic data are not first-class |
| G018 | P0 | Artifact deserialization / model-load containment | a valid file format can still exhaust memory, exploit loaders, or mismatch runtime assumptions |
| G019 | P0 | Tamper-evident audit log | receipts exist, but evidence can be incomplete or rewritten without a defined append-only integrity mechanism |
| G020 | P0 | Safe-mode / break-glass operating state | no unified read-only/degraded mode exists for damaged authority, storage or dependency trust |
| G021 | P1 | Global resource scheduler | local budgets do not prevent cross-plane starvation or priority inversion |
| G022 | P1 | Backpressure propagation | overload detection is present but upstream/downstream propagation semantics are not |
| G023 | P1 | Observability integrity | no monitor-of-monitors, telemetry-gap detection, cardinality budget or trace-loss policy |
| G024 | P1 | SLO/error-budget authority | QoS metrics exist without a policy for burn rate, protection or release gating |
| G025 | P1 | API/event/tool schema compatibility | typed contracts lack live mixed-version negotiation and deprecation windows |
| G026 | P1 | Structured decoding contract | structured-output behavior is evaluated but not enforced through grammar/schema-constrained decoding and repair |
| G027 | P1 | Uncertainty / abstention / OOD contract | "confidence" and difficulty are present without calibration ownership or abstain semantics |
| G028 | P1 | Cross-tenant cache and memory leakage | tenant isolation is named for KV, but not end-to-end across embeddings, prompts, prefixes, telemetry and artifacts |
| G029 | P1 | Cache coherence and generation invalidation | multiple cache layers can serve mutually inconsistent state |
| G030 | P1 | Event delivery semantics | no canonical outbox/inbox, delivery, dedupe-window or poison-event policy |
| G031 | P1 | Reconciliation after partial success | receipt existence does not define how to resolve "unknown outcome" after timeout/disconnect |
| G032 | P1 | Multi-agent deadlock/livelock/byzantine behavior | bounded retries do not solve circular waits, conflicting ownership, or malicious/buggy peers |
| G033 | P1 | Provenance laundering | summarized/copied/generated content can lose original trust and source ancestry |
| G034 | P1 | Numeric reproducibility envelope | bitwise determinism is not always possible; tolerated numeric drift is not declared per subsystem |
| G035 | P1 | Compiler / model IR contract | AA13 assumes model IR without defining stable shape/dtype/layout/alias semantics |
| G036 | P1 | Kernel correctness oracle | numerical tolerance, reference path, shape fuzzing and hardware-specific fallback are under-specified |
| G037 | P1 | Capacity planning / headroom | scaling reacts to current load without a declared reserve for recovery, bursts, canaries and control plane |
| G038 | P1 | Autoscaling oscillation protection | disaggregated serving/elastic training can thrash placement and state |
| G039 | P1 | Denial-of-wallet / cost attacks | token/tool budgets exist locally but no account/tenant/global economic abuse controls |
| G040 | P1 | Log/trace/prompt data minimization | observability can become a privacy and secret exfiltration surface |
| G041 | P1 | Serialization/parser bombs | files, documents, JSON, archives and model outputs can be intentionally pathological |
| G042 | P1 | Cancellation semantics after commit point | cancellation can race an irreversible side effect |
| G043 | P1 | Dependency/provider semantic drift | API still works but model/tool semantics change |
| G044 | P1 | Release/install ABI compatibility | installer/runtime work is not bound to model/kernel/plugin ABI compatibility |
| G045 | P1 | Backup age / restore compatibility | old backups may be unreadable after schema/runtime evolution |
| G046 | P1 | Garbage collection of provenance/state | immutable evidence can grow without bounded retention, compaction and legal deletion |
| G047 | P1 | Clock-independent TTL/freshness | wall clocks cannot be trusted for leases, cache freshness or ordering alone |
| G048 | P1 | Quorum / split-brain semantics | replicated authorities need one explicit writer/fencing model |
| G049 | P1 | Partial result semantics | tool/model streams can fail after emitting data; consumers need committed/partial/invalid states |
| G050 | P1 | Human approval race / staleness | approval can become stale if arguments/state change after the approval was issued |
| G051 | P1 | Training run provenance after elastic resize | topology migration can change ordering and numerical path without sufficient lineage |
| G052 | P1 | Synthetic-data collapse controls | repeated model-generated training data can narrow diversity and reinforce errors |
| G053 | P1 | Reward/verifier gaming in search | verifier-guided optimization can exploit the metric even when individual verifiers look healthy |
| G054 | P1 | Evaluator drift/versioning | promotion comparisons are invalid if the evaluator changes silently |
| G055 | P1 | Hidden dependency on one hardware vendor | hardware abstraction exists, but kernels/precision/checkpoints may remain non-portable |
| G056 | P1 | Network partition matrix | provider outage exists; asymmetric partitions and half-open connections need explicit campaigns |
| G057 | P1 | Filesystem/object-store semantics | atomic rename, eventual consistency, stale listing and multipart upload behavior vary by backend |
| G058 | P1 | Operator action provenance | manual repair/migration/override must enter the same causation and receipt graph |
| G059 | P1 | Configuration secret separation | signed config cannot accidentally require embedding secret values in signed artifacts |
| G060 | P1 | Bootstrapping trust root | who verifies the verifier, keys, manifests and policy at first boot is not defined |
| G061 | P2 | Multimodal representation contract | image/audio/video/time alignment are evaluation mentions, not architecture contracts |
| G062 | P2 | Unicode/confusable normalization | prompts, identifiers and filenames can differ visually while comparing differently |
| G063 | P2 | Locale/timezone/calendar semantics | scheduling and date-sensitive tools need explicit time standards and DST behavior |
| G064 | P2 | Energy/thermal-aware placement | optional energy metrics do not feed placement or throttling policy |
| G065 | P2 | Offline/degraded provider mode | model/provider neutrality should include loss of all remote providers |
| G066 | P2 | Long-term artifact format retirement | indefinite reproducibility requires migrations for old checkpoint/data formats |
| G067 | P2 | Benchmark saturation/retirement | a benchmark can cease being discriminative without being contaminated |
| G068 | P2 | Accessibility/interaction invariants | agent/UI automation can regress usability even when task success is preserved |
| G069 | P2 | Model/data license policy engine | license metadata exists but compatibility/allowed-use enforcement is not explicit |
| G070 | P2 | Legal-retention vs deletion conflict | immutable evidence and required deletion can conflict without retention classes |

---

# 2. P0 closure specifications

## G001 — Tokenizer and representation substrate

Canonical object:

```text
RepresentationSpec
  representation_id
  tokenizer_family
  tokenizer_version
  vocabulary_digest
  normalization_spec
  byte_fallback_policy
  special_token_map
  BOS/EOS/padding policy
  encode_semantics
  decode_semantics
  compatibility_class
```

Required tests:

- encode/decode round trip;
- byte fallback;
- malformed UTF-8;
- Unicode normalization and confusables;
- multilingual/script coverage;
- special-token escaping;
- structured-output stability;
- context-token accounting;
- cache-key compatibility;
- speculative-decoding tokenizer equality;
- embedding/output-head migration.

**Hard gate:** every model artifact binds one immutable `representation_id`.

## G002 — Data lineage and deterministic training mixture

Canonical objects:

```text
SourceRecord
DatasetManifest
DatasetShardManifest
MixtureManifest
SampleLineage
TransformReceipt
FilterReceipt
DeletionTombstone
SyntheticExampleLineage
HoldoutBoundary
```

Lineage:

```text
source
 -> acquisition version
 -> policy/license/consent metadata
 -> normalize
 -> filter
 -> dedupe
 -> transform
 -> synthetic augmentation
 -> shard
 -> mixture weight
 -> data cursor
 -> checkpoint
```

Required gates:

- deterministic shard/mixture reconstruction;
- source and shard hashes;
- exact sample-count accounting;
- missing/duplicate shard detection;
- near-duplicate cross-split analysis;
- holdout/benchmark exclusion;
- synthetic ancestry depth;
- poisoned-source quarantine;
- deletion propagation;
- mixture-weight provenance;
- curriculum-stage provenance.

**Hard gate:** a training checkpoint without a data-manifest root is incomplete.

## G003 — Unified model artifact identity

```text
ModelArtifactManifest
  artifact_id
  architecture_id
  architecture_config_digest
  representation_id
  weight_shards[]
  weight_format
  dtype
  quantization
  adapter_set[]
  model_code_digest
  runtime_abi
  kernel_capability_requirements
  training_parent
  optimizer_parent
  data_manifest_root
  eval_evidence_root
  provenance_root
  signatures[]
```

Serving loads by manifest, not by a directory guess.

**Hard gate:** incomplete, unsigned/untrusted, mismatched or ABI-incompatible artifact components fail closed.

## G004 — State/schema evolution

Canonical migration sequence:

```text
EXPAND
 -> tolerant read
 -> optional dual read/write
 -> backfill
 -> verify
 -> switch readers
 -> switch writers
 -> CONTRACT
```

Applies to:

- databases;
- events;
- memory records;
- receipts;
- tool envelopes;
- research evidence;
- eval records;
- artifact manifests;
- optimizer states;
- durable caches.

**Hard gate:** a canary that mutates durable state must prove old-version compatibility or use isolated state. Binary rollback without state rollback is not rollback.

## G005 — Evaluation firewall

Four distinct eval classes:

1. development/public;
2. internal regression;
3. blind promotion holdout;
4. production observation.

Controls:

- holdout IDs are excluded from all training-data manifests;
- promotion-holdout query counts are budgeted and audited;
- architecture/hyperparameter search cannot repeatedly optimize against a blind set;
- leaked sets are downgraded;
- evaluator model/data lineage is immutable;
- synthetic eval generation cannot use candidate outputs as answer keys without explicit provenance;
- multiple-comparison/search pressure is recorded.

**Hard gate:** contaminated or adaptively exhausted holdouts cannot justify promotion.

## G006 — Principal identity, tenancy and delegation

```text
Principal
  principal_id
  principal_type
  tenant_id
  authentication_context
  capabilities
  delegation_chain
  session_id
  issued_at
  expiry
  policy_version
```

Invariants:

- every side effect has a principal;
- delegation cannot broaden authority without an explicit new grant;
- tenant identity follows caches, memory, artifacts, receipts, traces and jobs;
- stale credentials are revalidated;
- break-glass identity is separate and audited.

## G007 — Execution sandbox

Minimum boundary:

- explicit filesystem mounts;
- network egress policy;
- process/syscall containment where supported;
- CPU/memory/time/output quotas;
- no ambient host credentials;
- secret projection by minimum scope and lifetime;
- ephemeral workdir;
- child-process policy;
- artifact scanning;
- cleanup verification.

**Hard gate:** high-risk generated code/tool execution never runs in the authoritative control-plane process.

## G008 — Supply-chain trust

Required:

- content digests;
- canonical origin;
- build recipe/toolchain identity;
- dependency lock identity;
- SBOM for runtime/distributable artifacts;
- model/data license metadata;
- signatures where supported;
- malware and secret-scan evidence;
- signature/digest verification at promotion and load;
- revocation/quarantine.

**Hard gate:** download success is not validation.

## G009 — Authoritative storage semantics

Every state store declares:

- consistency model;
- transaction boundary;
- isolation level;
- durability guarantee;
- replication semantics;
- integrity/checksums;
- snapshot behavior;
- compaction;
- capacity-exhaustion behavior;
- corruption detection;
- backup;
- restore;
- partial-write recovery;
- split-brain policy.

No subsystem may assume stronger semantics than its adapter guarantees.

## G010 — Time, leases, fencing, ordering

Required primitives:

- monotonic elapsed-time source for local deadlines;
- wall clock only for human timestamps/expiry where unavoidable;
- lease epoch;
- monotonically increasing fencing token;
- event sequence/correlation/causation IDs;
- dedupe identity and retention window;
- stale-writer rejection.

**Hard gate:** a worker whose lease expired cannot commit even if it wakes up later and still has network access.

## G011 — Secret lifecycle

Secret handling must define:

- source/provider;
- identity allowed to fetch;
- projection target;
- TTL;
- rotation;
- revocation;
- memory/process exposure;
- logging/trace redaction;
- prompt/context prohibition or explicit exception;
- child-process inheritance policy;
- crash-dump policy;
- generated-artifact scanning.

A secret reference may be signed; the secret value must not be embedded in ordinary signed config or provenance bundles.

## G012 — Disaster recovery

Declare per authority:

- RPO;
- RTO;
- backup interval;
- restore dependencies;
- key recovery;
- bootstrap order;
- region/site assumptions;
- restore verification;
- oldest supported backup version.

Required drills:

- loss of primary database;
- loss of artifact store;
- loss of vector/memory index;
- corrupt latest checkpoint;
- stale but intact backup;
- unavailable secret provider;
- simultaneous telemetry outage.

**Hard gate:** backups count only after a restore drill succeeds.

## G013 — Control-plane/data-plane isolation

Control plane owns:

- policy;
- identity;
- promotion;
- configuration;
- recovery;
- kill switches;
- artifact trust.

Data plane owns bounded work.

Required isolation:

- separate capacity reserve;
- separate queues;
- separate failure domains where practical;
- no data-plane saturation can starve revoke/rollback/kill;
- no model/tool output can write control-plane policy directly.

## G014 — Immutable configuration snapshots

Every run/request of consequence binds:

```text
ConfigSnapshot
  config_id
  policy_version
  model_routing_version
  tool_policy_version
  memory_policy_version
  eval_policy_version
  resource_policy_version
  feature_flags
  digest
```

Canary evidence is invalid if the evaluated configuration cannot be reconstructed.

## G015 — Non-idempotent side effects

External actions must declare one of:

- provider-native idempotency;
- transaction/prepare-commit;
- compare-and-set;
- compensating transaction;
- reconciliation query;
- **non-retryable after commit-unknown**.

Receipt state machine:

```text
PLANNED
 -> DISPATCHED
 -> ACKNOWLEDGED | UNKNOWN
 -> COMMITTED | FAILED | RECONCILED
 -> COMPENSATED (optional)
```

Never blindly retry `UNKNOWN` for an irreversible action.

## G016 — Deletion/tombstone propagation

Deletion must reach:

- primary record;
- search indexes;
- vector indexes;
- semantic/episodic memory;
- caches;
- materialized summaries;
- export artifacts;
- candidate training data;
- future checkpoints where policy requires;
- provenance references through a non-content tombstone.

Immutability applies to audit identity, not an excuse to retain prohibited content forever.

## G017 — Training poisoning / backdoor defense

Threats:

- malicious source documents;
- poisoned labels;
- trigger/backdoor examples;
- synthetic-data amplification;
- poisoned preference pairs;
- malicious teacher trajectories;
- training-code tampering;
- gradient/optimizer-state tampering.

Controls:

- source reputation is not enough;
- anomaly and influence sampling;
- canary/trigger suites;
- source-level ablations;
- per-source loss/outlier telemetry;
- isolated high-risk corpora;
- signed data transforms;
- training code/artifact verification.

## G018 — Artifact load containment

Before parsing/loading large or privileged artifacts:

- size/resource caps;
- format allowlist;
- safe parser;
- no arbitrary code execution by default;
- shard-count sanity;
- tensor shape/dtype bounds;
- decompression ratio cap;
- checksum verification;
- metadata sanity;
- model-code trust decision separate from weights.

## G019 — Tamper-evident audit

Meaningful authority changes and side effects need an append-only integrity story:

- ordered event identity;
- actor/principal;
- causation;
- previous-event/hash-chain or equivalent integrity proof;
- artifact/config digests;
- durable retention policy;
- externalized checkpoint/root where appropriate;
- explicit redaction semantics that preserve audit identity.

## G020 — Safe mode and break glass

One system-wide degraded state must be defined.

Safe mode may:

- freeze promotions;
- disable write-capable tools;
- serve only known-good artifacts;
- make memory read-only;
- stop learning/training writes;
- preserve diagnostics;
- permit signed rollback/recovery operations;
- reject nonessential workloads.

Break-glass access:

- short-lived;
- separately authenticated;
- heavily audited;
- unable to erase its own evidence;
- ideally dual-authorized for highest-impact actions.

---

# 3. P1 closure requirements

## G021–G024 — Resources, backpressure and observability

Create a global resource governor above local budgets.

It must enforce:

- tenant/account quotas;
- queue caps;
- priority classes;
- control-plane reserve;
- fairness;
- starvation detection;
- priority-inversion detection;
- cost ceilings;
- memory/CPU/GPU/tool/network budgets;
- admission/load shedding.

Backpressure must be explicit across:

```text
client
 -> API
 -> planner
 -> model
 -> tool
 -> storage
 -> downstream provider
```

Observability itself must report:

- telemetry ingestion gaps;
- dropped spans/logs/metrics;
- timestamp skew;
- cardinality explosion;
- sampling policy;
- trace-link failures;
- exporter failure;
- stale dashboards/alerts.

## G025 — Mixed-version compatibility

All public internal contracts get:

- schema version;
- minimum reader version;
- minimum writer version;
- capability negotiation;
- unknown-field behavior;
- deprecation date/window;
- migration owner;
- compatibility tests.

## G026 — Structured decoding

For tool calls, receipts and machine contracts:

```text
schema
 -> constrained decoder/grammar where supported
 -> parse
 -> semantic validate
 -> policy validate
 -> repair only if repair preserves authority boundary
```

Free-text repair must never be allowed to invent privileged fields.

## G027 — Uncertainty and abstention

Separate:

- model token probability;
- verifier confidence;
- retrieval confidence;
- calibrated task-success probability;
- evidence completeness;
- OOD/novelty score.

Policies can choose:

- answer;
- answer with uncertainty;
- retrieve;
- tool;
- escalate;
- abstain.

Calibration is versioned by task population, not universal.

## G028–G029 — Tenant isolation and cache coherence

Every cache key includes all state that changes meaning:

- tenant/principal scope;
- model artifact;
- representation;
- prompt/system policy version;
- tool/memory policy;
- prefix bytes/digest;
- adapter set;
- quantization/runtime semantics where relevant.

Invalidation must be explicit after:

- model promotion;
- policy change;
- deletion;
- memory promotion/retraction;
- tokenizer change;
- adapter change.

## G030–G031 — Events and reconciliation

Canonical event path should use outbox/inbox or equivalent patterns for durable cross-boundary changes.

Define:

- at-most-once / at-least-once assumptions;
- dedupe window;
- poison event handling;
- replay behavior;
- consumer checkpoint;
- reconciliation job;
- exactly-once claims prohibited unless actually proven.

## G032 — Multi-agent failure protocol

Test:

- circular delegation;
- two agents waiting for each other;
- duplicated ownership;
- conflicting plans;
- stale shared state;
- malicious/buggy peer;
- partial quorum;
- one agent flooding the bus;
- delegated capability amplification.

Require ownership leases, bounded dependency graphs, deadlock detection, cancellation and arbitration.

## G033 — Provenance laundering

A summary, embedding, translation, chunk, generated answer or extracted claim must retain ancestry to the original evidence.

Derived content cannot become `TRUSTED_TOOL_DATA` merely because a trusted model transformed it.

## G034–G036 — Numeric/IR/kernel correctness

Define a stable model/compiler IR with:

- shape;
- dtype;
- layout/stride;
- aliasing/mutation;
- device;
- quantization scale metadata;
- dynamic-dimension rules;
- operator semantics.

Kernel validation:

- high-precision/reference implementation;
- randomized shape fuzzing;
- extreme values;
- NaN/Inf behavior;
- deterministic/debug mode;
- tolerance envelope by dtype;
- cross-hardware differential tests;
- safe fallback.

## G037–G039 — Capacity and cost abuse

Maintain reserved headroom for:

- recovery;
- canaries;
- control plane;
- burst;
- failover.

Autoscaling uses hysteresis/cooldowns and state-migration cost.

Economic abuse controls include:

- max concurrent expensive requests;
- per-principal and tenant budget;
- tool-call spend;
- long-context spend;
- reasoning-search spend;
- anomaly detection;
- hard kill ceiling.

## G040–G041 — Telemetry privacy and parser abuse

Logging defaults to metadata, not raw secrets/prompts/documents.

Parser ingress applies:

- byte caps;
- recursion/depth caps;
- archive member caps;
- decompression ratio caps;
- timeout;
- sandbox where needed;
- content-type verification;
- malformed Unicode handling.

## G042 — Cancellation commit barrier

Every operation declares cancellation phases:

```text
CANCELLABLE
 -> COMMITTING
 -> COMMITTED
```

After commit starts, cancellation means "stop waiting" or "compensate", not "pretend nothing happened."

## G043–G045 — Drift, ABI and old backup compatibility

Provider/model/tool adapters require semantic canaries.

Runtime artifacts declare ABI/capability requirements.

Restore testing includes historical snapshots, not only the current version.

## G046–G050 — Retention, clocks, split brain and approvals

- evidence retention has compaction policy;
- TTLs use monotonic time locally and versioned timestamps durably;
- replicated writers use fencing/quorum rules;
- partial streams are labeled partial until committed;
- human approval binds exact action arguments, config digest and expiry.

## G051–G060 — Training, evaluator, hardware, partitions and trust root

- elastic training changes generate lineage events;
- synthetic-data ancestry and model-family diversity are tracked;
- verifier/search gaming gets adversarial holdouts;
- evaluator versions are immutable in comparisons;
- portability claims require at least one alternate backend or explicit single-vendor status;
- asymmetric network partitions and half-open sockets are tested;
- filesystem/object-store semantics are adapter capabilities, not assumptions;
- manual operator mutations emit receipts;
- secret values stay outside signed ordinary config;
- boot verifies trust root before loading mutable policy/model/plugin state.

---

# 4. P2 frontier completion

## G061 — Multimodal substrate

Create `ModalityArtifact` / `MultimodalPort` contracts for:

- image;
- audio;
- video;
- document/layout;
- time-aligned sensor streams.

Carry codec/version, timestamps, coordinate/time bases, transformations and provenance.

## G062 — Unicode/confusable policy

Normalize only where semantics permit. Preserve raw bytes for evidence. Detect confusable identifiers in security-sensitive paths.

## G063 — Time semantics

Durable timestamps use timezone-aware UTC internally plus original timezone when relevant. Scheduling declares DST/ambiguous/nonexistent-local-time behavior.

## G064 — Energy/thermal placement

When observable, feed power/thermal throttling into scheduler evidence instead of treating throughput changes as random noise.

## G065 — Offline mode

Define minimum useful operation when all remote model/provider APIs are unavailable.

## G066 — Long-term format retirement

Every durable artifact format needs read/migrate tooling across declared support windows.

## G067 — Benchmark retirement

Retire or reduce weight when a benchmark is saturated, unstable, non-discriminative or no longer representative.

## G068 — Interaction/accessibility

Computer-use/UI agents must include semantic accessibility regressions where interfaces expose them.

## G069 — License policy

License metadata needs executable compatibility rules for training, redistribution, model artifacts and commercial/runtime use.

## G070 — Retention conflict

Define precedence and handling when legal/audit retention obligations conflict with deletion/privacy policy; preserve non-content audit identities when content itself must be removed.

---


## 4.1 Second hostile pass — residual attack surfaces

The first pass found architectural families. The second pass attacks race windows, boundary parsing, key infrastructure, cache identity, distributed checkpoint consistency and feedback loops.

| ID | Severity | Residual gap |
| --- | --- | --- |
| G071 | P1 | canonical serialization for signed/hashed objects can drift across language/runtime versions |
| G072 | P1 | TOCTOU between authorization/approval and actual execution |
| G073 | P1 | approval replay against changed arguments, state, principal or policy |
| G074 | P1 | SSRF and DNS rebinding through URL-capable tools/retrievers |
| G075 | P1 | redirect chains can escape an originally allowed origin/network policy |
| G076 | P1 | filesystem path traversal, symlink races and mount-boundary escape |
| G077 | P1 | archive extraction path traversal / zip-slip / archive bombs |
| G078 | P1 | package/plugin dependency confusion and namespace takeover |
| G079 | P1 | generated code can install dependencies with arbitrary install-time scripts |
| G080 | P1 | JIT/kernel/compiled-code cache poisoning or stale binary reuse |
| G081 | P1 | cross-tenant accelerator-memory residue and buffer reuse |
| G082 | P1 | KMS/secret-provider outage during boot, rotation or recovery |
| G083 | P1 | partial key rotation leaves mixed writers/readers and unverifiable artifacts |
| G084 | P0 | root signing/trust key compromise lacks explicit revoke, re-root and re-sign recovery |
| G085 | P1 | distributed checkpoint shards can be individually valid but collectively inconsistent |
| G086 | P1 | snapshot without quiescence/barrier can capture impossible cross-store state |
| G087 | P1 | index rebuild can expose a mixture of old/new generations |
| G088 | P1 | vector embeddings remain after embedding-model/version change |
| G089 | P1 | retrieval index and query encoder can silently disagree on version/normalization |
| G090 | P1 | low-grade memory poisoning accumulates gradually below per-write thresholds |
| G091 | P1 | compaction/GC can accidentally resurrect or discard deletion tombstones |
| G092 | P1 | randomness/seed ownership is not explicit across experiments and production sampling |
| G093 | P1 | elastic resize can duplicate or reuse distributed RNG streams |
| G094 | P1 | data-loader cursor recovery can skip or duplicate training samples |
| G095 | P1 | collectives can hang/partially progress without a consistent recovery boundary |
| G096 | P1 | silent memory/network/storage corruption needs end-to-end checks, not only file hashes |
| G097 | P1 | counters/epochs/sequence IDs can overflow, wrap or be truncated |
| G098 | P1 | unit confusion between bytes/tokens/seconds/ms/currency can defeat resource gates |
| G099 | P1 | feature flags can form invalid combinations not tested individually |
| G100 | P1 | rollout/feature/config skew across replicas can create non-reproducible behavior |
| G101 | P1 | canary traffic may not represent tail users/tasks/hardware/failure conditions |
| G102 | P1 | automated rollback/re-promote can flap between versions without hysteresis |
| G103 | P1 | supposedly independent providers/regions can share correlated dependencies |
| G104 | P1 | DNS/CDN/cache poisoning can change fetched artifacts without changing logical URL |
| G105 | P1 | certificate expiry/rotation can brick bootstrap or recovery paths |
| G106 | P1 | KMS credential bootstrap can become circular during disaster recovery |
| G107 | P1 | audit-log signing-key rotation can break historical verification |
| G108 | P1 | valid old receipts can be replayed as if they authorize a new action |
| G109 | P1 | delayed/replayed events can arrive after policy or lease expiry |
| G110 | P1 | idempotency keys need namespace/scope/TTL rules to prevent collisions and cross-action suppression |
| G111 | P1 | generated IDs can collide or cross namespaces/tenants |
| G112 | P1 | digest/signature algorithms need versioning and cryptographic agility |
| G113 | P1 | semantically identical objects can hash differently without canonical serialization |
| G114 | P1 | consumers can treat an incomplete streamed result as committed data |
| G115 | P1 | speculative output may be externally consumed before later rejection/correction |
| G116 | P1 | prompt/prefix caches can leak across policy/system-prompt versions |
| G117 | P1 | context compression can drop authority/trust labels while keeping imperative text |
| G118 | P1 | summaries can hallucinate provenance or collapse contradictory sources |
| G119 | P1 | retrieval scores from different encoders/indexes are not directly comparable |
| G120 | P1 | learned data-quality filters can drift and silently reshape the training population |
| G121 | P1 | teacher/student synthetic-data loops can create circular evidence and error amplification |
| G122 | P1 | benchmark answers can leak through repository files, tools, search or retrieval at eval time |
| G123 | P1 | test/eval fixtures can later enter training corpora through repository ingestion |
| G124 | P1 | generated evals can self-confirm the model family that generated them |
| G125 | P1 | production behavior→feedback→training loops can amplify popularity rather than correctness |
| G126 | P1 | malicious or low-quality user corrections can poison memory/training promotion |
| G127 | P1 | agent-to-agent messages need authenticated sender identity and anti-impersonation |
| G128 | P1 | workflow checkpoints can replay privileged steps after capability/policy revocation |
| G129 | P1 | stale operator UI state and double-submit can issue obsolete or duplicate commands |
| G130 | P1 | temporary files, local caches and crash residue can retain secrets or sensitive artifacts |

### Second-pass closure rules

- G084 is an additional P0: root-key compromise must have a tested revocation and trust-root replacement path.
- Authorization/approval decisions bind the exact action digest and are revalidated at commit time.
- Fetchers resolve/validate every redirect and final network target; DNS rebinding cannot bypass egress policy.
- File extraction and path writes use canonicalized sandbox-relative paths and reject symlink/mount escapes.
- Checkpoints use one manifest/commit marker so a mixed shard generation never appears complete.
- Index/cache generations switch atomically by generation identifier.
- Embedding/index identity is part of cache/retrieval keys.
- RNG/data cursors are checkpointed as first-class distributed state.
- Signed/hashed structures use canonical serialization and algorithm/version identifiers.
- Speculative/partial output is never labeled committed before acceptance.
- Authority/trust labels survive compression, summarization, translation and agent relays.
- Promotion canaries include tail populations and use hysteresis to avoid rollback flapping.
- Human/operator actions use fresh state and duplicate-submit protection.

**Open P0 rule:** any applicable open P0 blocks a production-readiness claim, regardless of benchmark or capability performance.


## 4.2 Third hostile pass — systemic and lifecycle failures

This pass attacks the architecture between subsystems: policy precedence, bootstrap/recovery dependency cycles, deployment transitions, cryptographic/service identity, region constraints, and long-lived workflow behavior.

| ID | Severity | Systemic/lifecycle gap |
| --- | --- | --- |
| G131 | P0 | invariant/policy conflicts have no single precedence and conflict-resolution contract |
| G132 | P1 | policy merge from system/developer/operator/tenant layers can be ambiguous |
| G133 | P1 | configuration dependencies can form cycles or impossible combinations |
| G134 | P1 | boot dependencies can deadlock before diagnostics/control plane are available |
| G135 | P0 | recovery path can depend on the same failed storage/network/identity service it is meant to recover |
| G136 | P0 | safe mode/break-glass can become unusable when normal auth/KMS/control plane is unavailable |
| G137 | P1 | break-glass credentials can expire, be lost, or remain untested until disaster |
| G138 | P1 | dual-control requirements can deadlock urgent recovery with no bounded escalation path |
| G139 | P1 | alert storms can hide the causal signal and exhaust operator attention |
| G140 | P1 | incident/runbook procedures can drift from current architecture and permissions |
| G141 | P1 | staging/test can differ materially from production hardware, scale, network and policy |
| G142 | P1 | fault-injection harness itself can be wrong and produce false confidence |
| G143 | P1 | chaos tests need blast-radius boundaries and automatic abort conditions |
| G144 | P1 | mocks/test doubles can provide stronger semantics than real dependencies |
| G145 | P1 | production task distribution can drift away from eval populations |
| G146 | P1 | canary cohort selection can systematically exclude the hardest/tail cases |
| G147 | P1 | shadow execution cannot validate real side effects unless transactional simulators mirror them faithfully |
| G148 | P1 | load tests can saturate data plane without testing protected control-plane reserve |
| G149 | P1 | downstream rate-limit semantics/backoff headers may differ by provider/version |
| G150 | P1 | external provider quota exhaustion can cause correlated fallback cascades |
| G151 | P1 | billing/credit/account limits can be a hidden single point of service failure |
| G152 | P1 | data-residency/region policy is not bound into placement, logs, backups and tools |
| G153 | P1 | failover to another region can violate residency or policy constraints |
| G154 | P1 | backup/restore destinations can cross prohibited boundaries |
| G155 | P1 | encryption-at-rest/in-transit requirements are not explicit per data class |
| G156 | P1 | encryption key scope/tenant/artifact binding is not explicit |
| G157 | P1 | cryptographic randomness/nonce generation is not separated from model RNG |
| G158 | P1 | entropy or secure-random initialization can fail during bootstrap/recovery |
| G159 | P1 | internal service identity/mTLS or equivalent authentication is not a canonical boundary |
| G160 | P1 | certificate rotation/pinning/CA migration can strand old or isolated nodes |
| G161 | P0 | internal service impersonation can bypass capability assumptions if service identity is not cryptographically bound |
| G162 | P1 | inbound webhook/event authenticity and replay protection are not universal |
| G163 | P1 | inbound event signatures can verify while payload canonicalization differs |
| G164 | P1 | outbound callbacks/webhooks can become SSRF/data-exfiltration channels |
| G165 | P1 | prompt/template/system instruction versions are not always bound into evidence/cache identity |
| G166 | P1 | system/developer instruction text can leak through outputs, traces, error messages or tool arguments |
| G167 | P1 | hidden policy/context exfiltration can be induced through model/tool interactions |
| G168 | P1 | sustained probing can extract model/system behavior or sensitive memorized content |
| G169 | P1 | abuse/jailbreak rate controls are not integrated with global resource/economic governors |
| G170 | P1 | public API nested/recursive payloads can bypass simple byte limits |
| G171 | P1 | graph/memory traversal can explode through cycles or adversarial fanout |
| G172 | P1 | retrieval fanout/reranking depth can create denial-of-wallet behavior |
| G173 | P1 | graph/retrieval index can be poisoned through entity/edge creation rather than document content |
| G174 | P1 | adversarial embeddings can create collisions/nearest-neighbor hijacking |
| G175 | P1 | similarity thresholds can drift across embedding model generations |
| G176 | P1 | document/content hashing can differ by normalization/container representation |
| G177 | P1 | aggressive dedupe can delete semantically distinct but similar examples |
| G178 | P1 | weak dedupe can leave benchmark/train leakage and frequency distortion |
| G179 | P1 | source license/consent can be revoked after dataset/checkpoint creation |
| G180 | P1 | model/data lineage needs policy for artifacts trained on later-revoked sources |
| G181 | P1 | adapter merge can destroy separability and complicate rollback/provenance |
| G182 | P1 | quantization/dequantization can be non-reversible and invalidate byte-level rollback assumptions |
| G183 | P1 | multiple adapters can interact nonlinearly despite isolated evaluation |
| G184 | P1 | optimizer state can become invalid after architecture surgery or parameter remapping |
| G185 | P1 | tokenizer extension can break draft/speculative model compatibility |
| G186 | P1 | model/provider router can enter feedback loops based on its own latency/failure observations |
| G187 | P1 | routing optimized for cost/latency can systematically select lower-quality behavior for some populations |
| G188 | P1 | fallback models may not preserve safety, tool, schema, context or capability contracts |
| G189 | P1 | provider fallback mid-conversation/workflow can change semantics without explicit state transition |
| G190 | P1 | one workflow can accidentally mix model/tool/schema versions without a version envelope |
| G191 | P1 | long-running workflows can cross deployments and resume under incompatible code/policy |
| G192 | P1 | workflow resume can use stale approvals/capabilities after revocation |
| G193 | P0 | disaster restore/replay can repeat external side effects unless external-effect offsets/receipts are reconciled |
| G194 | P1 | restored queues/jobs can duplicate work already completed outside the restored state |
| G195 | P1 | VM/container snapshot restore can move wall clock backward |
| G196 | P1 | monotonic-clock assumptions do not survive process/host restart without durable epochs |
| G197 | P1 | restored leases/fencing tokens can regress unless epochs survive restore |
| G198 | P1 | DNS/service-discovery caches can keep traffic on failed/retired endpoints after failover |
| G199 | P1 | eventual-consistent object stores can expose promotion metadata before all referenced shards are readable |
| G200 | P1 | atomic activation mechanisms differ across Windows/POSIX/object stores and require adapter-specific guarantees |

### Third-pass closure rules

- Policy/invariant precedence must be explicit and deterministic. Safety/security/authority invariants cannot be overridden by lower-precedence config.
- Recovery dependencies must be modeled as a graph and tested for cycles. At least one minimal recovery path must remain usable with major dependencies unavailable.
- Break-glass is a separately testable system, not documentation.
- Production parity must be stated per dimension; unknown parity is recorded as uncertainty.
- Chaos tooling has its own correctness tests and blast-radius controls.
- Region/residency policy is part of placement, logging, backup, tool and failover decisions.
- Internal service identity is authenticated and bound into principal/capability decisions.
- Long-lived workflows carry a version envelope and revalidate policy/approvals on resume or deployment crossing.
- Restore/replay reconciles external-effect receipts before re-dispatching work.
- Activation/checkpoint protocols declare backend-specific atomicity guarantees rather than assuming POSIX semantics everywhere.

# 5. Adversarial fault-campaign matrix

Do not test failures one at a time only. The dangerous bugs are interactions.

## Axis A — state

- clean;
- stale;
- partially migrated;
- corrupt;
- missing;
- duplicated;
- conflicting;
- read-only;
- near capacity.

## Axis B — network

- normal;
- latency spike;
- packet loss;
- asymmetric partition;
- DNS failure;
- half-open connection;
- duplicated response;
- reordered delivery;
- provider timeout after remote commit.

## Axis C — worker

- healthy;
- slow;
- paused;
- clock-skewed;
- lease-expired;
- restarted;
- duplicated;
- compromised;
- OOM-killed.

## Axis D — artifact/input

- valid;
- stale;
- mismatched version;
- malicious;
- oversized;
- decompression bomb;
- poisoned data;
- prompt-injected;
- signed but revoked;
- valid digest but wrong policy scope.

## Axis E — authority

- valid principal;
- expired session;
- revoked capability;
- stale approval;
- delegated identity;
- wrong tenant;
- break-glass;
- policy changed mid-flight.

## Axis F — resource

- normal;
- CPU saturation;
- GPU saturation;
- HBM near OOM;
- host RAM pressure;
- disk full;
- object store throttled;
- network saturated;
- cost budget exhausted.

## Axis G — observability

- healthy;
- logs dropped;
- metrics delayed;
- traces sampled away;
- clock skew;
- alerting down;
- cardinality explosion;
- misleading green aggregate hiding failed minority.

Minimum campaign strategy:

1. every P0 path: all single-axis faults;
2. every P0 side effect: pairwise combinations across state/network/authority;
3. promotion/rollback: at least pairwise state + artifact + observability;
4. distributed training/serving: pairwise network + worker + resource;
5. quarterly chaos campaign: selected three-axis combinations from prior incidents and highest-risk paths.

---

# 6. Promotion invariants discovered by the hostile audit

The following are now non-negotiable:

1. No model without immutable representation/tokenizer identity.
2. No training checkpoint without data-manifest lineage root.
3. No serving model without a unified artifact manifest.
4. No rollback claim without state/schema compatibility evidence.
5. No promotion score from a contaminated or exhausted holdout.
6. No side effect without authenticated principal identity.
7. No high-risk tool/code execution without containment.
8. No privileged artifact load without integrity/trust verification.
9. No authoritative store without declared consistency and restore semantics.
10. No distributed mutation without stale-writer protection.
11. No secrets in ordinary prompts/logs/config artifacts by default.
12. No backup claim without a restore drill.
13. No workload saturation may starve control-plane revoke/rollback.
14. No consequential run without an immutable config snapshot.
15. No blind retry after an unknown irreversible commit outcome.
16. No deletion claim without derived-state propagation.
17. No training-data trust based on source reputation alone.
18. No unsafe deserialization path for untrusted artifacts.
19. No authoritative mutation without tamper-evident audit identity.
20. No architecture is considered recoverable without a tested safe mode.

---

# 7. Completion criterion

The masterplan is **not adversarially closed** until all P0 findings have:

- a canonical contract;
- an owner;
- a stable plan ID;
- a machine-readable invariant;
- implementation dependency placement;
- unit/property/integration tests;
- fault-injection cases;
- observability;
- recovery/rollback semantics;
- evidence/signoff.

P1 items must be resolved or explicitly accepted with bounded scope before a subsystem claims production-grade status.

P2 items are required before claiming broad frontier completeness.

This audit intentionally remains open-ended. Every incident, near miss, benchmark leak, restore failure, security finding, failed research reproduction or production regression must be able to create a new gap ID without rewriting the audit format.


## 8. Audit checkpoint

PLAN-20260921-HOSTILE-GAP-AUDIT  
scope=G001..G200 + Track AB  
open_P0_blocks_production_readiness=true  
fault_model=single-axis + pairwise + selected-three-axis  
signoff_required_for_closure=true
