# Frontier-96 Post-Enterprise AI Capability Ladder

Status: **ACTIVE DESIGN AUTHORITY / NOT IMPLEMENTATION COMPLETE**

Parent masterplan: [MASTER_PLAN.md](MASTER_PLAN.md)

Machine mirror: [machine/frontier_96_ai_ladder.json](../../machine/frontier_96_ai_ladder.json)

Validator: [scripts/check_frontier_96_ladder.py](../../scripts/check_frontier_96_ladder.py)

## Why 96

The number 96 is used intentionally as a **systems capability ladder** above Skeleton's existing enterprise-superiority grade. It does **not** claim that the current ChatGPT product or current OpenAI frontier models expose a fixed 96-transformer-layer architecture.

Historically, the largest GPT-3 configuration published by Brown et al. (2020) used 96 transformer layers. Skeleton reuses the number as an engineering discipline: 96 independently specifiable, testable and signable system capabilities spanning authority, context, memory, retrieval, reasoning, planning, tools, agents, multimodality, learning, model systems, verification and frontier operations.

This overlay does not create `VOL-421+`. It deepens the frozen `VOL-000..420` architecture and its `W00..W30` construction ownership.

## Ladder position

```text
specified
  -> implemented
  -> hardened
  -> enterprise_qualified
  -> superior
  -> FRONTIER-96 ELIGIBLE
       -> F96-001
       -> ...
       -> F96-096
       -> frontier_96_qualified
```

A layer may not enter Frontier-96 qualification unless its mapped prerequisite capabilities are already at the relevant enterprise **superior** grade with current exact-head evidence.

## Frontier-96 laws

1. Enterprise superiority is the floor, not the finish line.
2. The ladder is an overlay, not a new top-level volume family.
3. No layer is complete because documentation exists.
4. No model, agent, evaluator or generator may self-promote its own layer.
5. Every layer requires implementation evidence and independent verification evidence bound to exact code/config/policy/data identities.
6. Security, privacy, authority, tenant isolation, acknowledged durable-state integrity, rollback and required human control are non-compensable.
7. Hidden chain-of-thought is never an implementation contract or verification dependency.
8. External/retrieved/generated content never gains instruction authority by appearing in context.
9. Every autonomous loop is bounded by budget, deadline, cancellation and terminal state.
10. Self-improvement produces candidates; production mutation remains separately authorized.
11. The final `F96-096` claim is invalid if any lower layer has stale evidence.
12. A frontier claim expires on material source, policy, scorer, model, dataset or acceptance-policy change until reverified.

## Strata

| Stratum | Layers | Purpose |
| --- | ---: | --- |
| F96-S01 — Authority & Context Sovereignty | F96-001..F96-008 | Make instruction authority, identity, policy, trust and context assembly explicit before higher cognition can act. |
| F96-S02 — Memory & Knowledge Continuity | F96-009..F96-016 | Turn short-lived model context into governed, temporal, privacy-aware continuity without poisoning or silent contradiction. |
| F96-S03 — Retrieval & Evidence Intelligence | F96-017..F96-024 | Build evidence-first retrieval that can search heterogeneous stores, preserve provenance and distinguish support from plausibility. |
| F96-S04 — Reasoning & Metacognition | F96-025..F96-032 | Add bounded strategy selection, structured reasoning, uncertainty and verifier loops without depending on hidden chain-of-thought. |
| F96-S05 — Planning, Search & Long-Horizon Control | F96-033..F96-040 | Convert goals into bounded executable plans with search, simulation, scheduling, checkpointing and repair. |
| F96-S06 — Tools, Actions & Transactional Agency | F96-041..F96-048 | Make external action privileged, typed, sandboxed, idempotent, reversible where possible, and independently verifiable. |
| F96-S07 — Agents, Delegation & Collective Intelligence | F96-049..F96-056 | Coordinate specialists with strict authority inheritance, leases, handoffs, disagreement resolution and bounded fan-out. |
| F96-S08 — Multimodal & World Intelligence | F96-057..F96-064 | Unify documents, images, speech, audio, video, spatial scenes and computer environments under evidence-preserving contracts. |
| F96-S09 — Learning, Adaptation & Outcome Optimization | F96-065..F96-072 | Learn from outcomes through governed feedback loops while keeping production promotion separate from candidate generation. |
| F96-S10 — Model Systems, Training & Compute Fabric | F96-073..F96-080 | Operate provider, local and native models through a hardware-aware runtime with reproducible lifecycle and rollback. |
| F96-S11 — Verification, Safety, Security & Governance | F96-081..F96-088 | Make correctness, security, privacy, provenance and human authority non-compensable gates rather than soft quality dimensions. |
| F96-S12 — Scientific Autonomy & Frontier Operations | F96-089..F96-096 | Close the loop with observability, chaos recovery, research, adversarial mirror testing, controlled self-improvement and signed finality. |

