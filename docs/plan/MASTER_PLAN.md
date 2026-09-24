# Skeleton AI Master Plan

Plan version: **1.6.0**

Architecture lane: `PR #1904 / integration/architecture-map-v1`

Index: [`MASTER_INDEX.md`](MASTER_INDEX.md)

Machine mirror: [`machine/ai_master_plan.json`](../../machine/ai_master_plan.json)

Exotic systems depth: [`EXOTIC_SYSTEMS_DEPTH.md`](EXOTIC_SYSTEMS_DEPTH.md) / [`machine/ai_exotic_systems_catalog.json`](../../machine/ai_exotic_systems_catalog.json)

Existing construction manual: [`docs/AI_APP_CONSTRUCTION_MANUAL.md`](../AI_APP_CONSTRUCTION_MANUAL.md)

Current execution frontier: [`EXECUTION_FRONTIER_2026-09-24.md`](EXECUTION_FRONTIER_2026-09-24.md) / [`machine/ai_execution_frontier_20260924.json`](../../machine/ai_execution_frontier_20260924.json)

## 1. Authority and relationship to existing PR #1904 contracts

This plan is the canonical long-range program specification. It is intentionally layered onto the existing architecture work rather than replacing it.

For **current runtime truth**, the existing fail-closed machine contracts remain authoritative: `machine/architecture.json`, `machine/ai_app_construction.json`, `machine/capability_interfaces.json`, `machine/state_topology.json`, `machine/ai_runtime_schemas.json`, and the associated construction/closure evidence.

For **target architecture, research scope, construction order, and completion criteria**, this master plan and `machine/ai_master_plan.json` are authoritative.

If target and current state differ, the difference is a gap to close. It is not permission to bypass the current contract.

## 2. Mission

Build Skeleton into a coherent AI application and research platform that can:

- preserve durable user/project/conversation continuity;
- assemble governed context from policy, state, memory, retrieval, knowledge and artifacts;
- route across local/remote/specialist models without leaking provider internals into core state;
- reason, plan, search, use tools and verify results under explicit budgets;
- execute bounded long-running work with checkpoints, cancellation, recovery and provenance;
- coordinate specialized agents without authority escalation or mutation collisions;
- produce and validate code, documents, research, models, datasets and other artifacts;
- ingest and evaluate historical and current AI research;
- train/adapt/evaluate models where justified while remaining useful through provider orchestration;
- operate locally, in desktop/web modes, or on distributed compute;
- install, update, repair, roll back, back up and recover predictably;
- measure quality, reliability, latency, cost, safety and evidence rather than claiming them.

## 3. Non-negotiable design laws

1. **Durable state is authority.** Streams, UI caches and model context are projections.
2. **Models propose; deterministic control planes authorize and commit.**
3. **Probabilistic intelligence sits on explicit deterministic contracts.**
4. **Every autonomous operation has identity, objective, scope, authority, budget, deadline, cancellation and terminal state.**
5. **No unbounded cognitive, retry, delegation, search or repair loops.**
6. **Provider SDK/native objects terminate at provider adapters.**
7. **Tools are privileged execution surfaces; descriptions are not permissions.**
8. **Child authority is a subset of parent authority.**
9. **Writes have idempotency or explicit compensation semantics.**
10. **Every significant outcome carries provenance.**
11. **Verification status is separate from model confidence.**
12. **Research candidates do not mutate production directly.**
13. **Production promotion requires executable evidence.**
14. **No top-level architecture expansion after Volume 420 without an ADR explaining why existing domains cannot represent the need.**
15. **SOTA claims require reproducible comparative evidence, not ambition or LOC.**

## 4. Canonical system topology

```text
Human / Operator
      |
      v
Product surfaces
      |
      v
API / Gateway
      |
      v
Operation + Authority + Policy + Budget
      |
      v
Context Compiler
  |       |        |
Memory  Retrieval Knowledge
  \       |       /
      Model Router
          |
      Model Runtime
          |
 Reason / Plan / Search
          |
   Action Proposal
          |
 Policy / Approval
          |
 Tool / Agent Runtime
          |
 World / Repository / Service
          |
 Observation + Durable Receipts
          |
 Verification
          |
 Durable Finalization
          |
 Result / Artifact / Memory
          |
 Evals + Outcomes
          |
 Research / Forge Candidates
          |
 Promotion Gate
```

Security, privacy, provenance, reliability, observability, evaluation and recovery surround every plane.

## 5. Core contract family

The target canonical contract catalogue includes at minimum:

- `OperationEnvelope`
- `ExecutionContext`
- `AIExecutionRequest`
- `AIExecutionResult`
- `Session`, `Conversation`, `Message`, `AgentTurn`
- `ProviderDescriptor`, `ModelDescriptor`, `ModelRequest`, `ModelResult`
- `CompiledContext`
- `MemoryRecord`
- `RetrievalQuery`, `RetrievalResult`
- `Entity`, `Relation`, `Claim`, `EvidenceRecord`
- `Plan`, `PlanStep`
- `AgentDescriptor`, `AgentInstance`
- `ToolDescriptor`, `ToolProposal`, `ToolInvocation`, `ToolResult`
- `Artifact`, `Checkpoint`, `Event`, `FailureRecord`
- `EvaluationRecord`, `BenchmarkRecord`
- `CapabilityDescriptor`, `GapRecord`
- `ResearchPaper`, `Experiment`
- `ReleaseRecord`, `DeploymentRecord`

