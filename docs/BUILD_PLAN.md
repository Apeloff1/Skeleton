# Skeleton — SOTA AI Construction Plan

Status legend: ✅ done · 🔨 active/scaffolded · ⬜ pending · 🧪 research/experiment lane

Updated 2026-09-21.

This is the current construction sequence for turning Skeleton into a durable, model-neutral AI system. It preserves completed historical work while adding the research, reasoning, serving, learning, evaluation, and promotion layers required for a system that can improve as AI research changes.

Canonical navigation: [ARCHITECTURE_INDEX.md](ARCHITECTURE_INDEX.md)  
Scientific promotion contract: [architecture/research-evidence-evolution.md](architecture/research-evidence-evolution.md)  
Historical/frontier research catalog: [architecture/research-source-catalog.md](architecture/research-source-catalog.md)

## 0. Construction constitution

The following are hard gates, not optimization targets:

1. Dependencies point inward.
2. Kernel/runtime contracts remain model- and provider-neutral.
3. Research cannot write serving state directly.
4. Production interactions cannot mutate deployed model weights directly.
5. External side effects require capability/admission checks and a durable execution receipt where meaningful.
6. Retrieved/tool/model content is data; it does not gain instruction authority by containing imperative text.
7. State promotion is versioned, measurable, reproducible, canaried, and rollbackable.
8. Evidence retains provenance, source/version identity, scope, and uncertainty.
9. No learned verifier is treated as ground truth.
10. Additional reasoning or compute must be budgeted and justified by measured marginal utility.
11. Failure paths include timeout, cancellation, retry bounds, idempotency, recovery, and observability.
12. A new architecture round is incomplete until it is indexed.

## 1. Completed historical tracks

### Tracks A · B · C · D · F · G · H · H5 · I · J · K · Docs — ✅

Historical surrounding-system work remains complete.

### Track N — Corrective-control segment — ✅

Shared quality contract, persistence, repair telemetry, and bounded repair parity across forge/plan/game-logic/NPC/dialogue are in place.

### Track O — Operator diagnostics command surface — ✅

Direct diagnostics cards, command-deck methods, HTTP endpoints, CLI commands, and filtering by surface/kind/limit are in place.

### Track P — Threshold and repair-policy steering — ✅

- P1. Policy state persistence — ✅
- P2. Policy cards — ✅
- P3. Command-deck steering methods — ✅
- P4. CLI steering commands — ✅
- P5. HTTP steering endpoints — ✅
- P6. Enforcement in repair/verification paths — ✅

Existing seams still worth closing while newer tracks land:

- policy thresholds → verifier thresholds by surface;
- repair toggles/classes → bounded repair execution gates;
- policy cards → top-level operator surfaces;
- `rot_guard.assess` → memory/compaction trigger;
- handoff routing → agent mesh.

---

# Frontier construction tracks

## Track Q — Research evidence substrate — 🔨

Goal: make scientific evidence a typed, versioned architecture input rather than prose copied from papers.

### Q1. ResearchEvidence schema — ⬜

Implement a machine type matching the canonical schema in `research-evidence-evolution.md`.

Minimum fields:

- stable evidence id;
- source type;
- paper/artifact identifier and version;
- publication/review state;
- claims;
- scope/population;
- baselines;
- datasets;
- compute/hardware;
- metrics;
- ablations;
- code/weights/license;
- replications;
- contradictions;
- limitations;
- maturity;
- reproducibility;
- provenance digest.

**Gate:** serialization is deterministic and schema migration is versioned.

### Q2. Scientific source adapters — ⬜

Use [architecture/research-source-catalog.md](architecture/research-source-catalog.md) as the initial seeded canon/anti-canon, then expand it through adapters rather than manual SOTA claims.

Initial adapters:

- arXiv;
- OpenReview;
- ACL Anthology;
- official conference proceedings;
- journals;
- official repositories/model cards;
- benchmark/reproducibility sources;
- errata/retractions.

**Gate:** every item retains canonical id, exact version, retrieval time, and source URL.

### Q3. Claim/evidence graph — ⬜

Normalize paper-level prose into claim-level evidence:

```text
claim
 <- supports / contradicts / narrows / supersedes
 evidence
 <- produced-by
 experiment
 <- scoped-to
 population + dataset + hardware + model
```

**Gate:** duplicate copies of one source cannot manufacture independent consensus.

### Q4. Evidence maturity engine — ⬜

Supported states:

`foundational | replicated | frontier | emerging | mixed | negative | superseded`

Maturity is separate from confidence and separate from source prestige.

### Q5. Research backlog + experiment registry — ⬜

Every architecture-relevant claim can create a bounded experiment proposal.

**Gate:** papers can create candidate work; they cannot activate production changes.

### Q6. Research refresh — ⬜