## The 96-layer ladder

### F96-S01 — Authority & Context Sovereignty

Make instruction authority, identity, policy, trust and context assembly explicit before higher cognition can act.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-001 | **Instruction Authority Lattice** | Compile system, developer, user, workspace, retrieved and generated instructions into a typed precedence lattice with non-escalation rules. | Property tests prove lower-trust content cannot acquire higher instruction authority; replay shows the same authority decision from durable inputs. | `W00`, `W01`, `W10`, `W14`, `W20` |
| F96-002 | **Intent & Objective Normalization** | Convert natural-language requests into explicit objectives, constraints, acceptance criteria, forbidden actions and ambiguity records. | Golden and adversarial suites show stable intent extraction, explicit unresolved ambiguity, and no silent broadening of user authority. | `W01`, `W10`, `W11`, `W14` |
| F96-003 | **Policy Compilation & Decision IR** | Compile human-readable policy into a deterministic decision representation usable by tools, agents, retrieval and release gates. | Equivalent-policy tests, deny-by-default unknowns, versioned policy receipts and deterministic replay all pass. | `W01`, `W14`, `W20` |
| F96-004 | **Identity / Session / Workspace Binding** | Bind every operation to user, tenant, workspace, project, session and delegated principal identities before context or tools are resolved. | Cross-tenant and stale-session tests prove zero unauthorized scope bleed; identity lineage is reconstructable from receipts. | `W03`, `W10`, `W14`, `W20` |
| F96-005 | **Trust-Segmented Context Assembly** | Preserve trust class, source, freshness, scope and authority metadata through every context compilation step. | Injection corpus proves untrusted text cannot be promoted; compiler snapshots preserve source and trust labels end-to-end. | `W07`, `W08`, `W09`, `W10`, `W20` |
| F96-006 | **Context Budget Optimizer** | Allocate context budget by policy, utility, freshness, evidence value, cost and model constraints instead of naive truncation. | Budget sweeps beat fixed truncation on quality/cost while never trimming non-droppable policy or required evidence. | `W06`, `W10`, `W18`, `W21` |
| F96-007 | **Loss-Bounded Semantic Compression** | Compress long context into typed summaries with preserved constraints, citations, uncertainty and recoverable source links. | Round-trip and entailment checks show mandatory constraints survive; dropped claims remain recoverable from source references. | `W10`, `W17`, `W18` |
| F96-008 | **Context Replay & Provenance** | Persist a replayable context manifest tying every model-visible token span or structured element to source identity and policy decision. | Independent replay reproduces the compiled context or emits a precise nondeterminism record; provenance gaps fail closed. | `W03`, `W10`, `W17`, `W21` |

### F96-S02 — Memory & Knowledge Continuity

Turn short-lived model context into governed, temporal, privacy-aware continuity without poisoning or silent contradiction.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-009 | **Working Memory Controller** | Maintain bounded task-local state with explicit lifetime, salience, eviction, checkpoint and reset semantics. | Stress tests show bounded growth, deterministic eviction policy and correct reset/recovery across retries and resumes. | `W03`, `W07`, `W19` |
| F96-010 | **Episodic Memory** | Store event-like experiences with time, scope, actor, evidence and outcome rather than undifferentiated chat text. | Temporal retrieval and deletion tests preserve episode identity, ordering, retention and tenant boundaries. | `W03`, `W07`, `W17` |
| F96-011 | **Semantic Memory** | Promote durable facts and abstractions only through source, confidence, contradiction and scope checks. | Contradiction suites keep competing claims distinct; source deletion/retention propagates into derived representations. | `W07`, `W09`, `W20` |
| F96-012 | **Procedural Memory** | Represent reusable procedures as versioned, permission-aware skills with preconditions, postconditions and rollback guidance. | Procedure replay is deterministic where expected; stale or unauthorized procedures are rejected before action. | `W07`, `W13`, `W14` |
| F96-013 | **Project / World-State Memory** | Maintain durable project and environment state separately from conversation summaries or model beliefs. | Restart and concurrent-writer tests preserve authoritative world state and expose conflicts instead of last-write-wins guessing. | `W03`, `W07`, `W19` |
| F96-014 | **Temporal Truth & Contradiction Graph** | Track claim validity windows, supersession, disagreement and evidence lineage without destructive overwrite. | Time-travel queries reproduce historical truth state; contradictory evidence coexists until an explicit reconciliation decision. | `W09`, `W17`, `W18` |
| F96-015 | **Memory Privacy, Retention & Deletion** | Apply classification, consent, retention, export, tombstone and derived-index deletion policies to every memory class. | Delete/export drills prove no tombstone resurrection and no stale embeddings/indexes retain prohibited content. | `W07`, `W20`, `W30` |
| F96-016 | **Memory Quality & Self-Healing** | Continuously score usefulness, staleness, duplication, poisoning risk and unresolved conflicts, producing repair candidates rather than silent mutation. | Poisoning and stale-memory benchmarks trigger quarantine/repair proposals; production changes remain separately authorized. | `W07`, `W18`, `W27`, `W28` |