Every serialized contract receives an ID, owner, version, schema, compatibility rule, migration rule, producers, consumers, tests and documentation.

## 6. State and operation model

Important state machines include operation, conversation, model request, tool invocation, plan step, agent, checkpoint, artifact, evaluation, research, installer, update and release.

A normal AI operation flows through bounded substates equivalent to:

```text
CREATED
-> ADMISSION
-> CONTEXT
-> ROUTING
-> INFERENCE
-> INTERPRET
-> PLAN/PROPOSE
-> AUTHORIZE
-> EXECUTE
-> OBSERVE
-> VERIFY
-> REVISE (bounded)
-> COMMIT
-> RESPOND
-> COMPLETED
```

Any state may transition through waiting, cancellation, recovery or failure where the contract permits.

## 7. Data, memory, retrieval and knowledge

### Data
Use transactional stores for authoritative mutable state, document/object stores for content/artifacts, vector/search/graph stores as governed capability-specific stores, and durable event/audit storage for replay/provenance.

Every persistent class declares owner, classification, source, retention, deletion behavior, encryption requirements, backup policy and licensing restrictions.

### Memory
Separate working, conversation, episodic, semantic, procedural, project, agent, artifact, research, engineering, failure and reflection memory. Long-lived writes pass promotion/privacy/deduplication/contradiction checks. Model text alone never grants permission to persist memory.

### Retrieval
Support lexical, dense, hybrid, graph, metadata, temporal, entity, multimodal, code-symbol and multi-hop retrieval behind common evidence contracts. Retrieval enforces authorization at query time and returns provenance.

### Knowledge
Represent entity/relation/claim/evidence/time/source explicitly. Contradictory claims coexist with scope/time/provenance rather than silently overwriting one another.

## 8. Model engineering and inference

Maintain two tracks:

- **Orchestration track:** immediately useful provider/local model adapters through a provider-neutral runtime.
- **Native model R&D track:** tokenization, architecture experiments, training, post-training, distillation, quantization, verifier/reward models, specialist models and multimodal systems.

Training data flows through acquisition, rights checks, integrity, deduplication, normalization, filtering, classification, PII handling, quality scoring, contamination analysis, sharding, versioning and frozen manifests.

Inference eventually supports streaming, structured output, tools, multimodality, cancellation, failover, continuous batching, prefix/KV caching, quantization, speculative decoding and distributed placement where measurements justify them.

Model lifecycle states remain distinct from capability maturity and include registry, evaluation, staging, canary, active, deprecated and retired.

## 9. Context and cognition

The Context Compiler combines immutable policy, user objective, durable conversation, workspace/project state, authorized memory, retrieval evidence, knowledge, tool descriptors, agent role and model constraints.

Trust classification survives compilation. Retrieved/external/tool/model-generated text cannot promote itself into higher instruction authority.

The cognitive runtime supports bounded strategy selection among direct inference, decomposition, retrieval, search, simulation, critic/verifier paths and multi-agent execution. It records enough structured state for replay, evaluation and debugging without depending on hidden reasoning text.

## 10. Planning and workflows

Plans are dependency DAGs with preconditions, postconditions, capability requirements, budgets, deadlines, acceptance criteria and recovery strategy.

A workflow IR/DSL may compile reusable long-running processes into validated DAGs. Static analysis detects cycles, unreachable steps, missing capabilities, unbounded loops and missing terminal behavior.

Critical-path, scheduling and simulation layers may optimize execution, but cannot violate authority or hard constraints.

## 11. Tools, connectors and side effects

The tool transaction is:

```text
model proposal
-> tool lookup
-> input schema validation
-> data classification
-> identity/scope authorization
-> risk/approval decision
-> budget/resource admission
-> idempotency reservation
-> sandboxed execution
-> output validation
-> postcondition verification
-> durable receipt
-> governed context projection
```

Every side effect is auditable. Compensation/saga patterns handle reversible multi-system operations. Shadow execution must never duplicate external side effects.

## 12. Agents, swarms and autonomy

An agent is identity + role + objective scope + authority + capabilities + memory/planning/verification policy + resource limits.

Multi-agent execution uses leases/fencing, explicit handoff packets, delegation budgets, conflict domains, bounded fan-out and evidence-based disagreement resolution.

Canonical engineering roles include supervisor, researcher, implementer, adversarial reviewer and independent verifier.

Autonomy levels are explicit. Operations may de-escalate on uncertainty/failure; escalation cannot occur silently.

## 13. Research program

The research plane ingests papers, technical reports, standards, datasets, code, replications, negative results, corrections and retractions.

Research objects preserve methods, datasets, claims, results, limitations, citations, implementations and replication status.

Research promotion proceeds through discovery, ingestion, understanding, reproduction, benchmarking, challenge, candidate integration and gated promotion.

Historical techniques are retained by problem solved, mechanism, strengths, weaknesses, failure conditions, modern descendants and reusable primitives.

## 14. Forge, learning and controlled evolution

Forge generates and compares candidate code, policies, prompts, routing strategies, agent configurations, datasets, model adapters and artifacts.