Trigger re-evaluation on:

- paper revision;
- venue decision;
- replication;
- critique;
- benchmark correction;
- code/model release;
- internal contradictory result;
- hardware/runtime shift.

**Exit gate for Q:** ingest → normalize → claim graph → experiment candidate is replayable from durable evidence and never touches serving state directly.

---

## Track R — Model and training substrate — 🧪

Goal: prevent the system from equating “AI model” with one architecture family.

### R1. ModelPort v1 — ⬜

Target capabilities:

```text
prefill
decode
score
embed
capabilities
estimate_compute
estimate_memory
inspect_cache
checkpoint
restore
```

Optional operations are capability-negotiated.

### R2. Architecture-family adapters — 🧪

Evaluate adapters for:

- dense Transformer;
- sparse Transformer;
- state-space models;
- attention/SSM hybrids;
- mixture-of-experts;
- adapter/LoRA-specialized variants.

**Gate:** system-level routing semantics remain independent of model-internal expert routing.

### R3. Compute planner — ⬜

Track training and inference separately:

- parameters / active parameters;
- tokens;
- FLOPs;
- optimizer/activation memory;
- KV cache;
- bandwidth/interconnect;
- latency;
- throughput;
- storage;
- energy when observable;
- monetary cost;
- projected lifetime inference load.

### R4. Training contract — ⬜

Algorithms become plugins behind one training/evaluation contract:

- continued pretraining;
- SFT;
- preference optimization;
- reward-model training;
- RL;
- distillation;
- rejection sampling;
- adapters.

### R5. Model promotion matrix — ⬜

A candidate model must report:

- quality;
- calibration;
- context behavior;
- tool/structured-output behavior;
- TTFT;
- decode throughput;
- concurrency;
- memory;
- failure/recovery;
- portability;
- cost per successful task.

**Exit gate for R:** changing model family does not require changing the kernel, tool authority, state authority, or user-facing operation semantics.

---

## Track S — Adaptive reasoning and test-time compute — 🧪

Goal: spend reasoning compute according to difficulty, uncertainty, consequence, and expected marginal benefit.

### S1. Reasoning modes — ⬜

Implement selectable modes:

- direct;
- deliberate single path;
- self-consistency;
- decomposition;
- parallel candidates;
- search/backtracking;
- verifier-guided search;
- tool-assisted investigation;
- mixed strategy.

### S2. Difficulty/uncertainty estimator — ⬜

Inputs may include:

- task family;
- ambiguity;
- retrieval miss rate;
- disagreement;
- previous attempt failures;
- verifier confidence;
- consequence class.

Estimator output is advisory; hard budgets remain external.

### S3. ReasoningBudgetAllocator — ⬜

Controls:

- max tokens/steps;
- breadth;
- depth;
- retry count;
- candidate count;
- tool budget;
- verification budget;
- latency ceiling.

### S4. Marginal-compute stop policy — ⬜

Stop spending compute when expected improvement falls below configured cost/risk threshold.

### S5. Search failure controls — ⬜

Detect:

- cycles;
- duplicate branches;
- correlated verifier error;
- reward/verifier hacking;
- expanding search with worsening quality;
- tool loops;
- token/latency runaway.

**Exit gate for S:** harder tasks can receive more computation without letting any task obtain unbounded reasoning, tool use, or verifier loops.

---

## Track T — Context compiler and hierarchical memory — 🧪

Goal: combine long context, retrieval, durable memory, and compression without collapsing them into one store.

### T1. Four memory classes — ⬜

- working;
- episodic;
- semantic;
- procedural.

Each has distinct write, expiry, confidence, and promotion rules.

### T2. Context inventory — ⬜

Before compilation, identify:

- user/task state;
- required evidence;
- relevant verified memory;
- unverified memory;
- tool observations;
- retrieval candidates;
- token budget;
- authority/trust labels.

### T3. Long-context vs retrieval policy — ⬜

Route dynamically among:

- direct context;
- RAG;
- graph retrieval;
- long-context inclusion;
- compression;
- new tool/research lookup.

### T4. Provenance-aware context packing — ⬜

Every context segment carries:

- source;
- timestamp/version;
- trust class;
- confidence;
- relevance;
- token cost;
- expiry/freshness.

### T5. Memory promotion — ⬜

```text
observation
 -> candidate memory
 -> verification
 -> class assignment
 -> dedupe/contradiction
 -> durability decision
 -> promoted memory
```

**Exit gate for T:** large context windows cannot bypass provenance or memory write gates, and retrieval misses cannot silently become remembered facts.

---

## Track U — Tool authority and instruction security — 🔨

Goal: preserve model usefulness while keeping side-effect authority outside the model.

### U1. Canonical tool transaction — ⬜