### F96-S03 — Retrieval & Evidence Intelligence

Build evidence-first retrieval that can search heterogeneous stores, preserve provenance and distinguish support from plausibility.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-017 | **Lexical Retrieval Plane** | Provide sparse retrieval with field-aware scoring, filters, deterministic baselines and explainable term evidence. | Regression corpus preserves ranking invariants; authorization filtering occurs before candidate exposure. | `W08`, `W18` |
| F96-018 | **Dense Retrieval Plane** | Provide embedding retrieval with versioned model/index identities, similarity semantics and compatibility guards. | Embedding-version mismatch fails explicitly; recall/latency benchmarks bind model, index and corpus versions. | `W08`, `W18`, `W29` |
| F96-019 | **Hybrid Fusion & Reranking** | Fuse sparse, dense and metadata signals through calibrated, auditable ranking stages. | Offline paired evaluation beats declared baselines without violating scope filters; reranker receipts expose contributing signals. | `W08`, `W18` |
| F96-020 | **Graph & Multi-Hop Retrieval** | Traverse entity/relation/claim graphs with bounded hop budgets and evidence-preserving path construction. | Synthetic and real graph tasks prove bounded expansion, cycle handling and path-level provenance. | `W08`, `W09`, `W18` |
| F96-021 | **Temporal & Freshness-Aware Retrieval** | Rank evidence using event time, valid time, freshness policy and source update semantics. | Temporal queries return the correct historical/current slice and mark stale/unknown freshness rather than inventing recency. | `W08`, `W09`, `W18` |
| F96-022 | **Code, Symbol & Multimodal Retrieval** | Unify code symbols, documents, image regions, audio segments and other modality-specific chunks behind common evidence contracts. | Cross-modal retrieval evals preserve exact source anchors and modality metadata; code symbol moves are version-aware. | `W08`, `W18`, `W26` |
| F96-023 | **Source Quality & Provenance Scoring** | Separate relevance from source trust, provenance completeness, licensing, freshness and known reliability history. | Evaluator demonstrates that a highly relevant low-trust source cannot silently outrank mandatory provenance or policy constraints. | `W08`, `W09`, `W17`, `W20` |
| F96-024 | **Evidence Synthesis & Citation Entailment** | Build answers from evidence units with claim-to-source mapping, contradiction handling and citation entailment checks. | Citation verifier demonstrates each material claim is supported, contradicted or explicitly uncertain; unsupported synthesis fails qualification. | `W09`, `W17`, `W18` |

### F96-S04 — Reasoning & Metacognition

Add bounded strategy selection, structured reasoning, uncertainty and verifier loops without depending on hidden chain-of-thought.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-025 | **Reasoning Strategy Router** | Select direct, retrieval, decomposition, simulation, tool, verifier or multi-agent strategies under budget and risk constraints. | Strategy traces show deterministic admissibility and measured utility; expensive paths are not invoked when cheaper qualified paths suffice. | `W11`, `W18`, `W21` |
| F96-026 | **Task Decomposition Engine** | Split complex objectives into bounded subproblems with explicit interfaces, dependencies and acceptance criteria. | Decomposition tests detect missing dependencies, duplicated work and unbounded recursion before execution. | `W11`, `W12`, `W17` |
| F96-027 | **Causal Reasoning Layer** | Represent candidate causes, interventions and confounders distinctly from correlation or narrative explanation. | Counterexample suites detect common causal fallacies; causal claims carry assumptions and evidence lineage. | `W11`, `W18`, `W26` |
| F96-028 | **Counterfactual Reasoning Layer** | Evaluate alternate states under explicit changed assumptions while preserving the baseline world state. | Counterfactual runs are isolated, reproducible and labeled hypothetical; no simulated side effect can mutate production. | `W11`, `W12`, `W19` |
| F96-029 | **Abductive & Analogical Reasoning** | Generate competing explanations and analogies, then score structural fit and disconfirming evidence. | Benchmarks reward correct mapping and penalize surface similarity; alternative hypotheses remain visible until resolved. | `W11`, `W18` |
| F96-030 | **Constraint & Formal Reasoning** | Use SAT/SMT/type/property or domain solvers when problems admit formal structure, with model reasoning as proposal rather than proof. | Formal claims include machine-checkable witness or explicit solver failure; model confidence cannot substitute for proof. | `W11`, `W17`, `W18` |
| F96-031 | **Critic / Verifier Deliberation** | Run bounded generator-critic-verifier cycles with role separation and non-self-promotion rules. | Adversarial tests prove the generator cannot mark its own output verified; retry counts and termination reasons are durable. | `W11`, `W17`, `W18` |
| F96-032 | **Uncertainty, Calibration & Stopping** | Track epistemic/aleatoric uncertainty proxies, evidence gaps, calibration and expected value of further computation. | Calibration curves, abstention tests and bounded stopping policies outperform fixed retry loops under cost/error targets. | `W11`, `W18`, `W21` |