Learning signals may come from outcomes, corrections, tool success, retrieval quality, routing results, benchmark regressions and production telemetry.

Self-improvement is always:
```text
observe weakness
-> hypothesis
-> candidate
-> sandbox
-> evaluate
-> adversarial challenge
-> champion comparison
-> canary
-> promote/reject
```

## 15. Security, privacy and governance

Security boundaries exist at user/application, application/model, model/tool, tool/OS, agent/authority, workspace/workspace, tenant/tenant, research/production, CI/release-signing and installer/update-service edges.

Use least authority, explicit delegation, sandboxing, egress control, secret references, short-lived credentials where available, supply-chain scanning, SBOM/provenance, tenant isolation, data minimization, retention/deletion/export and audit.

Prompt injection defenses rely on trust classification and independent tool authorization rather than trusting model instructions.

## 16. Reliability and distributed systems

Use explicit retries/backoff/jitter, circuit breakers, bulkheads, durable queues, dead letters, idempotent consumers, checkpointing, worker leases/fencing, backpressure and load shedding.

Distributed inference separates routing, placement, worker health, batching, caches and autoscaling. Scheduler inputs may include CPU/GPU/RAM/VRAM, NUMA/interconnect/network/storage topology and data locality.

Research, build/eval farms and background agents must not starve interactive production work.

## 17. Observability, SLOs and economics

One operation should be reconstructable from durable state plus telemetry.

Track request/queue/context/retrieval/model/tool/verification/finalization spans; model and tool usage; latency; error rates; queue depth; capacity; memory/retrieval usefulness; evaluation regressions; provider health; and cost.

Define SLIs/SLOs for critical planes and use error budgets. Track cost by operation, model/provider, tool, user/workspace, agent, benchmark and experiment.

## 18. Evaluation and verification

Evaluation is a pyramid: unit/property/contract tests -> integration -> capability evals -> system/agent evals -> long-horizon scenarios -> production outcomes.

Maintain benchmark hygiene: versions, contamination analysis, configs, seeds where relevant, environment, inference budget and statistical uncertainty.

Verification may be structural, evidence-based, action/postcondition, code execution, mathematical, independent-model, deterministic-rule or human review. High-impact acceptance cannot be overridden by generator retry alone.

## 19. Product, installation and operations

Product surfaces expose honest long-running state: objective, current phase, plan, completed work, blockers, artifacts, evidence, cost, warnings and cancellation.

Desktop installation handles hardware/runtime discovery, verified package installation, configuration, first-run health, repair, update and rollback.

Operations cover backups, restore drills, provider/database/queue/worker failures, incident response, doctor/support bundles, safe repair and deployment planning.

## 20. Repository architecture and machine control

The existing PR #1904 canonical roots remain intact. This plan does not authorize bulk moves. Machine manifests should progressively map requirements/capabilities/contracts to those canonical owners.

Architecture fitness functions should eventually fail CI for undeclared production components, illegal dependencies, capabilities without tests/evidence, tools without policy, critical operations without recovery, provider types crossing core boundaries, and target/current-state drift that is not represented as a gap.

## 21. P0 build program

The near-term build-depth program remains aligned to `machine/ai_build_queue.json` and the functional-AI dependency graph in `machine/ai_app_construction.json`.

Canonical work-package families:

```text
WP-W00 Architecture authority
WP-W01 Contract primitives
WP-W02 Kernel/lifecycle
WP-W03 Durable state
WP-W04 Events
WP-W05 Model runtime
WP-W06 Model routing
WP-W07 Memory
WP-W08 Retrieval
WP-W09 Knowledge/evidence
WP-W10 Context compiler
WP-W11 Cognitive runtime
WP-W12 Planning
WP-W13 Tools
WP-W14 Policy
WP-W15 Agent runtime
WP-W16 Swarm
WP-W17 Verification
WP-W18 Evaluation
WP-W19 Resilience
WP-W20 Security
WP-W21 Observability
WP-W22 API/streaming
WP-W23 Product
WP-W24 Desktop
WP-W25 Installer
WP-W26 Research
WP-W27 Forge
WP-W28 Learning
WP-W29 Distributed runtime
WP-W30 Production hardening
```

## 21.1 W00-W11 edge-case acceptance overlay

The P0 build program is cross-checked against `docs/plan/P0_EDGE_CASE_BUILD_MATRIX.md` and `machine/ai_p0_edge_case_matrix.json`.

The matrix currently maps **173 unique historical/edge/obscure catalogue entries** into W00–W11, including exact repository paths, invariants, test targets and acceptance conditions. Planned tests are explicitly labeled `planned:` and do not count as evidence until materialized and passing.

A W00–W11 package may reach implementation before every mapped edge case is closed, but it may not reach hardened/production status until relevant high-impact cases are either evidence-passing or recorded as explicit accepted risks with ownership.

## 21.2 Full-program edge-case ownership

The edge/historical catalogue is now fully owned across W00–W30 through `machine/ai_full_edge_case_matrix.json` and `docs/plan/FULL_EDGE_CASE_BUILD_MATRIX.md`.