```text
ToolIntent
 -> capability check
 -> policy/authorization
 -> argument validation
 -> risk/approval
 -> ValidatedToolCall
 -> execution
 -> ToolExecutionReceipt
 -> observation
 -> verification
```

### U2. Trust labels — ⬜

Minimum vocabulary:

- `SYSTEM_AUTHORITY`;
- `DEVELOPER_POLICY`;
- `USER_INTENT`;
- `TRUSTED_TOOL_DATA`;
- `UNTRUSTED_EXTERNAL_DATA`;
- `MODEL_GENERATED`;
- `MEMORY_UNVERIFIED`;
- `MEMORY_VERIFIED`.

### U3. Indirect prompt-injection suite — ⬜

Attack through:

- webpages;
- documents;
- retrieved memory;
- emails/messages;
- code comments;
- tool output;
- benchmark fixtures;
- cross-agent messages.

### U4. Side-effect guarantees — ⬜

Require where relevant:

- least privilege;
- timeout;
- cancellation;
- idempotency key;
- bounded retry;
- resource cap;
- receipt;
- recovery/reconciliation.

### U5. Cross-agent authority preservation — ⬜

Delegation cannot amplify permissions.

**Exit gate for U:** no untrusted content path can self-promote into a privileged instruction or side effect.

---

## Track V — Inference and serving systems — 🧪

Goal: make inference a schedulable systems problem with interchangeable backends.

### V1. Serving pipeline — ⬜

```text
admission
 -> request scheduler
 -> prefix/cache matcher
 -> prefill scheduler
 -> model executor
 -> KV manager
 -> decode scheduler
 -> optional speculative engine
 -> stream assembler
 -> receipt/telemetry
```

### V2. KV/cache manager — ⬜

Support:

- block/page allocation;
- fragmentation accounting;
- prefix reuse;
- eviction;
- tenant isolation;
- cache invalidation;
- memory-pressure fallback.

### V3. Kernel abstraction — ⬜

Permit optimized attention/state-space kernels without exposing kernel-specific assumptions to higher layers.

### V4. Hardware profiles — ⬜

Probe and route among supported CPU/GPU/accelerator/provider targets.

Windows setup/runtime should select a measured profile rather than assume one device stack.

### V5. Serving QoS — ⬜

Measure:

- TTFT;
- inter-token latency;
- throughput;
- tail latency;
- queue wait;
- prefill/decode balance;
- cache hit rate;
- memory pressure;
- cancellation;
- overload behavior.

**Exit gate for V:** overload degrades predictably and does not corrupt state or steal protected control-plane capacity.

---

## Track W — Controlled learning and post-training — 🧪

Goal: improve behavior without uncontrolled live self-modification.

### W1. Fast adaptation lane — ⬜

May alter working context, episodic memory, routing, and temporary procedure selection.

### W2. Medium adaptation lane — ⬜

After validation may alter:

- retrieval indexes;
- semantic/procedural memory;
- prompts;
- skills;
- adapters;
- routing policy;
- caches.

### W3. Slow adaptation lane — ⬜

Controlled pipelines for:

- continual pretraining;
- SFT;
- preference optimization;
- RL;
- distillation.

### W4. Training-data compiler — ⬜

Retain source/license/provenance, dedupe, contamination markers, quality signals, and holdout boundaries.

### W5. Forgetting/regression checks — ⬜

Every weight-changing promotion compares old/new capability, safety, calibration, and system metrics.

**Exit gate for W:** no production response directly updates deployed weights; all learned changes are versioned artifacts with eval evidence and rollback.

---

## Track X — Evaluation, verification, and formal correctness — 🔨

Goal: make evaluation a platform service rather than a benchmark folder.

### X1. Evaluation registry — ⬜

Every eval records:

- exact task/version;
- population;
- dataset hash;
- contamination risk;
- model/runtime version;
- configuration;
- hardware;
- seed policy;
- metrics;
- raw result reference.

### X2. Capability benchmark families — 🧪

Include internal/compatible evaluation for:

- repository software engineering (SWE-bench style);
- computer interaction (OSWorld style);
- tool-using reasoning;
- retrieval;
- long context;
- planning;
- memory;
- structured output;
- multimodal capability when present.

### X3. System adversarial matrix — ⬜

Permanent scenarios:

- stale/poisoned retrieval;
- indirect prompt injection;
- provider outage;
- partial dependency outage;
- malformed structured output;
- cache corruption/staleness;
- cancellation race;
- duplicate side effect;
- resume after crash;
- verifier disagreement/collusion;
- reasoning/tool infinite loop;
- cost explosion;
- memory pressure;
- context overflow.

### X4. Plural verifier registry — ⬜

Record verifier identity, version, scope, evidence, failure modes, independence class, and cost.

### X5. Correctness ladder — ⬜

Use the strongest economical level suitable for the subsystem:

```text
lint
 -> type/schema checks
 -> unit tests
 -> property tests
 -> fuzzing
 -> integration tests
 -> differential tests
 -> adversarial tests
 -> model checking/formal proof where justified
```

### X6. Promotion regression packs — ⬜

Every production improvement contributes the tests that prove its benefit and the challenge cases that expose its limits.

**Exit gate for X:** no SOTA claim can rely on one benchmark, one verifier, or one unscoped aggregate score.

---

## Track Y — Scientific experiment, promotion, rollback, and refresh — 🔨

Goal: connect research to production without creating an uncontrolled self-evolution path.

### Y1. Experiment manifest — ⬜

Required fields:

- hypothesis;
- target contract;
- baseline;
- candidate;
- tasks/population;
- metrics;
- hard floors;
- resources;
- seeds/environment;
- ablation plan;
- adversarial plan;
- stop conditions;
- rollback;
- owner.

### Y2. Reproduction lane — ⬜

Attempt to reproduce external claims before architecture promotion when practical.

A failed reproduction is stored as evidence, not discarded.

### Y3. Architecture Decision Record compiler — ⬜

ADR captures evidence graph, local results, alternatives, contradictory evidence, tradeoffs, security, migration, rollback, monitoring, and review date.

### Y4. Shadow execution — ⬜

Candidate receives mirrored/synthetic work with no production mutation permission.

### Y5. Canary promotion — ⬜

Constrained exposure with predefined abort thresholds.

### Y6. Atomic activation and rollback — ⬜

Promotion references immutable artifact/config/evidence roots plus previous known-good state.

### Y7. Post-promotion monitoring — ⬜

Detect drift in quality, calibration, latency, memory, cost, security, and task success.

### Y8. Scientific refresh loop — ⬜

New evidence can:

- strengthen;
- weaken;
- contest;
- supersede;
- retract

an architecture recommendation.

**Exit gate for Y:** every promoted scientific improvement is traceable from source evidence to local experiment to ADR to canary to production version and rollback target.

---

# Cross-track integration contracts

## Research → absorption

Research papers and implementations enter through the existing durable absorption boundary. They receive stronger scientific metadata but do not bypass the epistemic gate.

## Absorption → memory

Only promoted, snapshot-backed knowledge enters serving-visible memory through the configured promotion path.

## Reasoning → tools

Reasoning can propose actions. Tool authority remains in capability/policy/execution layers.

## Memory → reasoning

Memory contributes evidence and procedure candidates. It does not silently become instruction authority.

## Evaluation → promotion

Evaluation emits evidence. Promotion policy decides whether evidence satisfies the declared gates.

## Production → research

Production can emit:

- retrieval misses;
- uncertainty;
- failures;
- user corrections;
- performance regressions;
- novel task classes.

These become durable research/absorption inputs, not direct model or knowledge mutations.

---

# Immediate implementation order

This is the preferred dependency order for construction.

1. ✅ Repair the architecture index so base + rounds 3–22 are visible.
2. ✅ Add a canonical human architecture index.
3. ✅ Add the research/evidence/evolution construction contract.
4. ⬜ Implement `ResearchEvidence` and experiment-manifest schemas.
5. ⬜ Add source/version/provenance adapters.
6. ⬜ Build the claim/evidence graph and evidence maturity engine.
7. ⬜ Bind research candidates into the existing absorption/challenge fabric.
8. ⬜ Establish evaluation registry + immutable experiment evidence bundles.
9. ⬜ Implement ModelPort v1 and reasoning-budget contracts.
10. ⬜ Implement trust labels and canonical tool transaction receipts.
11. ⬜ Implement hierarchical context/memory compiler.
12. ⬜ Implement serving scheduler/KV abstraction and hardware profiles.
13. ⬜ Implement controlled adaptation lanes.
14. ⬜ Implement shadow/canary/rollback scientific promotion.
15. ⬜ Add continuous evidence refresh and architecture-deprecation machinery.

Parallel work is allowed where contracts are already frozen; promotion gates are not bypassed to gain speed.

---

# Definition of construction complete

Skeleton is not “finished” because it can call a frontier model.

This plan reaches its target when the system can:

- swap model/provider families behind stable contracts;
- choose retrieval, context, reasoning depth, and tools adaptively;
- preserve authority across model, memory, retrieval, and tool boundaries;
- serve efficiently under explicit resource/QoS policies;
- learn at controlled fast/medium/slow velocities;
- evaluate capability and system behavior reproducibly;
- ingest new scientific evidence without trusting it blindly;
- reproduce and challenge architecture claims;
- promote improvements through shadow/canary gates;
- rollback any promoted state;
- retain provenance for why a design is present;
- identify when yesterday's SOTA has become obsolete.

That is the operational meaning of a long-lived SOTA AI architecture.