### F96-S05 — Planning, Search & Long-Horizon Control

Convert goals into bounded executable plans with search, simulation, scheduling, checkpointing and repair.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-033 | **Goal Compiler** | Translate objectives into typed goals, constraints, success metrics, forbidden states and terminal conditions. | Goal mutation tests prove downstream agents cannot silently relax hard constraints or redefine success. | `W12`, `W14`, `W17` |
| F96-034 | **Dependency-DAG Planner** | Construct validated plan DAGs with preconditions, postconditions, capability requirements and explicit terminal states. | Static analysis rejects cycles, unreachable nodes, missing capabilities and plans without terminal behavior. | `W12`, `W17` |
| F96-035 | **Hierarchical Planning** | Support goal -> phase -> task -> step refinement while preserving ancestor constraints and budgets. | Refinement proofs show child plans remain subsets of parent scope and budgets; cancellation propagates downward. | `W12`, `W15`, `W17` |
| F96-036 | **Bounded Search Controller** | Use beam, best-first, tree or Monte Carlo search only under explicit branching, depth, time and token budgets. | Worst-case tests demonstrate hard bounds and stable termination; search state is checkpointable and inspectable. | `W11`, `W12`, `W19` |
| F96-037 | **Simulation & World-Model Sandbox** | Evaluate plans against isolated deterministic/stochastic simulators before privileged execution. | Simulation cannot mutate authoritative state; model mismatch is measured and surfaced rather than hidden. | `W12`, `W19`, `W26` |
| F96-038 | **Resource-Aware Scheduler** | Schedule plan nodes using dependencies, deadlines, cost, hardware, rate limits, locality and priority classes. | Load tests prove interactive priority, backpressure and fairness under saturation; starvation is detected and bounded. | `W12`, `W19`, `W21`, `W29` |
| F96-039 | **Plan Repair & Replanning** | Repair invalidated plans from observed state while preserving completed work, constraints and evidence. | Failure injection demonstrates minimal recomputation, no duplicate side effects and explicit supersession of stale plan nodes. | `W12`, `W17`, `W19` |
| F96-040 | **Long-Horizon Checkpoint / Resume** | Persist sufficient execution state to safely resume multi-hour/day operations across process or machine restarts. | Crash/restart drills resume exactly once, preserve budgets/authority, and never replay committed side effects without idempotency proof. | `W03`, `W12`, `W19`, `W30` |

### F96-S06 — Tools, Actions & Transactional Agency

Make external action privileged, typed, sandboxed, idempotent, reversible where possible, and independently verifiable.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-041 | **Capability & Tool Registry** | Expose tools as versioned typed capabilities with schemas, risk class, side effects, owners and policy bindings. | Registry validation rejects ambiguous names, incompatible schemas and undocumented side effects. | `W01`, `W13`, `W14` |
| F96-042 | **Authorization & Approval Engine** | Decide tool eligibility from principal, scope, data classification, risk, budget and required human approval. | Privilege-escalation tests fail closed; approvals bind exact proposed action and expire on material mutation. | `W13`, `W14`, `W20` |
| F96-043 | **Sandbox & Egress Boundary** | Run untrusted or high-risk code/tools with filesystem, process, network, secret and resource boundaries. | Escape, SSRF, path traversal, secret inheritance and resource-exhaustion suites remain contained. | `W13`, `W20`, `W30` |
| F96-044 | **Idempotent Side-Effect Ledger** | Reserve and record external side effects with idempotency keys, dedupe semantics and durable receipts. | Retry storms cannot duplicate irreversible actions; uncertain commit states enter reconciliation instead of blind retry. | `W03`, `W13`, `W19` |
| F96-045 | **Transactional / Saga Orchestration** | Coordinate multi-system actions using prepare/commit where possible and compensation/saga semantics otherwise. | Partial-failure drills converge to a declared terminal state with all committed/compensated steps evidenced. | `W13`, `W19`, `W30` |
| F96-046 | **Connector Reliability Mesh** | Standardize rate limits, pagination, retries, leases, webhooks, eventual consistency and provider-specific failure translation. | Provider fault matrices show bounded retries, backoff, pagination completeness and no error-envelope leakage. | `W13`, `W19`, `W21` |
| F96-047 | **Computer-Use & UI Action Control** | Treat GUI/browser/desktop actions as privileged perception-action loops with screen-state identity and stale-state checks. | Stale UI, double-click, focus theft and layout-shift tests prevent unintended actions; destructive actions require verified target state. | `W13`, `W14`, `W17` |
| F96-048 | **Postcondition Verification & Action Receipts** | Verify the world after each material tool action and persist before/after evidence, not merely tool-return success. | Fault injection proves false-success responses are detected; receipts bind invocation, observed postcondition and final authority decision. | `W13`, `W17`, `W21` |