All **240 catalogue entries** have at least one work-package owner. Each entry carries criticality, recommended evidence modes and explicit work-package references. Critical/high concrete failure cases require executable evidence or an explicit accepted-risk record before the owning capability can be promoted to hardened/production.

The current atomic AI build queue also inherits this matrix. Each task exposes counts for the total/critical/high/medium/reference cases inherited from its work-package references, making edge-case pressure visible to scheduling, review and promotion logic.

The full-program matrix also extracts a dedicated risk ledger at `machine/ai_edge_case_priority_queue.json` / `docs/plan/EDGE_CASE_PRIORITY_QUEUE.md`. It currently contains every case classified critical or high, ordered separately from the larger reference catalogue so high-risk obligations cannot disappear inside documentation volume.

## 21.3 Mandatory build accountability and sign-off

Construction accountability is mandatory and machine-enforced through `machine/ai_build_accountability.json`, with the visible checklist in `docs/plan/BUILD_ACCOUNTABILITY_LEDGER.md`.

Every tracked volume, work package, AIQ task, vertical slice, and historical/edge/obscure obligation has a completion checkbox. Checkboxes are derived state and may not be hand-toggled. A checked item requires:

- implementation sign-off;
- independent verification sign-off;
- signer identity and role;
- RFC3339 UTC timestamp ending in `Z`;
- full 40-character git SHA;
- non-empty evidence references;
- explicit attestation statement;
- signature method;
- completion timestamp;
- ledger evidence.

Implementation and verification signers must be different. A same-signer exception requires its own signed, timestamped, commit-bound exception record with rationale and evidence.

Work that has merely started must record a UTC `started` event in the append-only history. Status promotion is therefore auditable from planned → started → implemented → verified → checked/closed.

Unbound/manual attestations are not accepted; signatures must bind to GitHub identity, GPG, SSH signing, Sigstore, or CI OIDC. No retroactive signatures are fabricated. Items that predate the ledger remain unchecked until they receive real evidence and sign-off.

## 21.4 Master build sequence

The canonical middle layer between the 421-volume target and the atomic AIQ queue is `machine/ai_master_build_sequence.json`, documented in `docs/plan/MASTER_BUILD_SEQUENCE.md`.

It groups W00–W30 into eight dependency-aware construction waves without creating a second completion system:

```text
MBW-00 Authority + contracts
  -> MBW-01 Runtime spine + durable state + recovery
       -> MBW-02 Model/memory/retrieval/knowledge/context
       -> MBW-03 Tools/policy/verification/security
            -> MBW-04 Cognition/planning/agents/swarms
                 -> MBW-05 Observability/API/product/desktop
                 -> MBW-06 Evaluation/research/forge/learning
                      -> MBW-07 Installer/distributed runtime/production hardening
```

The sequence is deliberately stricter than a roadmap. Every wave declares entry criteria, concrete deliverables, required evidence modes, exit criteria, stop conditions, allowed overlap, and hard dependencies. All W00–W30 packages have exactly one primary wave owner, every AIQ stage 0–7 is represented, and every critical/high edge obligation resolves to at least one wave through its work-package ownership.

Wave completion is **derived**, never manually asserted. A wave only closes when its completion-bearing work packages, AIQ tasks, vertical slices and high-impact risk obligations satisfy the existing accountability contract: implementation sign-off, independent verification sign-off, UTC timestamp, full git SHA, evidence references and derived checkbox state.

### Promotion stop rules

Promotion must stop when any of these conditions exist:

- target-plan prose conflicts with current fail-closed runtime authority;
- a model can grant itself tool or policy authority;
- a side effect lacks idempotency or compensation semantics;
- retry/replay can duplicate an external effect;
- derived state is being treated as authoritative;
- policy or trust labels can disappear through context compression/truncation;
- a planned test is being cited as passing evidence;
- durable schema migration/rollback/restore behavior is undefined;
- a critical risk is hidden behind aggregate green status;
- production promotion lacks independent verification.

### First construction emphasis

The first depth pass should prioritize MBW-00 and MBW-01 closure quality even when later waves prototype in parallel. This prevents downstream AI behavior from solidifying around ambiguous contracts, weak durable-state ownership or non-recoverable event semantics.

The next major convergence is MBW-02 + MBW-03: intelligence context and privileged action must mature together. Richer reasoning is not a substitute for authorization, and stronger policy is not useful if context compilation can erase or launder trust.

MBW-04 is the point where bounded autonomy becomes legitimate. MBW-05 and MBW-06 can then deepen product/evidence surfaces in parallel. MBW-07 is qualification, not feature accumulation: installer, distributed execution and production hardening must prove that the already-built system survives clean machines, upgrades, rollback, congestion and failure.

## 21.5 Systems-engineering closure overlay

The depth-only systems-engineering contract is `machine/ai_engineering_pass.json`, with the human ledger in `docs/plan/ENGINEERING_PASS.md`. It covers every W00–W30 package without adding architecture breadth or creating a second completion mechanism.

The required closure chain is:

```text
requirement
-> interface
-> authoritative state + invariant
-> authority/trust rule
-> failure model
-> quantitative budget
-> implementation
-> executable test/eval
-> fault/recovery evidence
-> telemetry
-> migration + rollback
-> reproducibility record
-> independent verification
-> signed accountability
```

