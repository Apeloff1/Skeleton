# Volume Depth Pass 000–040

Architecture lane: `PR #1904 / integration/architecture-map-v1`

Machine authority: [`machine/ai_master_plan.json`](../../machine/ai_master_plan.json)

Depth pass: **DP-000-040 — Foundational architecture-to-streaming depth**

This pass converts VOL-000 through VOL-040 from title-only scope markers into buildable plan records. It does **not** claim implementation. Evidence remains separate and signed implementation status remains governed by `machine/ai_build_accountability.json`.

Each record now carries requirements, capabilities, contracts, implementation paths, tests, evaluations, risks, and explicit remaining gaps.

| Volume | Domain | Primary build intent | Key acceptance pressure |
| --- | --- | --- | --- |
| VOL-000 | Plan Constitution | Define authoritative precedence among runtime truth, construction authority, target plan and evidence. | human/machine plan divergence; status inflation without evidence |
| VOL-001 | Scientific & Historical Foundation | Preserve scientific claims with source, method, result, limitation and correction/retraction lineage. | cargo-culting historically famous techniques; source selection bias |
| VOL-002 | System Architecture | Maintain one canonical architecture graph for roots, ownership zones, runtime DAGs and interfaces. | documentation/runtime split brain; transitional roots becoming accidental owners |
| VOL-003 | Canonical Contract System | Give every serialized contract stable identity, owner, version, compatibility rule and migration semantics. | schema drift; privileged defaults from unknown values |
| VOL-004 | Kernel & Execution Foundation | Bootstrap services in deterministic dependency order with explicit readiness and shutdown semantics. | orphan tasks; readiness before dependencies are usable |
| VOL-005 | Data & Persistence | Declare authoritative, derived, cache and ephemeral state classes with one canonical owner each. | split-brain ownership; partial multi-store writes |
| VOL-006 | Model Development Program | Version training data with rights, integrity, deduplication, contamination and PII metadata. | data rights violations; benchmark contamination |
| VOL-007 | Inference Engine | Expose provider-neutral inference with streaming, cancellation, structured output and bounded retries. | duplicate provider effects during retry; KV/prefix cache semantic corruption |
| VOL-008 | Model Routing | Route by capability, policy, privacy/data boundary, reliability, latency and cost constraints. | fallback changes privacy boundary; cost optimizer degrades quality silently |
| VOL-009 | Context Engineering | Compile immutable policy, user objective, durable state, authorized memory/retrieval, tools and model constraints into typed context. | policy trimmed from long context; instruction laundering |
| VOL-010 | Memory System | Separate working, conversation, episodic, semantic, procedural, project and artifact memory classes. | memory poisoning; tombstone resurrection |
| VOL-011 | Retrieval System | Support lexical, dense, hybrid, metadata, temporal, graph, code-symbol and multi-hop retrieval behind common evidence contracts. | stale index; tenant filter applied after ranking |
| VOL-012 | Knowledge System | Represent entity, relation, claim, evidence, scope, time and source separately. | false reconciliation; scope/time mismatch |
| VOL-013 | Cognitive Core | Select bounded cognitive strategies based on task, risk, budget and available evidence. | unbounded reasoning loops; self-confidence treated as verification |
| VOL-014 | Planning Engine | Represent plans as dependency DAGs with preconditions, postconditions, capabilities, budgets and deadlines. | invalid plans reaching execution; goal drift |
| VOL-015 | Tool & Action System | Treat every tool as a privileged execution surface with independent authorization. | tool description prompt injection; shell/path/network injection |
| VOL-016 | Agent Runtime | Define agent identity, role, objective scope, authority, capability set, memory policy and resource limits. | authority creep; orphan agents |
| VOL-017 | Multi-Agent Orchestration | Coordinate multiple agents with explicit handoff packets, leases/fencing, conflict domains and bounded fan-out. | false consensus; deadlock/livelock |
| VOL-018 | Long-Horizon Autonomy | Support long-running operations with durable checkpoints, resumable plans, deadline/budget enforcement and human override. | zombie work; budget leakage |
| VOL-019 | World Models & Simulation | Keep simulation/world-model state clearly separated from real-world authority and side effects. | simulation treated as real evidence; model bias compounds through rollouts |
| VOL-020 | Multimodal Intelligence | Use typed modality contracts for images, documents, audio, speech and video with provenance and classification. | embedded prompt injection; metadata privacy leakage |
| VOL-021 | Code Intelligence | Build repository intelligence from files, symbols, imports, ownership, tests and change history. | stale index; false dependency confidence |
| VOL-022 | Autonomous Repository Engineering | Use inspect→plan→lease→edit→build→test→review→verify as the canonical repository mutation flow. | destructive edits; test gaming |
| VOL-023 | Forge | Generate code/policy/prompt/config/artifact candidates only inside bounded experiment scopes. | candidate escapes sandbox; metric gaming |
| VOL-024 | Learning & Evolution | Collect learning signals with source, scope, confidence and outcome provenance. | self-reinforcing bad feedback; silent behavior drift |
| VOL-025 | Safety Architecture | Maintain explicit hazard/risk taxonomy and safe default behavior for high-impact operations. | overblocking legitimate tasks; underblocking dangerous actions |
| VOL-026 | Cybersecurity | Enforce least privilege, secret isolation, sandboxing, egress control and supply-chain integrity across model/tool/CI/runtime boundaries. | TOCTOU; SSRF/DNS rebinding |
| VOL-027 | Privacy & Data Protection | Classify data at ingestion and preserve classification through derived artifacts. | derived data survives deletion; backup retains sensitive data |
| VOL-028 | Governance & Authority | Represent identities, roles, grants, approvals and delegation as explicit versioned authority objects. | stale grants; approval fatigue |
| VOL-029 | Reliability | Use bounded retry/backoff/jitter, circuit breakers, bulkheads, queues, DLQ and load shedding as explicit policies. | retry storms; thundering herd |
| VOL-030 | Distributed Systems | Model partitions, ordering, leases/fencing, clocks, idempotency and consistency choices explicitly. | split brain; clock/order confusion |
| VOL-031 | Compute & Hardware | Inventory CPU/GPU/RAM/VRAM/storage/network/NUMA/interconnect resources with freshness. | VRAM fragmentation; stale capacity |
| VOL-032 | High-Performance Native Core | Use native acceleration only behind stable capability/ABI boundaries with safe fallback. | undefined behavior; ABI drift |
| VOL-033 | Java / JVM Plane | Use JVM components only where they provide measured interoperability/performance/operational benefit. | classpath drift; GC pauses |
| VOL-034 | Observability | Correlate logs, metrics, traces, model/tool usage and durable receipts by operation identity. | secret leakage in telemetry; missing spans hide failure |
| VOL-035 | Evaluation Program | Version every benchmark/eval with dataset, config, environment, model, inference budget and statistical method. | benchmark cherry-picking; contamination |
| VOL-036 | Adversarial Evaluation | Maintain adversarial cases mapped to threat/edge obligations and capability owners. | evaluator leakage; attack overfitting |
| VOL-037 | Verification Plane | Represent verification separately from generator confidence and acceptance policy. | self-confidence treated as proof; correlated verifier failure |
| VOL-038 | Provenance | Track end-to-end lineage from source/user input through context/model/tool/agent/artifact/output. | canonicalization mismatch; missing lineage edge |
| VOL-039 | Event Architecture | Use versioned event envelopes with stable identity, causation/correlation and ordering metadata. | duplicate/out-of-order events; consumer side effect before inbox marker |
| VOL-040 | Streaming | Define resumable streaming with stable event IDs, sequence semantics, cursors and terminal finality. | cursor compaction gap; duplicate provisional content |


## Depth law

A depth pass is planning depth, not implementation evidence. The required fields above make the volume actionable enough to hand to builders and reviewers. Promotion to `implemented`, `integrated`, `verified`, `hardened`, or `production` still requires the stricter maturity policy and signed accountability.

## Cross-volume dependency spine

```text
Plan constitution / scientific lineage / system architecture
        ↓
Canonical contracts
        ↓
Kernel + durable state + events
        ↓
Model inference/routing
        ↓
Context + memory + retrieval + knowledge
        ↓
Cognition + planning
        ↓
Tools + policy + agents + long-horizon autonomy
        ↓
Safety + security + privacy + governance
        ↓
Reliability + distributed/compute/native runtimes
        ↓
Observability + evaluation + verification + provenance
        ↓
Events + streaming
```

The point of this ordering is not to block all parallel work. It identifies semantic dependencies that must be stable before downstream maturity can be claimed.

## Remaining work after DP-000-040

- deepen VOL-041 onward using the same non-empty traceability standard;
- materialize planned tests/evals into executable evidence;
- resolve implementation paths marked `planned:` into owned repository components;
- bind per-volume requirements to exact work packages/AIQ tasks where the mapping is not already explicit;
- advance maturity only through the signed accountability and evidence gates.