### F96-S07 — Agents, Delegation & Collective Intelligence

Coordinate specialists with strict authority inheritance, leases, handoffs, disagreement resolution and bounded fan-out.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-049 | **Agent Identity & Role Isolation** | Give each agent an explicit identity, role, objective scope, capabilities, memory policy and resource budget. | Cross-role tests prove agents cannot inherit undeclared tools, memory or credentials. | `W15`, `W20` |
| F96-050 | **Delegation Contract** | Delegate only a subset of parent authority with explicit objective, budget, deadline, return contract and revocation semantics. | Delegation property tests reject authority amplification and preserve revocation across queued/running children. | `W15`, `W14`, `W17` |
| F96-051 | **Lease, Fencing & Ownership** | Protect mutable work through leases/fencing tokens so stale or duplicated workers cannot both commit. | Split-brain and clock-skew tests prove stale owners are fenced before mutation. | `W15`, `W16`, `W19` |
| F96-052 | **Handoff Packet & Continuity** | Transfer tasks with canonical objective, state, evidence, open questions, constraints and accepted risks. | Handoff round-trips preserve all hard constraints and unresolved blockers; implicit conversational state is insufficient. | `W15`, `W16`, `W17` |
| F96-053 | **Bounded Parallelism & Fan-Out** | Parallelize independent work under declared concurrency, collision domains and merge policies. | Stress tests enforce fan-out ceilings, detect overlapping mutation domains and preserve cancellation/backpressure. | `W16`, `W19`, `W21` |
| F96-054 | **Disagreement & Arbitration** | Resolve conflicting agent outputs through evidence, role-aware arbitration and independent verification rather than majority confidence. | Synthetic collusion and shared-error tests prevent false consensus from being promoted. | `W16`, `W17`, `W18` |
| F96-055 | **Hierarchical Command Plane** | Preserve Supervisor -> Secretary -> Worker authority with non-executing coordination boundaries and auditable task issuance. | Boundary tests prove Supervisor/Secretary cannot bypass execution policy and Workers cannot rewrite parent authority. | `W15`, `W16`, `W14` |
| F96-056 | **Swarm Recovery & Quorum Safety** | Recover multi-agent operations from worker loss, duplicated messages, stale state and partial quorum without corrupting authority. | Chaos tests demonstrate deterministic reassignment, no double commit and explicit degraded-mode semantics. | `W16`, `W19`, `W30` |

### F96-S08 — Multimodal & World Intelligence