Fifteen engineering dimensions are machine-enforced across requirement testability, interface ownership, state authority, authority/trust, failure containment, recovery, quantitative NFR budgets, capacity/backpressure, compatibility/migration, observability, executable verification, evaluation, reproducibility, release/rollback, and ownership/change impact.

Numeric targets are bound at implementation depth rather than invented globally. Any applicable latency, throughput, durability, availability, resource, cost or quality claim must declare a threshold, unit, workload, environment, measurement method, owner and waiver policy before promotion. Production evidence must contain measured values against those thresholds.

Cross-boundary schema/API/config/storage/model changes must also declare mixed-version behavior, migration order and rollback/restore semantics. Promotion stops if a queue/fan-out/store can grow without a bound, replay can duplicate an effect, cancellation/restart can violate terminal finality, a migration assumes atomic fleet upgrade, or evidence cannot be reproduced from code/config/data/model/environment identity.

The engineering overlay is a stronger definition of implementation depth. It does not override current runtime authority; it makes `verified`, `hardened` and `production` claims require concrete engineering proof in addition to the existing signed accountability contract.


## 21.6 Adversarial cross-condition closure overlay

The systems-engineering pass closes individual requirement/interface/state/failure/budget/evidence dimensions. The adversarial closure pass closes the remaining interaction loophole: a package may not reach strong maturity by satisfying those dimensions independently while failing under combined lifecycle, authority, resource, restore, semantic-drift, or evidence conditions.

Canonical contracts:

- human: `docs/plan/ADVERSARIAL_CLOSURE_PASS.md`;
- machine: `machine/ai_adversarial_closure.json`;
- validator: `scripts/check_ai_adversarial_closure.py`;
- regression: `skeleton/testing/test_ai_adversarial_closure.py`.

The overlay defines 24 closure axes and 12 permanent compound-fault campaigns covering bootstrap/root trust, quiescence/restart, hard resource exhaustion, degraded dependency behavior, unknown external outcomes, reconciliation/orphans, mixed-version migration/rollback, restore/tombstone/external-effect reconciliation, time/lease semantics, identity/key continuity, silent semantic drift, canonicalization/TOCTOU, hostile parser/resource bombs, evidence integrity, economic denial of service, telemetry failure, cross-tenant isolation, data rebuild/compaction, human break-glass recovery, plan/machine/code drift, recovery dependency cycles, reproducibility/hermeticity, long-horizon aging, and multi-axis fault interaction.

Every `WP-W00` through `WP-W30` must carry the applicable closure-axis references in its build packet and evidence. A missing applicability decision is not implicitly `N/A`.

Strong maturity promotion is cumulative:

```text
ADV-E0 applicability
  -> ADV-E1 single-axis executable evidence
  -> ADV-E2 pairwise interaction evidence
  -> ADV-E3 applicable compound campaigns
  -> ADV-E4 replayable recovery/rollback/restore
  -> ADV-E5 independent digest-bound closure sign-off
```

Consequential side-effect, authority, durable-state, migration, rollback, restore, and trust-root paths may not use single-fault testing as a substitute for applicable compound campaigns.

Unknown external outcome is a first-class recovery state. Restore is not complete until tombstones, revoked authority, leases, derived state, and external effects are reconciled. Fallback may preserve or reduce capability, but may not silently widen privilege, privacy exposure, data residency, irreversibility, or cost.

No signature is fabricated by planning. Verified/hardened/production closure requires real artifact-bound evidence and the existing signed accountability mechanism.


## 21.6 Atomic task engineering propagation

The engineering obligations defined for W00–W30 are now propagated into every atomic AIQ task through `machine/ai_engineering_task_matrix.json`, documented in `docs/plan/ENGINEERING_TASK_MATRIX.md`.

This closes a previously important gap between package-level engineering policy and executable queue work. Each AIQ task inherits the exact union of its referenced work packages' required engineering dimensions, NFR budget classes, evidence modes, principal failure modes, recovery requirements, change-impact triggers and construction-wave ownership.

```text
AIQ task
-> work_package_refs
-> engineering profiles
-> inherited dimensions/budgets/failures/recovery
-> implementation packet
-> executable evidence
-> independent verification
-> signed accountability
```

The inheritance is fail-closed. A shorter task-local acceptance list cannot silently narrow package-level engineering obligations. Any not-applicable disposition must be explicit and reviewable.

Task completion and engineering-strong capability promotion remain separate claims. Existing signed AIQ completion state is preserved, but it cannot by itself justify `verified`, `hardened` or `production` maturity. Those stronger claims require bound quantitative budgets, executable engineering evidence, compatibility/recovery proof, independent verification and the existing signed-accountability contract.

## 22. Vertical-slice acceptance ladder

- **VS-000:** install/boot/persist/event/stream/shutdown/restart/recover.
- **VS-001:** full user AI operation with durable conversation, context, retrieval/memory, routing, cognitive loop, governed tool, verification, commit and streaming.
- **VS-002:** repository engineering agent: inspect -> plan -> lease -> edit -> build -> test -> review -> verify.
- **VS-003:** scientific researcher: acquire -> evidence graph -> reproduce -> experiment -> evaluate.
- **VS-004:** multi-agent engineering with bounded roles and leases.
- **VS-005:** controlled self-improvement with champion/challenger and promotion.
- **VS-006:** distributed workers/inference with failover and recovery.
- **VS-007:** clean-machine desktop install -> AI operation -> artifact -> restart -> update -> rollback.

