# Skeleton AI Master Plan

Plan version: **1.0.0**

Architecture lane: `PR #1904 / integration/architecture-map-v1`

Index: [`MASTER_INDEX.md`](MASTER_INDEX.md)

Machine mirror: [`machine/ai_master_plan.json`](../../machine/ai_master_plan.json)

Existing construction manual: [`docs/AI_APP_CONSTRUCTION_MANUAL.md`](../AI_APP_CONSTRUCTION_MANUAL.md)

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
- authority/security/privacy assessment;
- migration/compatibility behavior;
- unit/property/contract/integration tests;
- adversarial/failure/recovery tests;
- performance characterization;
- observability;
- evaluation and evidence;
- deployment and rollback;
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

## 25. Scope freeze and future plan evolution

Volume 420 freezes breadth. New discoveries should be inserted as chapters/subchapters under an existing volume. A new top-level volume requires an ADR showing that the requirement cannot be represented cleanly within the frozen domains.

From this point the preferred unit of progress is **validated implementation depth** rather than additional architectural surface area.