Unify documents, images, speech, audio, video, spatial scenes and computer environments under evidence-preserving contracts.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-057 | **Document & Image Vision** | Parse layout, regions, tables, diagrams and images while preserving pixel/page anchors and OCR uncertainty. | Document evals bind extracted claims to exact regions/pages and distinguish uncertain text from verified text. | `W05`, `W08`, `W18`, `W26` |
| F96-058 | **Speech & Audio Intelligence** | Handle transcription, diarization, acoustic events and speech generation with timing, speaker and confidence metadata. | Noise, overlap and speaker-switch tests preserve timestamps and uncertainty; generated speech is provenance-labeled. | `W05`, `W18`, `W26` |
| F96-059 | **Video & Temporal Perception** | Model events across frames with temporal anchors, scene changes, tracks and long-video summarization. | Temporal QA and event localization benchmarks preserve frame/time evidence and avoid single-frame hallucinated continuity. | `W05`, `W08`, `W18`, `W26` |
| F96-060 | **Cross-Modal Fusion** | Fuse text, image, audio, video and structured state while retaining modality-specific uncertainty and source identity. | Conflict tests keep contradictory modalities explicit; fusion cannot erase lower-confidence provenance. | `W09`, `W10`, `W18` |
| F96-061 | **Spatial / Scene Representation** | Represent objects, relations, geometry, visibility, state and uncertainty in a deterministic scene/world graph. | Round-trip fixtures preserve entity identity and topology; impossible transforms or ambiguous ownership fail explicitly. | `W03`, `W09`, `W18` |
| F96-062 | **Interactive World / Computer Model** | Maintain a perception-action world state for browser, desktop or simulated environments with stale-state detection. | Refresh, resize, focus and external-change tests force re-observation before action when state identity changes. | `W13`, `W17`, `W19` |
| F96-063 | **Cross-Modal Memory & Retrieval** | Store and retrieve multimodal episodes/objects through shared entity and evidence identifiers. | Cross-modal queries return modality anchors and respect deletion/retention across every derived index. | `W07`, `W08`, `W09` |
| F96-064 | **Sensor Uncertainty & Provenance** | Carry confidence, calibration, capture conditions, transformation lineage and missing-data semantics through multimodal pipelines. | Corruption and missing-sensor tests never convert unknown into zero/false; transformed media remains lineage-linked. | `W09`, `W17`, `W18` |

### F96-S09 — Learning, Adaptation & Outcome Optimization

Learn from outcomes through governed feedback loops while keeping production promotion separate from candidate generation.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-065 | **Outcome Telemetry** | Capture task outcome, user correction, tool success, verifier results, latency, cost and recovery signals as governed learning events. | Event schemas distinguish observation from label; missing/biased telemetry is quantified before optimization. | `W18`, `W21`, `W28` |
| F96-066 | **Feedback Normalization** | Convert explicit/implicit feedback into typed signals with source, scope, confidence, consent and anti-gaming controls. | Conflicting and malicious feedback suites prevent direct production mutation and preserve minority/high-risk signals. | `W18`, `W20`, `W28` |
| F96-067 | **Preference Modeling** | Learn task/user/workspace preferences under privacy boundaries and with reversible, inspectable state. | Preference drift tests separate stable preference from one-off instruction; deletion/export semantics remain correct. | `W07`, `W18`, `W28` |
| F96-068 | **Adaptive Routing & Bandits** | Optimize model/tool/strategy selection from outcomes using constrained bandit or policy methods under safety floors. | Offline replay and canary tests demonstrate gain without violating non-compensable gates; exploration budgets are explicit. | `W06`, `W18`, `W28` |
| F96-069 | **Prompt / Policy Candidate Optimization** | Generate and compare prompt/policy candidates in sandboxed evaluation rather than editing production authority directly. | Candidates require versioned datasets, scorers and independent promotion; benchmark overfit triggers rejection. | `W14`, `W18`, `W27`, `W28` |
| F96-070 | **Retrieval / Memory Adaptation** | Tune ranking, chunking, promotion and retention policies from measured utility while preserving provenance and privacy. | A/B or replay evidence proves utility gain; poisoning, feedback loops and catastrophic forgetting are tested. | `W07`, `W08`, `W18`, `W28` |
| F96-071 | **Online / Offline Adaptation Boundary** | Separate immediate runtime adaptation, offline learned candidates and model-training changes with explicit data/authority boundaries. | Tests prove online signals cannot silently mutate protected model/policy state; rollback restores the prior behavior bundle. | `W20`, `W28`, `W30` |
| F96-072 | **Champion / Challenger Promotion** | Promote learned candidates only through reproducible comparator evaluation, adversarial challenge, canary and rollback readiness. | Promotion record binds candidate, baseline, dataset, scorer, code, policy, budget, verifier and rollback artifact. | `W17`, `W18`, `W27`, `W28`, `W30` |

### F96-S10 — Model Systems, Training & Compute Fabric