## 23. SOTA qualification

A capability may be described as a **SOTA candidate** only with reproducible implementation, credible benchmark, appropriate baselines, controlled evaluation, contamination analysis, independent verification, robustness/security checks and cost/latency characterization.

Architecture breadth, code size, model size, number of agents, or internal confidence are not SOTA evidence.

## 24. Definition of done

A production capability is complete only when all applicable elements exist:

- requirement and rationale;
- architecture owner and capability descriptor;
- contract/schema/state model;
- implementation and configuration;
- systems-engineering profile covering applicable engineering dimensions;
- authority/security/privacy assessment;
- explicit failure model, bounded retries/queues/fan-out, and recovery semantics;
- migration/compatibility behavior including mixed-version and rollback/restore behavior;
- quantitative NFR budgets with units, workload, environment and measurement method;
- unit/property/contract/integration tests;
- adversarial/failure/recovery tests;
- performance/capacity characterization against bound thresholds;
- observability sufficient to reconstruct critical transitions and recovery;
- reproducible evaluation and evidence bound to code/config/environment identity;
- deployment, canary and executable rollback;
- operator/developer documentation;
- machine manifest updates;
- architecture validation.

## 24.1 Historical, obscure and edge-case depth

The master plan has a cross-cutting anti-amnesia catalogue at `docs/plan/EDGE_CASES_HISTORICAL.md` with a machine mirror at `machine/ai_edge_case_catalog.json`.

It captures historical mechanisms such as STRIPS, truth-maintenance systems, blackboard architectures, BDI/Contract Net, sparse IR baselines, actor/CSP/Petri-net coordination, WAL/MVCC/Sagas, logical clocks, consensus, capability security and supervision trees. Historical material is retained for the mechanism, original assumptions, discovered failure modes and modern analogue rather than nostalgia.

It also records concrete obscure failure families that frequently evade happy-path designs:

- duplicate keys, null/absent ambiguity, Unicode normalization/confusables, numeric precision and time anomalies;
- duplicate/out-of-order events, split brain, stale leases, ABA, lost acknowledgements, retry/reconnect storms, deadlock/livelock/starvation and partial multi-store updates;
- indirect prompt injection, memory/retrieval poisoning, stale evidence, temporal/scope mismatch, schema/model/version races, false multi-agent consensus, benchmark leakage, reward hacking and goal drift;
- TOCTOU, symlink/hardlink/path/archive escapes, SSRF/DNS rebinding, secret inheritance and platform-specific filesystem/process behavior;
- tombstone resurrection, stale indexes, embedding incompatibility, partial migrations, rollback incompatibility and backup/restore failures;
- GPU resets, VRAM fragmentation, nondeterministic kernels, thermal/NUMA effects, suspend/resume and driver-runtime incompatibility;
- browser refresh/reconnect, double-submit, multi-device concurrency, stale optimistic state and accessibility/locale edge cases.

For every implemented capability, applicable catalogue entries must be considered during acceptance design. High-value cases should be promoted into executable evidence:

```text
edge/history entry
  -> requirement/invariant
  -> regression/property/fuzz/chaos test
  -> observability signal
  -> recovery/runbook
  -> acceptance evidence
```

A successful happy path does not close a P0 gap when mapped high-impact failure cases remain undefined.

## 24.2 Volume maturity promotion contract

Volume status is now a machine-enforced maturity claim rather than a descriptive label.

- **specified** — canonical scope/identity exists; implementation may not.
- **scaffolded** — requirements, capability shape, contracts, risks and gaps are explicit enough to build.
- **implemented** — implementation paths and focused tests exist behind declared contracts.
- **integrated** — the capability participates in the assembled runtime and has integration/evaluation coverage.
- **verified** — independent acceptance evidence exists.
- **hardened** — failure/security/recovery and applicable high-impact edge obligations are closed or explicitly accepted.
- **production** — release, rollback, operations/SLO evidence and signed accountability support the claim.
- **experimental** — bounded research candidate, never production authority by implication.
- **deprecated** — replacement/retirement path is explicit.
- **retired** — removed from active authority while lineage/evidence remain preserved.

The machine policy in `machine/ai_master_plan.json` declares the minimum non-empty traceability fields required for each maturity state. The master-plan validator rejects promotions that skip those fields.

A file existing is not “implemented.” A happy-path test is not “verified.” A benchmark win is not “hardened.” A merged PR is not “production.” Each stronger word must carry stronger machine-checkable evidence.

## 24.3 Volume depth passes

The masterplan is no longer allowed to remain uniformly title-level. Depth passes progressively convert frozen volumes into buildable records without falsely claiming implementation.

The first enforced tranche is **DP-000-040**, documented in `docs/plan/VOLUME_DEPTH_000_040.md`. VOL-000 through VOL-040 each carry non-empty requirements, capabilities, contracts, implementation paths, tests, evaluations, risks, and gaps.