Operate provider, local and native models through a hardware-aware runtime with reproducible lifecycle and rollback.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-073 | **Provider-Neutral Model Contract** | Normalize model requests/results, structured output, streaming, tools, errors, usage and cancellation behind stable core contracts. | Adapter conformance tests prove provider objects do not escape boundary; unsupported capabilities degrade explicitly. | `W01`, `W05`, `W06` |
| F96-074 | **Model Capability Router** | Route by quality, modality, latency, cost, context, policy, residency, tool support and health. | Counterfactual routing evals quantify tradeoffs; policy/residency constraints are hard filters, not weighted preferences. | `W06`, `W18`, `W21` |
| F96-075 | **Inference Batching, Cache & Stream Runtime** | Coordinate continuous batching, KV/prefix caches, streaming, cancellation and admission without cross-request leakage. | Concurrency tests prove cache isolation, cancellation finality and bounded queue latency under saturation. | `W05`, `W19`, `W21`, `W29` |
| F96-076 | **Efficient Inference: Quantization & Speculation** | Use quantization, speculative decoding and optimized kernels only with measured quality and deterministic fallback. | Quality/performance gates compare against reference path; unsupported hardware or drift triggers safe fallback. | `W05`, `W18`, `W29` |
| F96-077 | **Distributed Placement & Failover** | Place inference/training work across workers using topology, locality, model shards, health and capacity with lease/fencing semantics. | Node/GPU/network failure drills rehome work without duplicate finalization or silent quality downgrade. | `W19`, `W29`, `W30` |
| F96-078 | **Heterogeneous Accelerator Fabric** | Discover and schedule CPU, GPU, NPU, ASIC and vendor-specific accelerators through capability descriptors rather than hard-coded brands. | Unknown hardware falls back safely; capability probing is versioned and benchmark-backed; memory/topology limits are enforced. | `W21`, `W29`, `W30` |
| F96-079 | **Native Training & Post-Training** | Support dataset lineage, pretraining/adaptation, SFT, preference/reward/verifier training, checkpointing and reproducibility under rights/privacy gates. | Training run manifests reproduce data/code/config/hardware identities; contamination and checkpoint recovery tests pass. | `W18`, `W26`, `W28`, `W29` |
| F96-080 | **Model Lifecycle, Registry & Rollback** | Govern registry, staging, canary, active, deprecated and retired models with compatibility and rollback contracts. | Rollback drill restores exact prior model+adapter+policy bundle; stale clients receive compatible behavior or explicit refusal. | `W05`, `W06`, `W30` |

### F96-S11 — Verification, Safety, Security & Governance

Make correctness, security, privacy, provenance and human authority non-compensable gates rather than soft quality dimensions.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-081 | **Structural & Schema Verification** | Validate types, schemas, invariants, state transitions and output structure before semantic acceptance. | Malformed, partial and adversarial outputs fail deterministically; schema success is never treated as factual success. | `W01`, `W17` |
| F96-082 | **Factual & Evidence Verification** | Verify claims against retrieved/known evidence with contradiction, uncertainty and source-quality handling. | Independent verifier catches unsupported material claims and reports evidence gaps rather than fabricating support. | `W09`, `W17`, `W18` |
| F96-083 | **Code / Action Verification** | Execute tests, static analysis, sandbox checks and postconditions for code or real-world actions before acceptance. | Generated code/actions cannot self-certify; exact-head/result identity binds all acceptance evidence. | `W13`, `W17`, `W18`, `W20` |
| F96-084 | **Adversarial & Red-Team Verification** | Systematically challenge prompt injection, jailbreaks, poisoning, collusion, resource abuse, race conditions and recovery edges. | Regression corpus is versioned; newly found failures become mandatory tests or explicit accepted-risk records. | `W17`, `W18`, `W20` |
| F96-085 | **Prompt-Injection & Trust-Boundary Defense** | Enforce instruction/data separation across retrieval, tools, connectors, files, web and agent handoffs. | Indirect-injection suites show external content cannot authorize tools, alter policy or persist memory without an independent gate. | `W10`, `W13`, `W14`, `W20` |
| F96-086 | **Privacy, Tenant & Data-Use Governance** | Enforce classification, minimization, retention, residency, consent, tenant isolation and purpose limitation end-to-end. | Cross-tenant, export, deletion and residency tests produce zero unauthorized disclosure or orphaned derived data. | `W03`, `W20`, `W30` |
| F96-087 | **Provenance & Supply-Chain Integrity** | Bind code, model, dataset, artifact, dependency, build and release provenance with tamper-evident identities. | SBOM/provenance verification, dependency substitution and artifact-tamper tests fail closed before promotion. | `W17`, `W20`, `W30` |
| F96-088 | **Non-Compensable Promotion & Human Override** | Make safety, privacy, authority, tenant isolation, state integrity, rollback and required human control absolute promotion gates. | Scorecard tests prove quality/cost wins cannot compensate for a failed hard gate; override actions are scoped, signed and auditable. | `W14`, `W17`, `W20`, `W30` |

### F96-S12 — Scientific Autonomy & Frontier Operations

Close the loop with observability, chaos recovery, research, adversarial mirror testing, controlled self-improvement and signed finality.

| Layer | Capability | Build contract | Required acceptance proof | Existing owners |
| --- | --- | --- | --- | --- |
| F96-089 | **Full-Operation Observability & Replay** | Reconstruct an operation from durable state plus logs, metrics, traces, receipts, decisions and version identities. | Independent incident replay explains each critical transition and highlights any unobservable gap as a release blocker. | `W03`, `W17`, `W21` |
| F96-090 | **SLO, Cost & Resource Governors** | Enforce latency, reliability, cost, token, memory, GPU and queue budgets with admission, degradation and error-budget policies. | Saturation tests show bounded tail behavior and declared degradation order; budget overruns cannot trigger unsafe fallback. | `W19`, `W21`, `W30` |
| F96-091 | **Chaos, Recovery & Disaster Autonomy** | Continuously rehearse worker loss, queue duplication, data-store outage, network partition, accelerator reset and restore/rollback paths. | Game-day evidence proves RTO/RPO and exact-once/at-least-once semantics where declared; unrehearsed recovery blocks frontier qualification. | `W19`, `W30` |
| F96-092 | **Autonomous Research Loop** | Run discovery -> evidence graph -> hypothesis -> experiment -> replication -> analysis -> challenge under bounded budgets and research integrity rules. | Research candidates preserve negative results, citations, methods and uncertainty; no experiment promotes itself into production. | `W18`, `W26`, `W27` |
| F96-093 | **Self-Improvement Candidate Factory** | Generate code, routing, policy, prompt, dataset and model candidates from measured weaknesses, isolated from production authority. | Every candidate has hypothesis, diff, expected metric, risk analysis, sandbox result and rejection path; direct self-modification is forbidden. | `W27`, `W28`, `W20` |
| F96-094 | **Hundred-Trial Mirror Room** | Challenge candidate behavior through at least 100 diverse adversarial/simulation attempts before frontier promotion, with attempt independence and failure clustering. | Promotion evidence includes all attempts, seeds/scenarios, discovered failure classes and repair/retest lineage; cherry-picked passes are invalid. | `W17`, `W18`, `W27`, `W28` |
| F96-095 | **Cross-Domain Generalization & Specialist Ensemble** | Combine general and specialist systems through evidence-aware routing while measuring transfer, interference and out-of-domain behavior. | Held-out domain tests quantify gains and regressions; specialist consensus cannot override hard governance gates. | `W06`, `W16`, `W18`, `W28` |
| F96-096 | **Frontier Finality & Signed Release** | Declare the 96-layer superstructure complete only when every layer is independently verified, current-evidence valid, rollback-ready and signed at exact head. | Machine validator reports 96/96 qualified, no stale evidence, no failed hard gate, reproducible release identity and independent final signature. | `W17`, `W18`, `W20`, `W30` |

## Promotion contract

Each layer progresses through:

```text
planned
-> specified
-> implemented
-> integrated
-> independently_verified
-> frontier_hardened
-> signed_complete
```

The machine record must preserve at minimum:

- exact layer and dependency identities;
- mapped work-package/volume ownership;
- implementation commit and repository head;
- code/config/policy/model/data/scorer identities where applicable;
- focused correctness tests;
- adversarial, boundary and recovery tests;
- benchmark/SLO evidence where the layer makes quality, latency, throughput or cost claims;
- implementation signer;
- independent verifier;
- RFC3339 UTC timestamps;
- rollback or safe-disable path;
- evidence freshness state.

A layer with a stale prerequisite automatically loses frontier qualification until the prerequisite is reverified.

## Frontier-96 completion semantics

`frontier_96_qualified` means **all 96 layers** are simultaneously `signed_complete` on current evidence and `F96-096` has an independent finality signature.

It does not replace the existing 421-volume accountability ledger. Existing volume completion and enterprise-superiority qualification remain prerequisite authorities. Frontier-96 adds a higher acceptance surface.

Initial state for this plan revision is **0 / 96 signed complete**. Planning depth is complete; implementation qualification is intentionally unclaimed.

## Construction waves

- **F96-W0:** F96-001..016 — authority, context, memory and knowledge.
- **F96-W1:** F96-017..032 — retrieval, evidence, reasoning and metacognition.
- **F96-W2:** F96-033..048 — planning, search, tools and transactional action.
- **F96-W3:** F96-049..064 — agents, delegation, multimodal and world intelligence.
- **F96-W4:** F96-065..080 — learning, adaptation, model systems, training and compute.
- **F96-W5:** F96-081..096 — verification, security, frontier operations, scientific autonomy and finality.

Waves may overlap only where dependency and mutation-domain analysis proves safety. No wave may lower an enterprise non-compensable gate to increase throughput.

## First implementation frontier

The first implementation batch should materialize `F96-001..008` because every later stratum depends on trustworthy authority/context semantics. The acceptance bundle should include authority-lattice property tests, trust-preserving context compilation, budget/compression benchmarks, replay manifests, adversarial injection cases and exact-head independent verification.