The second enforced tranche is **DP-041-080**, documented in `docs/plan/VOLUME_DEPTH_041_080.md`. It continues the exact same non-empty traceability rule across API Architecture, product/web/desktop and long-running UX, multi-tenancy, install/update/repair/uninstall, repository and import architecture, machine manifests/linting, gap/risk/ADR control, CI/release/deployment/environment/configuration, backup/DR/incident response, performance/capacity/cost/quality, specialized intelligence including Jeeves, artifact/CAS/experimentation/reproducibility, and software/test architecture.

The third enforced tranche is **DP-081-120**, documented in `docs/plan/VOLUME_DEPTH_081_120.md`. It deepens formal methods, benchmark/red-team/human-control disciplines, explainability/accessibility/i18n/compliance, documentation and operations, backlog/priority/build governance, VS-000 through VS-007, functional/autonomous/research/SOTA-candidate acceptance, anti-pattern/build-order/DoD/traceability/capability/debt/fitness controls, project metrics, roadmap/completion semantics, and final assembly qualification.

The fourth enforced tranche is **DP-121-160**, documented in `docs/plan/VOLUME_DEPTH_121_160.md`. It deepens requirements/NFR/capability/behavior/state/interface/schema/compatibility contracts, internal protocols and consistency/transaction/outbox/cache/content-addressing rules, ingestion/document/lineage/data-quality/dataset/synthetic-data systems, training and post-training control/recovery/evaluation, multimodal ingestion/vision/audio/speech/video/retrieval, and the Tool SDK.

The fifth enforced tranche is **DP-161-200**, documented in `docs/plan/VOLUME_DEPTH_161_200.md`. It deepens connectors/plugins/marketplace/sandboxing, policy simulation, threat/security/zero-trust/network/egress/secrets/keys/tenant/privacy/deletion controls, SBOM/MBOM and SLO/error-budget/trace/performance/cost/efficiency disciplines, chaos/recovery/release/canary/feature-flag/rollback architecture, and developer/local/fixture/simulation/fuzz/property/formal-verification infrastructure.

The sixth enforced tranche is **DP-201-240**, documented in `docs/plan/VOLUME_DEPTH_201_240.md`. It deepens agent communication/handoff/performance/economics/delegation/consensus/reviewer/verifier workflows, research teams/literature/citations/reproduction/statistics/evaluation, model/dataset/tool/agent cards and health, provider risk/failover and offline/air-gap/edge/enterprise deployment, identity/admin/audit/operations dashboards, and model operations/rollback.

The seventh enforced tranche is **DP-241-280**, documented in `docs/plan/VOLUME_DEPTH_241_280.md`. It deepens prompt/routing/memory/retrieval policy registries, temporal/uncertainty/hypothesis/causal/search/stopping intelligence, answer/artifact quality and human/reversibility/blast-radius/change budgets, migration/legacy/deprecation/archaeology/consolidation/provenance/ownership controls, documentation/diagram/snapshot/build reproducibility and provenance, and installer/update/bootstrap/crash/support security/recovery.

The eighth enforced tranche is **DP-281-320**, documented in `docs/plan/VOLUME_DEPTH_281_320.md`. It deepens doctor/self-diagnosis/safe-repair/digital-twin/deployment planning, scheduler/fairness/backpressure/load-shedding/queue/retry/breaker/bulkhead/dead-letter/replay primitives, determinism/time/identity/logical ordering, master control/objective/constraint/decision/workflow compilation and migration, task complexity/decomposition/critical-path/scheduling simulation, and autonomy control/levels/escalation/de-escalation.

The ninth enforced tranche is **DP-321-360**, documented in `docs/plan/VOLUME_DEPTH_321_360.md`. It deepens human override/interrupt/goal-drift/specification-gaming/plan-execution alignment, human factors/approval fatigue/trust/intent/project memory/workspaces, resource/artifact/change-impact/change-risk/safe-change/system compiler domains, generated/internal/provider/storage/event/evaluation SDKs, data/index/embedding/freshness lifecycle, and source-trust/claim/knowledge reconciliation/snapshots.

The tenth enforced tranche is **DP-361-400**, documented in `docs/plan/VOLUME_DEPTH_361_400.md`. It deepens memory garbage collection/quality/interference/versioning/reconciliation, cognitive strategy selection and reasoning cost/regression, plan verification/static analysis/simulation, tool composition/dependency/health/discovery/result-trust/effect/compensation/saga semantics, distributed inference and model placement/caching/autoscaling/load testing, hardware/NUMA/GPU/storage/data/network topology, remote execution/worker attestation, and the build farm.

The final tranche is **DP-401-420**, documented in `docs/plan/VOLUME_DEPTH_401_420.md`. It closes evaluation/research compute, quotas/budget/forecasting/cost anomaly controls, license/data-rights/attribution/research-ethics governance, model lifecycle/deprecation/provider migration/shadow/champion-challenger systems, experimental sandbox/research branching/technique retirement/failure knowledge, and the Architecture Scope Freeze at VOL-420.

The fields may contain planned targets; they are planning depth, not evidence. `planned:` paths are not passing tests. `evidence` remains empty unless real artifacts/results exist, and `implementation_status` remains governed by the signed accountability ledger.

Sequential depth is now complete across **VOL-000..VOL-420**. Future work must increase implementation, verification, hardening and production evidence inside the frozen domains; new top-level breadth requires the existing scope-freeze ADR exception.

## 24.4 Exotic systems depth layer

The breadth-frozen plan now includes a dedicated exotic-mechanism reservoir at `docs/plan/EXOTIC_SYSTEMS_DEPTH.md`, with a machine mirror at `machine/ai_exotic_systems_catalog.json`.

The first enforced tranche contains **73 candidates across 13 categories**:

- cognitive architectures: active inference, predictive processing, global-workspace arbitration, leased blackboards and stigmergic coordination;
- optimization/search: MCTS tool planning, CMA-ES, MAP-Elites, novelty search, population-based training, bandit allocation and value-of-information scheduling;
- memory/knowledge: modern Hopfield memory, sparse distributed memory, hyperdimensional/vector-symbolic memory, bitemporal truth, truth-maintenance sets and Datalog slices;
- model/inference: sparse MoE routing, adaptive early exit, speculative decoding variants, recurrent-memory/state-space models, energy-based verifiers and test-time compute controllers;
- formal methods: TLA+/Alloy candidates, SMT-backed plan verification, temporal-logic runtime monitors and proof-carrying action proposals;
- distributed runtime: CRDT research planes, differential dataflow, optimistic simulation, tuple spaces, gossip membership, work stealing and deterministic replay;
- hardware/compute: spiking/neuromorphic research, FPGA kernels, photonic/reversible watchlists and approximate-computing kernels;
- adaptive learning: conformal calibration, reservoir/liquid networks, meta-learning adapters, continual-learning rehearsal and homeostatic control;
- security/resilience: capability-style authority, information-flow labels, rotating sandbox identities, N-version verification, Byzantine-resilient aggregation and honeytoken canaries;
- dataflow/storage: content-addressed artifacts, Merkle snapshots, incremental view maintenance, erasure-coded cold evidence and temporal feature logs;
- multimodal interfaces: event cameras, spatial audio, haptic simulation hooks and cross-modal agreement checks;
- research methodology: negative-results registries, ablation-first promotion, mechanism-transfer lineage and sunset-by-default experiments;
- deployment/product: microreboot lifecycle islands, semantic resumable streams, local-first ambient desktop profiles and dual-slot atomic installers/updaters.

These are **not** implied implementation commitments and do not receive production authority by novelty. The default state is `candidate` in `research_sandbox` (or `watchlist` for horizon technologies). Promotion is fail-closed and must preserve the ordinary architecture:

```text
candidate
  -> named owner + bounded budget
  -> baseline/champion comparison
  -> failure/adversarial evaluation
  -> explicit integration contract
  -> kill-switch + canonical fallback proof
  -> shadow/canary where safe
  -> independent verification
  -> existing maturity + signed-accountability promotion
```

Every exotic item must remain mapped to existing Volume 000–420 domains and complete W00–W30 ownership. An exotic mechanism cannot bypass durable-state authority, policy/authorization, normal evidence requirements, rollback/recovery, compatibility, SLO/cost review, or the signed completion system. If a candidate loses ownership, evidence, reproducibility or an operable fallback, it reverts to watchlist/retired rather than lingering on the critical path.

The machine validator rejects unknown volume/work-package references, missing fallback/kill-switch semantics, insufficient evidence requirements, production-authority defaults, category-depth regressions, and breadth-freeze violations.


## 24.5 Current execution frontier and ledger reconciliation

Sequential planning depth is complete, so the canonical continuation is now the execution frontier documented in `docs/plan/EXECUTION_FRONTIER_2026-09-24.md` with machine contract `machine/ai_execution_frontier_20260924.json`.

The frontier exists to prevent implementation from outrunning accountability. It snapshots the 42-task P0 queue as **1 done / 6 evidence-pending / 1 in-progress / 34 pending**, records landed implementation candidates without auto-promoting them, and defines a dependency-ordered construction sequence `EF-W0` through `EF-W6`.

The first obligation is reconciliation, not new breadth:

```text
landed implementation
  -> exact AIQ identity
  -> exact-head acceptance evidence
  -> implementation lifecycle event/signoff
  -> independent verification lifecycle event/signoff
  -> completion digest
  -> ledger promotion
```

This explicitly covers Stage-0 drift and the larger implementation/accountability gap now visible through Stage 3. Landed candidate evidence includes conversation authority, durable memory plus derived projections, governed tool execution, provider/context convergence and the verification plane. A merged commit may be evidence, but it is not by itself a completion claim.

After reconciliation of the landed Stage-0 through Stage-3 candidates, the next net-new build frontier is bounded cognitive execution -> engine boundary -> stream reconciliation -> full-stack evidence. Lower-stage evidence remains dependency-authoritative and can invalidate downstream promotion.

The frontier validator `scripts/check_ai_execution_frontier.py` cross-checks the snapshot and candidate lifecycle states against `machine/ai_build_accountability.json`. Any subsequent ledger promotion therefore requires this frontier snapshot to be deliberately advanced rather than silently becoming stale.

## 25. Scope freeze and future plan evolution

Volume 420 freezes breadth. New discoveries should be inserted as chapters/subchapters under an existing volume. A new top-level volume requires an ADR showing that the requirement cannot be represented cleanly within the frozen domains.

From this point the preferred unit of progress is **validated implementation depth** rather than additional architectural surface area.
