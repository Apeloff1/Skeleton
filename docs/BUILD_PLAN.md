# Skeleton — SOTA AI Construction Plan

Status legend: ✅ done · 🔨 active/scaffolded · ⬜ pending · 🧪 research/experiment lane

Updated 2026-09-21.

This is the current construction sequence for turning Skeleton into a durable, model-neutral AI system. It preserves completed historical work while adding the research, reasoning, serving, learning, evaluation, and promotion layers required for a system that can improve as AI research changes.

Canonical navigation: [ARCHITECTURE_INDEX.md](ARCHITECTURE_INDEX.md)
Scientific promotion contract: [architecture/research-evidence-evolution.md](architecture/research-evidence-evolution.md)
Historical/frontier research catalog: [architecture/research-source-catalog.md](architecture/research-source-catalog.md)
Exotic architecture manual: [architecture/exotic-architecture-lab.md](architecture/exotic-architecture-lab.md)
Frontier research atlas: [architecture/frontier-research-atlas-2026.md](architecture/frontier-research-atlas-2026.md)
Research experiment protocols: [architecture/frontier-research-experiment-protocols-2026.md](architecture/frontier-research-experiment-protocols-2026.md)
Research saturation accountability: [architecture/research-saturation-checklist-2026.md](architecture/research-saturation-checklist-2026.md)

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


## Track Z — Deep internals and optimizer control plane — 🧪

Goal: make optimization, numerical stability, parameter updates, and training-system internals explicit, measurable, replaceable subsystems rather than hidden framework defaults.

This track is intentionally below ModelPort and above raw kernels. A candidate optimizer is not “better” because it is newer or faster on one benchmark. It must be evaluated by loss/quality per token, wall-clock, memory, communication, stability, reproducibility, checkpoint cost, downstream task quality, and interaction with model scale, batch size, precision, architecture family, and distributed topology.

### Z0. Mandatory optimizer contract — ⬜

Every optimizer implementation MUST expose a common contract:

\`\`\`text
OptimizerSpec
OptimizerStateSchema
ParameterClassPolicy
StepInput
StepPlan
StepTelemetry
CheckpointCodec
DistributedStateLayout
PrecisionPolicy
FailurePolicy
PromotionEvidence
\`\`\`

Required capabilities:

- initialize from an immutable parameter manifest;
- classify parameters by shape, semantic role, model family, and sharding layout;
- declare optimizer-state bytes per parameter;
- declare supported dtypes and accumulator dtypes;
- declare whether updates are elementwise, matrix/tensor preconditioned, low-rank, orthogonalized, curvature-aware, sign-based, or mixed;
- expose gradient clipping/scaling semantics;
- expose weight-decay semantics separately from gradient update semantics;
- checkpoint and restore bit-for-bit where deterministic execution is supported;
- migrate optimizer state across compatible sharding/topology changes;
- emit step-level and window-level telemetry;
- fail closed on NaN/Inf/corrupt state;
- support shadow/counterfactual evaluation without committing candidate updates.

**Gate:** no training job depends directly on a framework-specific optimizer object outside the adapter layer.

### Z1. Stable baseline family — ⬜

Keep strong baselines permanently available:

- SGD + momentum/Nesterov;
- Adam / AdamW;
- Adafactor;
- LAMB/LARS where large-batch behavior justifies them.

The baseline family is not deprecated when challengers arrive. It anchors regressions, ablations, recovery, and reproducibility.

**Gate:** every challenger comparison includes at least one tuned stable baseline under the same data, tokens, model, precision, hardware, and stopping criterion.

### Z2. Memory-efficient optimizer family — 🧪

Evaluate:

- 8-bit/block-quantized optimizer states;
- factored second moments;
- low-rank gradient projection such as GaLore-style approaches;
- randomized subspace optimization;
- optimizer-state offload;
- optimizer-state sharding;
- mixed-precision moments;
- compressed communication for optimizer/gradient state.

Record separately:

- peak device memory;
- host memory;
- network traffic;
- optimizer-state checkpoint bytes;
- reconstruction/migration cost;
- quality delta;
- instability rate.

**Gate:** memory savings cannot be counted as a win if they move the bottleneck into communication, host memory, checkpointing, or quality loss.

### Z3. Structure-aware and higher-order challengers — 🧪

Candidate families:

- Shampoo-style tensor preconditioning;
- SOAP-style Adam-in-preconditioned-basis methods;
- Sophia-style lightweight curvature estimation;
- low-rank curvature sketches;
- blockwise/quasi-second-order methods;
- trust-ratio variants;
- safe-step / trust-region experiments.

Hard requirements:

- amortized preconditioner cost is measured;
- matrix decomposition/eigendecomposition frequency is explicit;
- numerical conditioning is monitored;
- sharded/distributed behavior is defined;
- fallback path exists when preconditioner state is corrupt or unaffordable.

### Z4. Orthogonalized update family — 🧪

Evaluate Muon-style orthogonalized momentum for compatible matrix parameters while retaining a conventional optimizer for incompatible tensors such as embeddings, biases, scalars, and selected gates.

Required experiments:

- exact parameter-class map;
- orthogonalization backend comparison;
- Newton–Schulz iteration count / alternative polar decomposition backend;
- update norm and spectral behavior;
- distributed gather/reduce implications;
- mixed Muon + AdamW state accounting;
- scale-transfer behavior across width/depth/batch changes;
- sensitivity to weight decay and momentum.

**Gate:** optimizer assignment by parameter semantic class is explicit and versioned; no shape heuristic silently changes behavior after a model refactor.

### Z5. Sign and parameter-free / schedule-light challengers — 🧪

Evaluate where appropriate:

- Lion-style sign momentum;
- Prodigy / D-adaptation families;
- schedule-free AdamW/SGD variants;
- learned or automatically adapted step-size controllers.

Measure:

- tuning burden;
- warmup sensitivity;
- stop-time sensitivity;
- transfer across model sizes;
- large-batch behavior;
- interaction with weight decay;
- checkpoint/eval mode semantics.

**Gate:** “fewer hyperparameters” is measured as reduced tuning compute and operator burden, not assumed from API surface alone.

### Z6. Optimizer router by parameter class — ⬜

Introduce a versioned \`ParameterOptimizationMap\`.

Possible classes:

- token embeddings;
- positional/rotary parameters where trainable;
- attention Q/K/V/O matrices;
- latent-KV projections;
- MLP up/down/gate matrices;
- MoE router;
- expert matrices;
- normalization scales;
- biases;
- output head;
- adapters/LoRA;
- recurrent/SSM state parameters;
- multimodal projection layers.

Each class declares:

- optimizer family;
- LR multiplier;
- weight decay;
- clipping;
- precision;
- sharding;
- update-frequency policy;
- frozen/trainable state.

**Massive-upgrade hook:** allow optimizer mixtures inside one model while preserving one atomic global training step.

### Z7. Optimization flight recorder — ⬜

Persist bounded diagnostic windows for:

- global and per-class gradient norm;
- update norm;
- update/weight ratio;
- gradient noise scale estimates;
- cosine similarity between gradient, momentum, and applied update;
- loss-scale events;
- NaN/Inf incidence;
- clipping fraction;
- optimizer-state saturation/quantization error;
- preconditioner condition estimates;
- Hessian-trace / curvature sketches where economical;
- per-layer learning progress proxies;
- dead/exploding expert/router indicators;
- communication wait time;
- step-time decomposition.

Data must be sampled/compressed so observability does not become a training bottleneck.

### Z8. Counterfactual optimizer replay — ⬜

For selected windows, retain enough gradient/update evidence to replay alternative optimizer policies offline or in a shadow lane without mutating the authoritative training run.

Uses:

- compare candidate updates against the committed optimizer;
- diagnose divergence;
- test LR/WD policy changes;
- detect whether a new optimizer benefit came from update geometry or secondary hyperparameter changes;
- reproduce rare catastrophic steps.

**Gate:** replay evidence is explicitly bounded because full-gradient retention at scale is prohibitively expensive.

### Z9. Stability circuit breakers — ⬜

Automatic hold/rollback conditions include:

- non-finite loss/gradient/update;
- sudden loss explosion;
- persistent loss plateau beyond declared tolerance;
- update/weight ratio excursion;
- gradient norm discontinuity;
- optimizer-state corruption;
- precision overflow/underflow;
- routing collapse in MoE;
- data-loader/sample corruption;
- collective communication mismatch;
- divergence between replicas;
- checkpoint verification failure.

Actions may include:

\`\`\`text
warn -> reduce step / recover scaler -> quarantine batch
     -> restore optimizer checkpoint -> restore full training checkpoint
     -> pause run for operator/research review
\`\`\`

No autonomous recovery step may erase the evidence required to explain the failure.

### Z10. Precision-aware optimization — 🧪

Treat precision as part of optimizer design:

- FP32 master-state reference;
- BF16/FP16 compute;
- FP8 training paths;
- FP8 optimizer moments where supported;
- experimental FP4 paths;
- stochastic rounding;
- per-tensor/per-channel scaling;
- outlier handling;
- accumulation precision;
- loss scaling;
- mantissa/error tracking.

**Gate:** lower precision must pass long-horizon stability tests, not only short benchmark runs.

### Z11. Hyperparameter scaling and transfer — 🧪

Build a reproducible scaling-policy layer for:

- learning rate;
- warmup;
- batch size;
- sequence length;
- width;
- depth;
- active MoE parameters;
- optimizer family;
- weight decay;
- gradient clipping.

Evaluate µP-style transfer and optimizer-specific shape-aware transfer rules as research candidates.

**Gate:** a scaling rule is promoted only when it predicts successful transfer across at least two meaningful scale changes, with failed transfers retained as negative evidence.

### Z12. Data/optimizer co-design — 🧪

Optimization diagnostics must be joinable with:

- data source;
- curriculum stage;
- domain mixture;
- sequence length;
- packing density;
- duplicate rate;
- toxicity/quality filters;
- synthetic-data provenance.

This permits distinguishing optimizer instability from data phase changes.

### Z13. Batch and sequence adaptation — 🧪

Candidate controller can tune within declared bounds:

- microbatch size;
- gradient accumulation;
- global batch;
- sequence-length curriculum;
- token packing;
- activation checkpointing level.

Objective is not simply maximum throughput. Optimize successful learning progress per wall-clock and per resource budget while maintaining quality floors.

### Z14. Distributed optimizer topology — ⬜

Support versioned layouts for:

- data parallel;
- FSDP/ZeRO-style sharding;
- tensor parallel;
- pipeline parallel;
- context/sequence parallel;
- expert parallel;
- combinations of these.

The optimizer adapter must know which state is:

- replicated;
- sharded;
- partitioned by tensor dimension;
- partitioned by expert;
- offloaded;
- recomputed.

### Z15. Atomic optimizer checkpoint and migration — ⬜

A checkpoint must bind:

- model parameter version;
- optimizer spec/version;
- optimizer state schema;
- parameter-class map;
- LR/schedule state;
- scaler/precision state;
- RNG state;
- data cursor;
- distributed topology;
- training manifest;
- evidence digest.

Migration to a new topology or optimizer requires an explicit migration function and verification step.

### Z16. Optimizer promotion gate — ⬜

A challenger may become a default only after:

1. controlled baseline comparison;
2. equal-token and equal-wall-clock views;
3. quality-per-compute analysis;
4. memory and communication accounting;
5. long-horizon stability;
6. checkpoint/resume validation;
7. scale-transfer test;
8. failure-injection test;
9. downstream evaluation;
10. reproducibility on a second seed/configuration;
11. rollback target;
12. signed ADR.

**Exit gate for Z:** optimizer choice becomes a versioned, observable, reversible training policy, with no hidden framework default controlling authoritative weight updates.

---

## Track AA — Rare massive upgrades and full-stack step changes — 🧪

Goal: maintain a quarantined path for upgrades that can change the system by an order of magnitude in capability, scale, context, cost, or reliability, while preventing novelty from bypassing evidence.

These are deliberately high-upside, high-complexity candidates. They should be tested as architectural forks, shadow backends, or isolated training programs before they can affect the main runtime.

### AA1. Hardware-native sparse attention — 🧪

Evaluate natively trainable sparse attention designs, including hierarchical token compression/selection patterns, against exact attention.

Measure:

- pretraining FLOPs;
- forward/backward wall-clock;
- decode latency;
- long-context quality;
- retrieval-like behaviors;
- kernel occupancy;
- sparsity overhead;
- worst-case dense fallback.

**Massive-upgrade condition:** sparse attention must improve end-to-end lifecycle cost, not just theoretical complexity.

### AA2. Hybrid attention + state-space/recurrent core — 🧪

Prototype mixed blocks that combine:

- full/local/sparse attention;
- selective state-space layers;
- recurrent memory/state;
- occasional global attention.

ModelPort must hide the internal family.

Evaluate:

- long-context quality;
- recurrent-state corruption/recovery;
- streaming latency;
- training stability;
- cache/state size;
- parallelism limitations.

### AA3. Fine-grained / shared-expert MoE — 🧪

Build a model-internal expert plane with:

- expert parallelism;
- shared experts;
- fine-grained specialization;
- dropless/block-sparse execution;
- capacity and load telemetry;
- router collapse detection;
- expert hot-spot detection;
- expert checkpoint sharding.

Keep this entirely separate from application/provider/agent routing.

### AA4. Latent/compressed KV architecture — 🧪

Investigate architectural reductions in KV-cache footprint through learned latent projections, grouped/shared KV, compression, quantization, or other cache-aware attention designs.

Required metrics:

- bytes/token;
- TTFT;
- inter-token latency;
- long-context quality;
- cache reconstruction cost;
- prefix reuse compatibility;
- speculative decoding compatibility.

### AA5. 100K→1M+ context training program — 🧪

Context length is a training/system property, not a config toggle.

Program includes:

- sequence/context parallelism;
- ring/2D attention variants;
- long-context curriculum;
- position-scaling strategy;
- checkpoint/recompute policy;
- memory-pressure models;
- retrieval-vs-context routing;
- needle/aggregation/reasoning evals;
- cache and serving implications.

No claimed context length is accepted without useful-task quality at that length.

### AA6. FP8-first training stack — 🧪

Build a complete FP8 training candidate:

- matrix compute;
- gradients;
- collective communication where supported;
- optimizer moments;
- scaling/outlier policy;
- long-horizon stability probes;
- BF16 reference lane.

FP8 is promoted only if full-run quality parity/floors and recovery behavior are demonstrated.

### AA7. FP4 experimental training fork — 🧪

Keep FP4 strictly experimental until hardware, numerical methods, and reproducibility mature.

Required:

- mixed-precision escape hatches;
- outlier compensation;
- sensitive-layer allowlist;
- accumulation policy;
- long-run collapse detection;
- cross-hardware reproducibility.

### AA8. Topology-aware 6D+ parallelism — 🧪

Treat parallelism as a placement search problem over:

- data;
- tensor;
- pipeline;
- sequence/context;
- expert;
- optimizer/state sharding;
- optional model replicas / heterogeneous devices.

The planner consumes real interconnect topology and profiles rather than assuming a uniform cluster.

### AA9. Communication/computation overlap compiler — 🧪

Schedule:

- reduce-scatter/all-gather;
- expert all-to-all;
- tensor collectives;
- preconditioner work;
- optimizer steps;
- checkpoint transfers;

against forward/backward compute to reduce exposed communication.

Require deadlock detection and deterministic debug mode.

### AA10. Elastic training and live topology migration — 🧪

Research restart-safe resizing:

- worker loss;
- worker addition;
- topology reshaping;
- expert repartition;
- optimizer-state redistribution;
- data-cursor preservation;
- RNG/seed semantics.

The canonical state remains checkpoint-based; elasticity cannot create unverifiable weight histories.

### AA11. Asynchronous/lazy checkpoint plane — 🧪

Evaluate staged checkpointing through:

- device → host;
- host → local durable storage;
- durable storage → remote/object storage.

Track checkpoint lag and recovery-point objective.

**Gate:** a “completed checkpoint” is not declared until integrity verification and required durability level are satisfied.

### AA12. Training straggler and silent-fault intelligence — ⬜

Detect:

- slow accelerators;
- network tail events;
- thermal/power throttling;
- ECC/hardware faults;
- dataloader starvation;
- collective retries;
- skewed expert load;
- host-memory pressure;
- filesystem stalls.

Correlate incidents with optimizer and loss telemetry so performance faults are not misdiagnosed as model instability.

### AA13. Kernel fusion/autotuning compiler — 🧪

Candidate subsystem:

\`\`\`text
model IR
 -> shape/dtype/topology profile
 -> candidate kernels
 -> correctness oracle
 -> microbenchmark
 -> compile/cache
 -> runtime guard
 -> fallback
\`\`\`

Targets include:

- attention;
- MLP;
- normalization;
- RoPE/position operations;
- MoE dispatch;
- quantize/dequantize;
- optimizer transforms;
- state-space scans.

Never permit benchmark-selected kernels to bypass numerical correctness tests.

### AA14. Dynamic depth / conditional layer execution — 🧪

Investigate token/task-dependent layer skipping or early exit.

Must preserve:

- deterministic full-depth fallback;
- quality floors;
- calibration;
- structured-output correctness;
- tool-call reliability;
- adversarial robustness.

### AA15. Multi-token / speculative generation stack — 🧪

Support interchangeable speculative mechanisms:

- draft model;
- multi-head/token prediction;
- tree candidates;
- verifier/acceptance engine.

Track accepted tokens per verification pass, distribution correctness where required, extra memory, and latency under concurrency.

### AA16. Disaggregated prefill/decode serving — 🧪

Separate compute-heavy prefill and memory/bandwidth-heavy decode when workload and hardware justify it.

Design includes:

- KV transfer protocol;
- placement;
- affinity;
- prefix-cache locality;
- admission control;
- failure/retry semantics;
- network saturation handling;
- autoscaling.

### AA17. KV-centric multi-tier memory fabric — 🧪

Treat KV/cache as movable state across:

- accelerator HBM;
- host RAM;
- local high-speed storage;
- remote cache/storage where latency permits.

Require:

- content/version keying;
- tenant isolation;
- invalidation;
- compression format;
- integrity checks;
- eviction cost model;
- privacy/security policy.

### AA18. Cross-model distillation foundry — 🧪

Create controlled teacher ensembles for:

- logits;
- rationales/process traces where allowed;
- tool trajectories;
- verifier labels;
- synthetic curriculum;
- retrieval behavior.

Teacher output is evidence/training data, never production authority.

### AA19. Architecture surgery and transplant lab — 🧪

Research controlled transformations such as:

- dense → MoE expansion;
- attention block replacement;
- insertion of recurrent/SSM blocks;
- KV-compression retrofits;
- tokenizer/vocabulary extension;
- width/depth growth;
- adapter merge/unmerge.

Every transformation needs parameter mapping, initialization rationale, regression suite, and rollback to the source checkpoint.

### AA20. Automated optimizer/architecture co-search — 🧪

Bounded search can propose:

- optimizer family;
- per-parameter optimizer map;
- LR/WD;
- precision;
- checkpointing level;
- parallelism layout;
- kernel profile;
- model-block variants.

Search is constrained by resource budgets and uses held-out evaluation. It cannot directly promote a candidate.

### AA21. Learned optimizer / meta-optimizer quarantine — 🧪

Explore learned update rules only behind a strict sandbox.

Risks to test:

- scale transfer failure;
- distribution shift;
- optimizer reward hacking;
- hidden state corruption;
- catastrophic rare steps;
- poor interpretability;
- checkpoint incompatibility.

Default promotion bar is higher than for analytic optimizers.

### AA22. Self-measuring architecture — ⬜

Every massive-upgrade candidate must produce a standardized \`UpgradeImpactReport\`:

- capability delta;
- quality delta;
- training cost;
- inference cost;
- memory delta;
- energy if available;
- hardware assumptions;
- implementation complexity;
- operational complexity;
- failure modes;
- security effect;
- migration complexity;
- rollback cost;
- evidence maturity;
- confidence/uncertainty;
- known negative results.

### AA23. Pareto frontier registry — ⬜

Do not collapse all upgrades into a single score.

Maintain fronts for:

- quality vs training FLOPs;
- quality vs inference cost;
- quality vs latency;
- throughput vs latency;
- context vs memory;
- reliability vs utilization;
- portability vs specialization.

A candidate can be superior for one deployment profile and inferior for another.

### AA24. Rare-event stress campaigns — ⬜

Before promotion, inject:

- node loss;
- partial network partitions;
- corrupted optimizer shard;
- stale checkpoint shard;
- duplicated batch;
- missing data shard;
- cache poisoning;
- non-finite activation;
- router collapse;
- all-to-all slowdown;
- prefill/decode imbalance;
- cancellation storms;
- near-OOM pressure;
- precision-scaler oscillation.

### AA25. Massive-upgrade promotion law — ⬜

A rare massive upgrade requires all of:

1. immutable experiment manifest;
2. evidence maturity classification;
3. reproducible baseline;
4. minimal and full-scale ablation;
5. systems benchmark;
6. capability benchmark;
7. adversarial/failure campaign;
8. cost accounting;
9. migration plan;
10. rollback plan;
11. shadow deployment where applicable;
12. canary;
13. signed architecture decision record;
14. post-promotion monitors;
15. scheduled revalidation date.

**Exit gate for AA:** Skeleton can absorb high-upside architectural advances aggressively in research while keeping production evolution slow, observable, reversible, and evidence-bound.

---

# Mandatory plan-item accountability for Z / AA

All new Z and AA work items inherit this record schema:

\`\`\`yaml
id: Z# | AA#
status: pending | active | blocked | validated | promoted | rejected
created_at: 2026-09-21T21:33:00+02:00
updated_at: <ISO-8601>
owner: <human-or-authorized-agent>
evidence:
  - <test/benchmark/experiment/ADR reference>
dependencies:
  - <stable IDs>
signoff:
  required: true
  signer: <identity>
  signed_at: <ISO-8601>
  artifact_digest: <digest>
  decision: accept | reject | supersede
\`\`\`

Rules:

- checkboxes/status are updated only with evidence;
- signoff is mandatory for validated/promoted states;
- timestamps are mandatory for state transitions;
- a signature binds the artifact/evidence digest, not merely prose;
- a superseded item retains its full history;
- rejected experiments remain searchable negative evidence;
- provider/agent execution must read the canonical plan and dependency contracts before modifying authoritative implementation.

### Planning checkpoint signature

\`\`\`text
checkpoint_id: PLAN-20260921-INTERNALS-OPTIMIZERS-MASSIVE-UPGRADES
created_at: 2026-09-21T21:33:00+02:00
scope: Track Z + Track AA + accountability contract
status: authored
signoff_required_for_implementation_claims: true
authoring_actor: ChatGPT
production_authority_granted: false
\`\`\`

---


## Track AB — Adversarial foundations and systemic hardening — 🔨

Goal: close the cross-cutting failure modes that can invalidate every higher-level capability claim.

Canonical hostile audit: architecture/masterplan-gap-audit.md

Track AB is a prerequisite gate for production-grade claims in Tracks R–AA. Research experiments may continue in isolation, but a subsystem cannot claim production readiness while a relevant P0 gap remains open.

### AB1. Representation/tokenizer identity — ⬜
Implement immutable RepresentationSpec with tokenizer/version, vocabulary digest, normalization, byte fallback, special tokens, encode/decode semantics, compatibility class, and migration tests.
**Gate:** every model artifact binds exactly one representation identity.

### AB2. Data lineage + deterministic mixture root — ⬜
Implement SourceRecord, DatasetManifest, DatasetShardManifest, MixtureManifest, SampleLineage, TransformReceipt, DeletionTombstone, SyntheticExampleLineage, and HoldoutBoundary.
**Gate:** every weight-changing checkpoint binds a reconstructable data/mixture lineage root or explicitly declares a non-reproducible limitation.

### AB3. Unified model artifact manifest — ⬜
Bind architecture, representation, weights, dtype/quantization, adapters, model code, runtime ABI, kernel requirements, training parent, optimizer parent, data root, eval root, provenance and signatures into one immutable model artifact identity.
**Gate:** serving never loads an unbound directory of weights.

### AB4. Durable schema/state evolution — ⬜
Standardize expand → tolerant-read/dual-read → backfill → verify → reader switch → writer switch → contract migrations across databases, events, memory, receipts, manifests, eval state and optimizer state.
**Gate:** rollback must include state compatibility, not only binary rollback.

### AB5. Evaluation firewall — ⬜
Separate development, regression, blind-promotion and production-observation evals. Budget blind-set queries and prohibit training/search optimization against exhausted holdouts.
**Gate:** contaminated, leaked or adaptively exhausted evidence cannot justify promotion.

### AB6. Principal, tenant and delegation envelope — ⬜
Every consequential action carries authenticated principal, tenant, session, capability set, delegation chain, expiry and policy version.
**Gate:** delegation cannot silently broaden authority; cross-tenant access fails closed.

### AB7. Execution sandbox — ⬜
Contain generated code and high-risk tools with explicit filesystem/network/process/resource/secret boundaries and cleanup verification.
**Gate:** high-risk execution cannot share the authoritative control-plane process.

### AB8. Supply-chain and artifact trust root — ⬜
Require digests, origin, build/toolchain identity, dependency locks, SBOM where relevant, model/data license metadata, scan evidence, signature verification, revocation and quarantine.
**Gate:** download/parse success is never equivalent to trust.

### AB9. Authoritative storage consistency contract — ⬜
Every durable store declares transaction, isolation, durability, replication, corruption detection, snapshot, backup, restore, capacity and split-brain semantics.
**Gate:** callers cannot assume guarantees stronger than the storage adapter declares.

### AB10. Distributed time, leases, fencing and event ordering — ⬜
Introduce monotonic local deadlines and lease epochs; use fencing counters plus explicit sequence, correlation, causation, and deduplication metadata.
**Gate:** a stale/expired writer cannot commit after losing authority.

### AB11. Secret lifecycle / taint propagation — ⬜
Define secret fetch, scope, projection, TTL, rotation, revocation, prompt/log/trace handling, child-process inheritance, crash-dump handling and artifact scans.
**Gate:** raw secret values do not enter ordinary config/provenance/prompts/logs by default.

### AB12. Disaster recovery — ⬜
Declare RPO/RTO and restore dependencies for every authoritative state family. Run restore drills including stale backups and unavailable dependencies.
**Gate:** a backup does not count until restoration is verified.

### AB13. Control-plane isolation — ⬜
Reserve independent queue/capacity and authority for revoke, rollback, kill switches, configuration, identity and recovery.
**Gate:** data-plane saturation cannot starve the system's ability to stop or recover itself.

### AB14. Immutable configuration snapshot — ⬜
Bind model routing, tool policy, memory policy, eval policy, resource policy and feature flags into a digest-addressed ConfigSnapshot.
**Gate:** consequential eval/run evidence without reproducible config identity is invalid.

### AB15. Side-effect commit/unknown/compensation protocol — ⬜
For non-idempotent external actions, require provider idempotency, transactional protocol, compare-and-set, compensation, reconciliation, or explicit non-retryable UNKNOWN state.
**Gate:** irreversible UNKNOWN outcomes are never blindly retried.

### AB16. Deletion/tombstone propagation — ⬜
Propagate deletion across primary records, indexes, vector stores, memories, caches, summaries, exports and future training candidates while retaining non-content audit identity where policy permits.

### AB17. Training-poisoning/backdoor defense — ⬜
Add poisoning, malicious synthetic data, preference-pair, teacher-trajectory, training-code and optimizer-state tampering scenarios to permanent evaluation.

### AB18. Safe artifact deserialization/load boundary — ⬜
Enforce size, shard-count, dtype/shape, decompression, parser, code-execution and metadata limits before privileged loading.

### AB19. Tamper-evident authority audit — ⬜
Bind actor, principal, causation, config/artifact digests and ordered integrity evidence for meaningful authority changes and side effects.

### AB20. Safe mode / break glass — ⬜
Define a unified read-only/degraded state that freezes promotion and write-capable tools, preserves diagnostics, serves only known-good artifacts, and allows tightly audited rollback/recovery.

### AB21. Global resource governor and backpressure — ⬜
Add quotas, priority classes, fairness, starvation detection, cost ceilings, control-plane reserve, admission/load shedding and explicit upstream/downstream backpressure.

### AB22. Observability integrity and monitor-of-monitors — ⬜
Detect missing/delayed telemetry, trace loss, exporter failure, timestamp skew, cardinality explosions and misleading aggregates.

### AB23. Mixed-version/API/event compatibility — ⬜
Every durable/public contract declares schema version, reader/writer floor, unknown-field behavior, negotiation, deprecation window and compatibility tests.

### AB24. Structured decoding and semantic validation — ⬜
Use schema/grammar-constrained decoding where available for machine actions; parsing and repair cannot invent privileged fields.

### AB25. Calibrated uncertainty / OOD / abstention — ⬜
Separate model probability, verifier confidence, retrieval confidence, evidence completeness and calibrated task-success/OOD estimates. Support retrieve/tool/escalate/abstain policies.

### AB26. Cache coherence and tenant isolation — ⬜
Cache identity binds tenant, artifact, representation, policy, adapters and relevant runtime semantics. Define invalidation after promotion, deletion, policy change and memory retraction.

### AB27. Durable event delivery/reconciliation — ⬜
Define outbox/inbox or equivalent delivery, dedupe, poison-event, consumer checkpoint, replay and reconciliation semantics. Exactly-once claims require proof.

### AB28. Multi-agent deadlock/livelock/byzantine containment — ⬜
Add ownership leases, bounded dependency graphs, deadlock detection, arbitration, cancellation and capability-preserving delegation.

### AB29. Provenance-laundering prevention — ⬜
Derived summaries, chunks, embeddings, translations and model outputs retain source/trust ancestry; transformation cannot raise authority.

### AB30. Numeric/IR/kernel correctness envelope — ⬜
Define model/compiler IR and dtype-specific numerical tolerances, reference implementations, randomized shape fuzzing, extreme-value tests, deterministic debug path and safe fallbacks.

### AB31. Capacity, autoscaling and denial-of-wallet controls — ⬜
Reserve failover/recovery headroom; use hysteresis for autoscaling; enforce per-principal/tenant/global spend ceilings for context, search and tools.

### AB32. Telemetry privacy and parser-bomb defenses — ⬜
Default telemetry to metadata rather than raw sensitive content. Bound bytes, nesting, archive members, decompression ratios and parsing time.

### AB33. Cancellation commit barriers — ⬜
Every side-effecting operation declares cancellable → committing → committed phases and post-commit compensation semantics.

### AB34. Provider semantic drift / ABI compatibility — ⬜
Run semantic canaries for providers/tools; artifacts declare runtime/kernel/plugin ABI requirements; installer/runtime profiles enforce compatibility.

### AB35. Historical restore + retention/GC — ⬜
Restore-test old snapshots; define evidence/provenance retention, compaction and legally required deletion without silently destroying lineage identity.

### AB36. Trust-root bootstrap and compromise recovery — ⬜
Boot verifies keys, policy roots, manifests and trusted code before loading mutable models/plugins/policies. Define root-key revocation, replacement trust root, re-sign/revalidation strategy, historical audit verification, partial-rotation recovery and KMS-unavailable bootstrap.
**Gate:** compromise of a root signing/trust key has a tested containment and re-root procedure.

### AB37. Combined fault campaigns — ⬜
Run the audit matrix across state, network, worker, artifact, authority, resource and observability axes.

Requirements:
- every P0 path: all single-axis faults;
- every P0 side effect: pairwise state × network × authority;
- promotion/rollback: state × artifact × observability;
- distributed training/serving: network × worker × resource;
- periodic selected three-axis campaigns.

### AB38. Residual race/boundary attack closure — ⬜
Close G071–G130, including TOCTOU approval races, SSRF/DNS rebinding, path/symlink/archive escapes, dependency confusion, JIT-cache poisoning, accelerator residue, KMS/key-rotation failures, distributed checkpoint atomicity, snapshot consistency, embedding/index version drift, RNG/data-cursor recovery, collective hangs, silent corruption, feature-flag skew, canary representativeness, replay attacks, canonical serialization, speculative-output commit boundaries, provenance loss in compression/summarization, synthetic-data feedback loops, agent impersonation and stale operator actions.

**Gate:** no residual gap may remain an unowned implicit assumption; every item is closed, downgraded with bounded evidence, or explicitly scheduled with a production-readiness restriction.

### AB39. Systemic lifecycle and recovery closure — ⬜
Close G131–G200: deterministic invariant/policy precedence, bootstrap/recovery dependency cycles, dependency-reduced safe mode, break-glass survivability, staging/production parity, chaos-harness validation, rate/quota cascades, region/data-residency boundaries, encryption/service identity, webhook authenticity, prompt/policy exfiltration, graph/retrieval fanout abuse, license revocation lineage, adapter/quantization/model-router compatibility, long-running workflow version envelopes, restore/replay reconciliation, durable fencing across restore, and backend-specific activation atomicity.

**Gate:** recovery can be executed from a documented minimal dependency set; internal services authenticate identity; restored work reconciles external-effect receipts before dispatch; policy conflicts resolve deterministically.

**Exit gate for AB:** every P0 audit finding has a canonical contract, owner, machine invariant, tests, fault injection, observability, recovery semantics and signed evidence. No subsystem with an applicable open P0 may claim production-grade status.

---


## Track AC — Exotic architecture laboratory — 🧪

Goal: explore architectures that may invalidate today's default assumptions about tokenization, autoregressive decoding, fixed model depth, immutable inference-time weights, dense activation, conventional precision, or the boundary between memory and computation.

Track AC is deliberately **not** a production-default lane. It is a quarantined architecture laboratory. Evidence-backed candidates can graduate toward Track AA only after they demonstrate a real full-stack advantage. Speculative candidates can remain useful even if they fail, because negative evidence prevents repeated dead-end exploration.

### AC0. ExoticCandidate contract — ⬜

Every candidate declares:

- candidate id/version;
- architectural family;
- hypothesis;
- which current invariant/assumption it challenges;
- representation/tokenizer requirements;
- persistent vs ephemeral state;
- whether weights/state mutate at inference time;
- training algorithm;
- inference algorithm;
- compute graph shape;
- stopping/convergence rule;
- memory/KV/state complexity;
- hardware assumptions;
- distributed-training implications;
- serving implications;
- tool/memory/authority implications;
- reproducibility status;
- strongest baseline;
- falsification test;
- kill criteria;
- reset/replay semantics;
- migration/rollback path;
- evidence maturity.

**Gate:** an exotic candidate without a falsifiable advantage hypothesis remains an idea note, not an experiment.

### AC1. Test-time neural memory — 🧪

Prototype Titans/MIRAS-style long-term neural memory where a bounded memory module learns from the active sequence.

Required separations:

- model-internal ephemeral memory ≠ Skeleton durable semantic/episodic memory;
- inference-time parameter/state updates cannot gain tool or control-plane authority;
- per-request/per-session/resettable modes are distinct;
- memory writes carry resource budgets and rollback/reset semantics.

Measure:

- recall at extreme context;
- reasoning over recalled state;
- state growth;
- write/read latency;
- interference/forgetting;
- cross-session leakage;
- poisoning sensitivity;
- reproducibility after replay.

**Kill:** if learned memory loses provenance-critical facts, creates cross-tenant/session leakage, or fails to outperform retrieval/context baselines at equal cost.

### AC2. Tokenizer-free dynamic byte latent modeling — 🧪

Evaluate BLT-style raw-byte models with learned/dynamic patches.

Research questions:

- can RepresentationSpec support a byte-native family without pretending token ids are universal?
- can dynamic patch boundaries remain reproducible and cache-safe?
- does byte-level robustness improve multilingual, rare-symbol, code, malformed-text and security-sensitive behavior?
- how do prompt/cache/tool schema boundaries work when computation units are dynamic patches?

**Kill:** if end-to-end training/serving cost or structured-output reliability loses materially to a tuned tokenizer baseline without compensating robustness.

### AC3. Discrete-diffusion / iterative-denoising language generation — 🧪

Build a ModelPort family that does not assume left-to-right autoregressive decode.

Candidate modes:

- masked-token denoising;
- discrete diffusion;
- block diffusion;
- AR/diffusion hybrid;
- parallel refinement;
- confidence-guided remasking.

Required new semantics:

- draft/partial state is not committed output;
- iteration count and convergence are budgeted;
- tool calls cannot execute from an unstable intermediate state;
- streaming semantics explicitly distinguish tentative vs committed text.

**Kill:** if parallel decoding gains disappear under concurrency, structured output, tool use, long responses, or quality-equivalent settings.

### AC4. Recurrent latent-depth reasoning — 🧪

Evaluate recurrent-depth models that spend more test-time compute by repeating hidden computation rather than emitting longer visible chains.

Candidates include:

- shared-block recurrence;
- Universal-Transformer-like depth recurrence;
- YOCO-U-style partial recursion;
- recurrent latent reasoning.

Measure:

- capability vs recurrence count;
- adaptive per-token depth;
- convergence/oscillation;
- KV/state footprint;
- hidden-state corruption;
- self-speculation compatibility;
- reasoning gains without specialized verbalized traces.

**Kill:** if extra recurrence produces unstable/non-monotonic quality, uncontrollable latency, or no gain over ordinary test-time search at equal compute.

### AC5. Equilibrium/fixed-point language modules — 🧪

Explore implicit-depth modules that iteratively solve for a hidden fixed point.

Required:

- convergence detector;
- iteration cap;
- non-convergence fallback;
- numerical tolerance;
- deterministic debug mode;
- implicit-gradient correctness tests;
- hardware/runtime profiling.

**Kill:** if convergence pathologies, training complexity, or tail latency overwhelm depth/parameter-sharing benefits.

### AC6. Conditional depth / Mixture-of-Depths — 🧪

Route only selected tokens through expensive layers while preserving a hard compute budget.

Measure:

- router stability;
- token starvation;
- important-token miss rate;
- structured-output reliability;
- adversarial routing attacks;
- cache/layout implications;
- quality under fixed FLOPs.

**Kill:** if routing complexity or missed-token failures erase wall-clock benefit.

### AC7. Differential/noise-canceling attention — 🧪

Evaluate differential-attention families that explicitly subtract competing attention distributions or otherwise suppress irrelevant context.

Measure:

- retrieval precision;
- long-context distraction;
- activation outliers;
- numerical stability;
- extra softmax/kernel cost;
- compatibility with sparse/flash attention;
- prompt-injection robustness as a measured outcome, not an assumed property.

### AC8. Native ternary / ~1.58-bit model family — 🧪

Treat BitNet-like ternary-weight models as a distinct train-from-scratch architecture, not merely post-training quantization.

Measure:

- quality/token;
- training stability;
- CPU/GPU/NPU inference;
- energy/memory;
- kernel portability;
- activation precision;
- KV precision;
- adapter/finetune compatibility;
- checkpoint/storage benefits.

**Massive-upgrade hook:** pair with sparsity only after independent baselines exist.

### AC9. Fully sparse activation substrate — 🧪

Evaluate Q-Sparse-style activation sparsity independently of MoE.

Research:

- token/channel sparsity;
- block sparsity;
- straight-through training behavior;
- hardware-realized speedup;
- outlier sensitivity;
- interaction with 1.58-bit weights;
- interaction with MoE and conditional depth.

**Kill:** theoretical FLOP reduction without measured end-to-end speed/energy improvement.

### AC10. Sparse-BitNet compound substrate — 🧪

Jointly evaluate:

- ternary weights;
- low-bit activations;
- semi-structured N:M sparsity;
- sparse activations;
- sparse KV where appropriate.

This is a compound candidate and therefore requires factorial ablations. No gain may be attributed to the combined architecture without separating the contribution of each mechanism.

### AC11. Cross-layer shared sparse routing — 🧪

Evaluate a routing/index structure computed once or infrequently and reused across attention layers.

Questions:

- can routing cost be amortized?
- does one routing error propagate through many layers?
- can route reuse create stale attention?
- what does it do to KV layout and distributed partitioning?

### AC12. Latent multimodal language substrate — 🧪

Explore continuous latent units for images/audio/video while preserving discrete text/code semantics.

Candidate pattern:

- shared causal backbone;
- modality-specific encoder/decoder;
- continuous latent vectors;
- diffusion/refinement head for continuous outputs;
- common provenance/authority envelope.

**Gate:** modality conversion cannot erase source/time/coordinate provenance.

### AC13. Reversible model blocks — 🧪

Explore reversible residual/Transformer blocks to reconstruct activations during backward passes rather than store them.

Measure:

- activation-memory reduction;
- recompute overhead;
- numerical reconstruction drift;
- interaction with low precision;
- pipeline/tensor parallelism;
- checkpointing complexity.

### AC14. Learned context compression state — 🧪

Train a model-internal compressor that converts long context into bounded latent state.

It competes against:

- raw long context;
- retrieval;
- conventional summarization;
- Titans-style test-time memory;
- recurrent/SSM state.

Required probes:

- lost-detail rate;
- contradiction preservation;
- provenance retention;
- adversarial compression;
- reversibility/inspectability.

### AC15. Multi-timescale neural state — 🧪

Build separate fast/medium/slow internal state channels with different decay/write rates.

Examples:

- token-local state;
- segment/session state;
- learned long-term neural state.

Skeleton durable memory remains external and separately governed.

### AC16. Fast-weight / weight-space working memory — 🧪

Explore bounded inference-time updates to a small fast-weight module.

Rules:

- base model weights remain immutable;
- fast weights have explicit scope/TTL;
- reset is deterministic;
- state is checksum-addressed;
- cross-tenant/session reuse is prohibited unless explicitly promoted through normal memory policy.

### AC17. Hypernetwork-generated ephemeral adapters — 🧪

A controller generates small adapter weights for a task/session instead of retrieving a fixed adapter.

Measure:

- generation cost;
- adapter stability;
- reproducibility;
- security;
- hidden capability drift;
- task transfer;
- whether generated weights outperform prompt/context adaptation.

### AC18. On-demand expert synthesis — 🧪

Research whether rare domains/tasks justify creating temporary low-rank or micro-expert modules from demonstrations/evidence.

Lifecycle:

propose → train/synthesize → sandbox eval → ephemeral use → expire or submit to normal promotion.

No generated expert becomes durable automatically.

### AC19. Expert birth/merge/retire dynamics — 🧪

For MoE-like substrates, study changing expert topology over training:

- spawn overloaded specialties;
- merge redundant experts;
- retire dead experts;
- rebalance routers;
- preserve checkpoint mapping.

**Kill:** topology churn that destroys reproducibility or optimizer-state continuity.

### AC20. Architecture-family switching router — 🧪

Allow one high-level ModelPort to route between materially different substrates:

- dense Transformer;
- recurrent-depth;
- SSM/hybrid;
- diffusion;
- byte latent;
- ternary/sparse family.

Routing decision is treated as a full model-version transition with capability/semantic constraints, not merely a latency optimization.

### AC21. Neural compiler / learned execution graph — 🧪

Explore models that emit or select an intermediate computation graph before execution.

Possible nodes:

- neural block;
- retrieval;
- deterministic math;
- parser;
- symbolic solver;
- simulator;
- tool.

Execution remains outside model authority and inherits sandbox/tool policy.

### AC22. Differentiable/neuro-symbolic program substrate — 🧪

Research explicit latent programs or typed symbolic intermediate representations that can be checked before execution.

Target advantages:

- exactness;
- compositionality;
- inspectable plans;
- formal/property verification opportunities.

**Kill:** symbolic overhead without measurable reliability or generalization gains.

### AC23. Latent world-model simulator — 🧪

Introduce a model-internal predictive environment state for tasks where action consequences matter.

Strict boundaries:

- simulation ≠ observation;
- imagined state carries MODEL_GENERATED trust;
- tools/environment receipts override predictions;
- the simulator cannot fabricate authoritative state.

### AC24. Model-predictive planning loop — 🧪

Use world-model rollouts to rank candidate action sequences before real tool execution.

Measure:

- calibration of predicted outcomes;
- planning depth;
- branching cost;
- simulator exploitation;
- distribution shift;
- value of real observations.

### AC25. Graph-native relational substrate — 🧪

Investigate architectures where entities/relations/events are first-class internal computation units rather than only retrieved text.

Compare:

- graph neural processing;
- graph attention;
- hypergraph state;
- text+graph hybrids.

Provenance must survive graph projection and aggregation.

### AC26. Continuous-time / event-driven neural state — 🧪

Explore continuous-time recurrent/state-space dynamics for irregular event streams.

Potential domains:

- telemetry;
- markets/time series;
- sensor streams;
- long-running agents.

Requires explicit timestamp quality and clock semantics from Track AB.

### AC27. Neural cellular / local-rule recurrent substrate — 🧪

Moonshot lane for computation built from repeated local update rules instead of deep unique layers.

Potential advantages:

- extreme parameter sharing;
- scalable iterative compute;
- local fault containment.

Promotion bar: exceptionally high.

### AC28. Spiking / neuromorphic backend — 🧪

Keep an interface experiment for event-driven/spiking hardware.

Research questions:

- conversion vs native training;
- latency/energy under sparse activity;
- precision/capability loss;
- state reset/replay;
- portability.

No hardware-efficiency claim without real-device measurement.

### AC29. Analog / photonic accelerator substrate — 🧪

Define only the portability boundary needed to test analog/photonic matrix engines if accessible.

Required:

- numeric-error model;
- calibration;
- drift;
- hardware-specific reproducibility;
- digital reference path;
- exact artifact/hardware identity.

### AC30. Error-correcting neural compute — 🧪

Research selective redundancy for critical neural computations:

- replicated hidden-state checks;
- activation checksums;
- parity-like tensor checks;
- selective recomputation;
- dual-path verification.

Goal: tolerate silent hardware/numeric faults without tripling the full model cost.

### AC31. Heterogeneous model federation — 🧪

Build experiments where different model families cooperate through typed belief/evidence objects instead of plain chat.

Possible roles:

- reasoner;
- verifier;
- retriever;
- simulator;
- coder;
- planner.

Independence is measured by training/provider/evidence lineage, not model count.

### AC32. Belief-state / probabilistic cognition layer — 🧪

Represent selected uncertain propositions as explicit distributions/intervals rather than one generated sentence.

Useful for:

- conflicting evidence;
- scientific claims;
- planning under uncertainty;
- sensor fusion.

Must not imply calibrated probability where calibration evidence is absent.

### AC33. Energy-based / iterative constraint inference — 🧪

Explore generation as minimizing a learned or hybrid constraint energy rather than one-pass next-token prediction.

Potential uses:

- globally constrained structured output;
- planning;
- consistency repair;
- multimodal alignment.

Convergence and local-minimum behavior are first-class failure modes.

### AC34. Bidirectional revise-anywhere generation — 🧪

Research models that can revise earlier output positions before commit.

Applications:

- code;
- structured documents;
- proofs;
- planning.

External consumers receive only committed revisions unless the interface explicitly supports tentative edits.

### AC35. Hierarchical block generation — 🧪

Generate plans/segments/blocks before token-level realization.

Compare:

- paragraph/AST/block latent plans;
- block diffusion;
- multi-token prediction;
- conventional AR decoding.

Measure semantic coherence and editability, not only tokens/sec.

### AC36. Self-speculative recurrent model — 🧪

Use cheap early/recurrent states from the same model as draft predictions and deeper states as verifier.

Research:

- acceptance rate;
- shared-error correlation;
- cache sharing;
- latency;
- exact-distribution guarantees where required.

### AC37. Architecture morphing / continuation training — 🧪

Extend AA19 into repeatable transformation research:

- dense → sparse;
- dense → MoE;
- token → byte-latent;
- standard attention → differential/sparse;
- fixed depth → recurrent depth;
- precision reduction;
- expert growth.

Every morph requires a weight/state mapping and a baseline from scratch when affordable.

### AC38. Per-request ephemeral learning — 🧪

A highly quarantined lane where a small mutable module learns during one request/workflow and is destroyed afterward.

Requirements:

- no durable weight mutation;
- strict budget;
- reproducible reset;
- poison isolation;
- no authority amplification;
- receipt recording that ephemeral adaptation occurred.

### AC39. Self-measuring architecture controller — 🧪

A controller may propose architecture/runtime choices based on measured task and hardware state.

It may select among pre-approved candidates but cannot invent/promote new authority.

Inputs:

- task class;
- context shape;
- hardware pressure;
- latency budget;
- confidence;
- expected marginal quality.

Outputs are bounded by a declared candidate set.

### AC40. Automated architecture synthesis sandbox — 🧪

Moonshot lane for bounded search over block graphs, recurrence, routing, precision, memory and decoding strategies.

Search can create candidates, not truth.

Hard limits:

- finite search space or explicit budget;
- isolated training/eval;
- blind promotion holdout;
- no direct production writes;
- mandatory simplification/ablation after discovery;
- reproducible genotype/architecture manifest.

### AC41. Exotic compound systems — 🧪

Only after single mechanisms are understood, test combinations such as:

- byte latent + recurrent depth;
- recurrent depth + neural long-term memory;
- diffusion + block autoregression;
- ternary weights + sparse activations + conditional depth;
- latent multimodal + diffusion heads;
- world model + neuro-symbolic planner;
- neural memory + retrieval + graph state.

**Gate:** compound systems require factorial or staged ablation. A five-mechanism bundle cannot claim causality from one aggregate win.

### AC42. Exotic anti-hype / falsification protocol — ⬜

Every exotic experiment must attempt to disprove itself.

Required views:

- strongest tuned conventional baseline;
- equal training tokens;
- equal wall-clock;
- equal inference cost;
- equal memory;
- equal hardware where meaningful;
- scaling trend, not one model size;
- downstream task quality;
- long-tail/tail-latency;
- failure recovery;
- operator complexity;
- implementation LOC/maintenance burden;
- portability;
- security impact.

An exotic architecture is rejected or retained only as research history if the advantage disappears after full-stack normalization.

### AC43. Exotic state-containment law — ⬜

Any candidate with mutable inference-time neural state must declare:

- state owner;
- scope;
- TTL;
- tenant/session binding;
- reset function;
- serialization format;
- integrity digest;
- replay semantics;
- poisoning boundary;
- promotion path;
- deletion behavior.

**Invariant:** mutable neural state is never equivalent to durable trusted memory.

### AC44. Exotic promotion ladder — ⬜

Promotion path:

idea → literature/evidence → toy reproduction → controlled scale → systems prototype → independent baseline → ablation → hostile audit → shadow → canary → Track AA candidate → production consideration.

Required kill switches:

- numerical instability;
- runaway recurrence/iterations;
- unbounded state growth;
- cross-tenant/state leakage;
- unreproducible hidden-state mutation;
- inability to checkpoint/reset;
- no measured full-stack advantage;
- violation of Track AB P0 invariants.

**Exit gate for AC:** Skeleton can test architecture-changing ideas without allowing novelty, hidden mutable state, or benchmark wins to bypass provenance, authority, recovery, or production-readiness gates.

---

# Exotic architecture tiers

**Tier E1 — evidence-backed frontier:** AC1–AC13.
**Tier E2 — radical but engineering-plausible:** AC14–AC26, AC31–AC39.
**Tier E3 — moonshot / hardware / architecture search:** AC27–AC30, AC40–AC41.

Tier is evidence maturity, not prestige. Candidates may move both directions.

---


## Track AD — Research saturation, replication, and frontier synthesis — 🔨

Goal: turn frontier research into a continuously refreshed, contradiction-aware experimental program rather than a static bibliography.

Canonical atlas: [architecture/frontier-research-atlas-2026.md](architecture/frontier-research-atlas-2026.md)

Track AD specializes Track Q. Q builds the evidence machinery; AD defines the **research workload** that must flow through it.

### AD0. ResearchQuestion registry — ⬜

Create a durable registry:

```text
ResearchQuestion
  question_id
  statement
  affected_contracts[]
  current_conclusion
  confidence
  evidence_for[]
  evidence_against[]
  unresolved_variables[]
  next_experiment
  falsification_condition
  owner
  review_at
```

Seed with RQ001–RQ010 from the atlas.

**Gate:** unresolved research questions remain explicitly unresolved; no consensus score silently turns uncertainty into architecture truth.

### AD1. Source-normalization backlog — ⬜

Normalize the atlas priority source list into ResearchEvidence records.

Required first wave includes:

- foundational architecture/scaling/retrieval anchors;
- 2025–2026 sparse attention, neural memory, byte latent, recurrent depth and diffusion work;
- optimizer/precision frontier;
- data mixture and synthetic-data evidence;
- test-time reasoning/verifier work;
- agent/memory/tool research;
- serving/KV/network systems;
- formal verification;
- monitorability/agent safety;
- interpretability.

**Gate:** exact identifier/version and source state are stored; workshop, rejected, withdrawn, preprint and peer-reviewed items cannot collapse into one maturity class.

### AD2. Claim-level decomposition — ⬜

Break each source into atomic claims.

Example:

```text
paper: optimizer X
  claim A: lower training loss at equal tokens
  claim B: lower wall-clock at hardware H
  claim C: lower state memory
  claim D: stable at batch B
```

Each claim gets its own evidence scope and contradiction edges.

**Gate:** one paper cannot create "consensus" by contributing multiple correlated metrics as if they were independent replications.

### AD3. Baseline registry — ⬜

For each research family define the strongest credible baseline.

Baseline metadata:

- artifact/version;
- training tokens;
- tuning budget;
- hardware;
- software/kernel version;
- precision;
- inference protocol;
- evaluation version;
- operator effort.

**Gate:** candidate comparisons without baseline parity are discovery evidence only.

### AD4. Research reproduction classes — ⬜

Support:

1. **sanity reproduction** — smallest implementation proving the mechanism exists;
2. **paper-scale reproduction** — reproduce reported setting where affordable;
3. **transfer reproduction** — different data/model/hardware;
4. **systems reproduction** — measure full-path wall-clock/cost;
5. **adversarial reproduction** — intentionally search for failure regions.

A research claim's maturity records which reproduction classes it has passed.

### AD5. Equal-resource normalization — ⬜

Every comparative experiment should expose multiple normalization views:

- equal tokens;
- equal training FLOPs;
- equal wall-clock;
- equal accelerator-hours;
- equal peak memory;
- equal inference latency;
- equal monetary budget;
- equal tuning/search budget.

**Gate:** no single normalization is silently treated as universal.

### AD6. Scale-transfer matrix — ⬜

For each promising method track transfer across:

- model width;
- depth;
- total parameters;
- active parameters;
- sequence length;
- batch;
- token budget;
- data distribution;
- hardware topology.

Classify:

`stable_transfer | partial_transfer | inversion | unknown`.

### AD7. Hardware-transfer matrix — ⬜

Research results are re-evaluated across relevant:

- CPU;
- NVIDIA GPU generations;
- AMD/ROCm where supported;
- Windows/DirectML where applicable;
- accelerators/NPU;
- cluster interconnect;
- storage/network tiers.

Theoretical FLOPs do not establish hardware transfer.

### AD8. Negative-evidence registry — ⬜

Permanently preserve:

- failed reproduction;
- null result;
- unstable run;
- optimizer divergence;
- scale inversion;
- hardware regression;
- benchmark contamination;
- unexpected quality tradeoff;
- security regression;
- operator-complexity blowup.

A rejected method remains searchable.

### AD9. Contradiction-resolution engine — ⬜

When credible evidence disagrees, compare:

- population/task;
- model family;
- model scale;
- data;
- training duration;
- hyperparameter search;
- hardware;
- metric definition;
- evaluator;
- implementation maturity.

Output may remain `mixed`.

**Gate:** contradiction is not resolved by publication date or venue prestige alone.

### AD10. Research freshness/decay — ⬜

Every research conclusion gets:

- evidence date;
- last checked;
- refresh trigger;
- review date.

High-velocity domains receive shorter refresh periods:

- reasoning;
- serving;
- agents;
- low precision;
- model safety;
- frontier architectures.

### AD11. Architecture research lane — 🧪

Reproduce and compare:

- dense attention;
- NSA-style sparse attention;
- SSM/hybrid;
- MoE;
- conditional depth;
- recurrent latent depth;
- neural memory;
- byte latent;
- diffusion/AR hybrids.

Track AC remains the quarantine for the most exotic variants.

### AD12. Optimizer research lane — 🧪

Priority:

- tuned AdamW;
- Muon;
- SOAP;
- GaLore/low-rank state;
- LoRA-Pre;
- memory-efficient/minimalist challengers.

Required research details:

- update-RMS normalization;
- optimizer-state bytes;
- communication;
- numerical instability;
- batch scaling;
- scale transfer.

### AD13. Precision research lane — 🧪

Evaluate:

- BF16 reference;
- FP8;
- low-precision optimizer state;
- FP4 experimental;
- ternary/native low-bit architecture separately.

Measure late-run stability, not only short benchmarks.

### AD14. Data-mixture research lane — 🧪

Implement multi-fidelity mixture experiments.

Track:

- domain weights;
- language weights;
- quality;
- diversity;
- curriculum;
- transfer-to-scale.

### AD15. Synthetic-data research lane — 🧪

Compare:

- human-only;
- unconstrained synthetic;
- verified synthetic;
- human-anchored synthetic;
- token-edited/semi-synthetic;
- bootstrapped synthetic;
- multi-teacher synthetic.

Track long-tail coverage and ancestry depth.

### AD16. Retrieval/context/memory research lane — 🧪

Experiments:

- RAG vs long context;
- multi-granularity memory;
- conversation+document hybrid retrieval;
- belief revision;
- neural memory vs external memory;
- graph state.

### AD17. Reasoning/test-time compute lane — 🧪

Compare under exact protocol manifests:

- direct;
- long single trace;
- self-consistency;
- Best-of-N;
- tournament/aggregation;
- tree/prefix search;
- verifier-guided;
- latent recurrent depth;
- tool-assisted.

### AD18. Verifier research lane — 🧪

Study:

- deterministic checkers;
- execution;
- formal proof;
- process reward models;
- generative PRMs;
- independent model critics;
- ensembles.

Explicitly measure correlated failure and verifier gaming.

### AD19. Agent horizon research lane — 🧪

Build controlled tasks with fixed decision logic and increasing:

- action count;
- state transitions;
- elapsed time;
- tool diversity;
- recovery requirements.

Measure where success collapses.

### AD20. Tool-use research lane — 🧪

Study:

- tool discovery;
- selection;
- schema quality;
- tool-description manipulation;
- deterministic retrieval;
- stateful tool protocols;
- failure recovery.

Tool capability remains separate from tool authority.

### AD21. Scientific-agent research lane — 🧪

Evaluate research stages independently:

- literature retrieval;
- gap identification;
- hypothesis;
- experimental design;
- coding;
- debugging;
- running;
- statistical analysis;
- replication;
- report generation.

Use FIRE/RExBench-like contamination-resistant tasks.

### AD22. Serving/KV/network research lane — 🧪

Priority reproductions:

- disaggregated prefill/decode;
- SmartGen-like selective KV transfer;
- load-aware prefill deflection;
- network-aware decode selection;
- robust KV reservation under output-length uncertainty;
- quality-aware compression + eviction;
- prefix locality + fairness.

### AD23. Evaluation-science lane — ⬜

Build:

- static regression sets;
- blind promotion holdouts;
- dynamic contamination-resistant evals;
- saturation detectors;
- benchmark retirement;
- evaluator versioning;
- query budgets.

### AD24. Agent-safety/monitorability lane — ⬜

Permanent research/eval families:

- action-level monitoring;
- covert sabotage simulations;
- motivated judge mislabeling;
- destructive action;
- unauthorized disclosure;
- monitorability;
- CoT controllability;
- tool manipulation;
- indirect prompt injection.

Use defense in depth; no single monitor is authority.

### AD25. Interpretability usefulness lane — 🧪

Compare:

- neuron circuits;
- SAE/transcoder circuits;
- attribution;
- causal intervention;
- counterfactual behavior prediction.

Success metric is utility for prediction/debugging/intervention, not human-plausible labels.

### AD26. Formal-methods lane — 🧪

Adapters for:

- Lean;
- SMT where applicable;
- model checking;
- schema/property checkers.

Study natural-language → formal semantic preservation.

### AD27. Uncertainty/calibration lane — 🧪

Calibrate:

- output correctness;
- trajectory success;
- retrieval correctness;
- environment uncertainty;
- verifier disagreement;
- OOD.

Build explicit abstention/escalation policies.

### AD28. Multimodal/world-model lane — 🧪

Research:

- continuous multimodal latents;
- reciprocal cross-modal reasoning;
- GUI dynamics/world models;
- action-conditioned world models;
- rollout uncertainty;
- simulator exploitation.

Predicted state remains MODEL_GENERATED.

### AD29. Research-agent self-evaluation quarantine — ⬜

An AI research agent cannot declare its own hypothesis reproduced.

Independent validation must come from:

- deterministic tests;
- separate evaluator;
- held-out evidence;
- human review where configured;
- reproducible artifacts.

### AD30. Research budget allocator — ⬜

Allocate research compute by:

- expected information gain;
- potential system impact;
- evidence uncertainty;
- experiment cost;
- reversibility;
- dependency criticality.

Cheap falsification runs precede giant training runs.

### AD31. Sequential experiment design — 🧪

Use previous experiments to narrow parameter/architecture search while preventing adaptive overfitting to blind promotion evals.

Separate:

- development metrics;
- research-selection metrics;
- blind promotion metrics.

### AD32. Causal contribution / ablation ledger — ⬜

For compound candidates record:

- component;
- interaction;
- marginal gain;
- cost;
- failure contribution.

No bundle receives causal credit without ablation.

### AD33. Research artifact graph — ⬜

Connect:

```text
source
 -> claim
 -> question
 -> experiment
 -> code
 -> data
 -> run
 -> result
 -> ADR
 -> regression
```

Every edge is versioned and digest-addressable where practical.

### AD34. Reproducibility capsule — ⬜

Every major result should package:

- git commit;
- artifact manifests;
- data roots;
- config;
- environment;
- seeds;
- hardware;
- logs;
- metrics;
- raw outputs;
- evaluator versions;
- known nondeterminism.

### AD35. Research conclusion compiler — ⬜

Generate a scoped conclusion:

```text
For <population/model/hardware/task>,
evidence as of <date> supports <claim>
relative to <baseline>
under <constraints>,
with <uncertainty>.
```

The compiler must refuse an unscoped "SOTA" conclusion.

### AD36. Frontier research dashboard — ⬜

Per domain expose:

- open questions;
- maturity;
- strongest evidence;
- contradictory evidence;
- local reproduction;
- next experiment;
- blockers;
- last refresh.

### AD37. Research regression tests — ⬜

Machine checks ensure:

- atlas is indexed;
- source records retain maturity;
- negative evidence cannot disappear silently;
- open questions cannot be marked resolved without evidence;
- production authority remains false for research-only candidates.

### AD38. Research saturation checkpoint — ⬜

Planning checkpoint:

```text
PLAN-20260921-FRONTIER-RESEARCH-SATURATION
atlas=docs/architecture/frontier-research-atlas-2026.md
conclusions=FR001..FR114
research_questions=RQ001..RQ010
source_verifications=SV001..SV046
frontier_delta=FD001..FD015
experiment_queue=RA001..RI003
production_authority_granted=false
research_refresh_required=true
```

### AD39. Source-status attestation — ⬜

For every priority source, record the exact current status:

- accepted/peer-reviewed;
- preprint;
- submission/ARR;
- withdrawn;
- official-organization evidence;
- unresolved.

**Gate:** accepted, submitted, preprint and withdrawn are never collapsed into one "published research" label.

### AD40. Identifier and version resolution — ⬜

Resolve and bind:

- arXiv ID/version;
- OpenReview forum/submission ID;
- DOI/venue where available;
- official technical report URL identity;
- code/model/data repository commit or release;
- source date and last-modified date.

**Gate:** a title match alone is insufficient evidence identity.

### AD41. Research independence graph — ⬜

Track correlated evidence through:

- shared authors;
- shared base model;
- shared data;
- shared benchmark;
- shared evaluator;
- shared code;
- shared provider;
- shared hardware;
- direct method ancestry.

**Gate:** five correlated papers cannot count as five independent replications.

### AD42. Methods extraction and hidden-variable ledger — ⬜

For consequential findings, extract:

- model size/family;
- data;
- training tokens;
- optimizer;
- LR/schedule;
- precision;
- hardware;
- batch;
- context;
- inference protocol;
- evaluator;
- seeds;
- selection/tuning budget;
- omitted/unknown variables.

Unknown methods remain explicit uncertainty.

### AD43. Benchmark provenance and contamination audit — ⬜

For every benchmark used for architecture promotion, record:

- creation/release date;
- public/private status;
- web availability;
- candidate training contamination risk;
- evaluator version;
- saturation/headroom;
- prompt/template version;
- known benchmark corrections.

### AD44. Research-agent governance — ⬜

AI research workers must operate under:

- immutable experiment manifests;
- sandboxed code execution;
- benchmark access controls;
- hidden promotion holdouts;
- scorer-variance defenses;
- generated-data provenance;
- trajectory audit;
- independent recomputation or review.

**Gate:** a research agent cannot mark its own result reproduced, accepted, or promotion-ready.

### AD45. Monitorability/version drift research — ⬜

Maintain monitorability as a versioned measured property over:

- model artifact;
- training recipe;
- reasoning effort;
- monitor model;
- observations available to the monitor;
- threat/task population;
- adversarial evasion;
- false-positive and false-negative evidence.

**Gate:** monitorability results do not transfer automatically after model/training/reasoning changes.

### AD46. Whole-trajectory safety science — ⬜

Evaluation must include sequences where risk emerges from accumulation:

- covert code modification;
- motivated/misleading classification;
- repeated privilege use;
- delayed external side effects;
- data exfiltration;
- unauthorized disclosure;
- hidden cleanup avoidance;
- post-error recovery;
- evaluation awareness.

### AD47. First-party evidence triangulation — ⬜

First-party deployment evidence may create urgent threat models and experiments, but architecture conclusions seek independent corroboration where possible.

Record:

- organization;
- access asymmetry;
- proprietary data unavailable for reproduction;
- local replication proxy;
- cross-lab evidence;
- uncertainty.

### AD48. September 2026 frontier-delta queue — 🧪

Reproduce or operationalize the highest-impact FD findings:

1. research-agent anti-cheating and independent validation;
2. monitorability drift across model/training versions;
3. trajectory-level safety evaluation;
4. judge incentive/mislabeling stress tests;
5. OOD detector generalization;
6. counterfactual interpretability usefulness;
7. unified KV/network/topology serving experiment;
8. inference-protocol manifests for reasoning;
9. factorial synthetic-data study;
10. source-status freshness automation.
11. prospective-memory trigger/lifecycle benchmark;
12. action-horizon/subgoal abstraction study;
13. adversarial tool-metadata selection study;
14. semantic-faithfulness vs formal-validity verifier split;
15. research-agent stage-by-stage capability decomposition;
16. typed prospective-intention-store vs retrospective-memory comparison.

### AD49. Research claim expiry and revalidation — ⬜

A conclusion can expire without becoming false.

Expiration triggers:

- newer stronger baseline;
- venue/status change;
- retraction/correction;
- new negative result;
- model generation change;
- hardware generation change;
- benchmark contamination/saturation;
- local reproduction failure;
- production telemetry contradicting scope.

Expired conclusions remain in lineage but cannot silently support new promotion decisions.

### AD50. Research saturation integrity gate — ⬜

Before claiming research saturation for a domain, require:

- at least one foundational anchor;
- at least one current frontier source where applicable;
- negative/counterevidence;
- source-status verification;
- strongest baseline;
- local experiment;
- replication status;
- scale/hardware scope;
- unresolved contradictions;
- refresh date;
- implementation dependency.

### AD51. Domain evidence matrix — ⬜

Maintain one current evidence matrix across all Track AD domains:

- durable evidence;
- fragile frontier;
- strongest counterevidence;
- mandatory baseline;
- blocking local experiment;
- implementation dependency.

**Gate:** no domain may be labeled "researched" from a source list alone.

### AD52. Contradiction ledger — ⬜

Maintain CX001–CX024 as explicit unresolved or scoped tensions.

Every contradiction records:

- evidence for each side;
- scope differences;
- methodological differences;
- what experiment would discriminate;
- current architecture posture.

**Gate:** contradictory evidence is never averaged into a vague consensus.

### AD53. Research-debt registry — ⬜

Maintain RDE001–RDE036.

Each debt item binds:

- borrowed assumption;
- risk if wrong;
- claims blocked;
- minimum retirement evidence;
- owner;
- refresh deadline.

**Gate:** production or architecture claims disclose material open research debt.

### AD54. Baseline parity contract — ⬜

A challenger baseline comparison is invalid unless the reference receives comparable:

- tuning budget;
- kernels/runtime;
- precision;
- data;
- context/inference budget;
- hardware;
- checkpoint/resume correctness;
- evaluation exposure.

### AD55. Selection-budget and multiple-comparison accounting — ⬜

Record how many variants were attempted before the reported winner.

Search-heavy architecture optimization must report:

- configurations;
- tuning/search algorithm;
- pilot runs;
- benchmark accesses;
- failed/discarded runs;
- human interventions.

### AD56. Variance and catastrophic-failure accounting — ⬜

When multiple full seeds are affordable, report them.

When they are not:

- run smaller-scale seed studies;
- retain failed/diverged runs;
- report uncertainty;
- separately report rare catastrophic failures.

**Gate:** one successful frontier run does not imply zero variance.

### AD57. External-validity ledger — ⬜

For every consequential result, declare which dimensions remain untested:

- model family;
- model size;
- language/domain;
- context length;
- hardware;
- topology;
- concurrency;
- adversarial setting;
- failure/recovery;
- geographic/provider environment.

### AD58. Lifecycle-cost accounting — ⬜

Research comparisons include material costs beyond the focal training/inference kernel:

- data synthesis/filtering;
- preprocessing;
- index construction;
- training;
- optimizer state;
- checkpoint/storage;
- serving;
- retrieval/search/verifier calls;
- networking;
- operations;
- migration/rollback.

### AD59. Research freshness SLA — ⬜

Default review windows follow evidence volatility.

High-volatility topics such as agents, monitorability, serving, low precision, research automation, and test-time scaling receive shorter refresh intervals than foundational results.

Refresh checks:

- latest version/status;
- new code/data;
- independent replication;
- counterevidence;
- stronger baseline;
- benchmark corrections;
- material hardware/runtime changes.

### AD60. Debt retirement and reopening — ⬜

Research debt states:

```text
OPEN
 -> EXPERIMENT_DESIGNED
 -> RUNNING
 -> EVIDENCE_COLLECTED
 -> CHALLENGED
 -> RETIRED | PARTIALLY_RETIRED | INVALIDATED | DEFERRED
```

A retired debt can reopen after:

- model-family change;
- scaling regime change;
- data/optimizer change;
- hardware change;
- benchmark correction;
- local production contradiction.

**Gate:** "paper says so" cannot retire local debt.

### AD61. Research experiment protocol registry — ⬜

Maintain RXP001–RXP035 as canonical experiment designs.

Every RXP protocol declares:

- question/hypothesis;
- null hypothesis where meaningful;
- variables;
- controls;
- held-constant dimensions;
- tuning budget;
- primary/secondary metrics;
- stop/failure rules;
- artifacts;
- decision vocabulary;
- research-debt targets.

### AD62. Experiment pre-registration envelope — ⬜

Before expensive or promotion-relevant runs, freeze:

- primary metric;
- baseline;
- key hyperparameter range;
- success/failure threshold;
- stop rule;
- evaluation set;
- analysis plan.

Post-hoc changes are allowed only if disclosed and marked exploratory.

### AD63. Experiment result state machine — ⬜

Allowed terminal/summary states:

```text
SUPPORTED_IN_SCOPE
PARTIALLY_SUPPORTED
NULL_RESULT
FALSIFIED_IN_SCOPE
INCONCLUSIVE_VARIANCE
INCONCLUSIVE_RESOURCE_LIMIT
INVALID_METHOD
INVALID_BASELINE
INVALID_EVALUATION
REPRODUCTION_FAILED
```

**Gate:** non-positive results are not automatically relabeled "needs more scale."

### AD64. Experiment artifact integrity — ⬜

Before results enter the claim graph, require:

- immutable code commit;
- config digest;
- dataset manifest;
- model artifact identity;
- evaluator version;
- hardware/software manifest;
- retained failures;
- baseline-parity review;
- raw evidence reference.

### AD65. Research experiment sequencing — ⬜

Execute high-information cheap falsification before expensive scale-up.

Default first wave:

1. dense baseline/scaling;
2. retrieval/context ladder;
3. test-time scaling matrix;
4. memory belief-revision/prospective-memory protocols;
5. tool metadata adversary;
6. serving crossover;
7. optimizer geometry;
8. synthetic-data factorial;
9. monitorability drift;
10. research-agent anti-cheating.

Expensive Track AC/AA candidates wait until applicable foundation/eval/manifest gates exist.

**Exit gate for AD:** every major Skeleton subsystem is connected to current research evidence, counterevidence, verified source status, a scoped conclusion, and an explicit local experiment; uncertainty and negative results remain visible; research can refresh quickly without directly changing production authority.

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

This ordering is adversarially revised: **P0 foundations precede exotic optimization or architecture promotion**.

1. ✅ Repair the architecture index so base + rounds 3–22 are visible.
2. ✅ Add a canonical human architecture index.
3. ✅ Add the research/evidence/evolution construction contract.
4. ✅ Add the hostile masterplan gap audit and machine hardening checkpoint.
5. ⬜ AB1–AB4: representation identity, data lineage, unified model artifact and state/schema migration contracts.
6. ⬜ AB5–AB10: evaluation firewall, principals/tenancy, sandbox, supply chain, storage semantics, leases/fencing/ordering.
7. ⬜ AB11–AB20: secret lifecycle, DR, control-plane reserve, config snapshots, side-effect reconciliation, deletion, poisoning, safe loading, tamper-evident audit, safe mode.
8. ⬜ AB21–AB36: resource/backpressure, observability integrity, compatibility, structured decoding, uncertainty, cache/event semantics, multi-agent containment, provenance, numeric IR, capacity/cost, parser bounds, cancellation, semantic drift/ABI, historical restore, trust-root bootstrap.
9. ⬜ AB37–AB39: combined fault campaigns plus residual race/boundary and systemic lifecycle/recovery closure.
10. ⬜ Implement ResearchEvidence and experiment-manifest schemas.
11. ⬜ Add source/version/provenance adapters.
12. ⬜ Build the claim/evidence graph and evidence maturity engine.
13. ⬜ Bind research candidates into the existing absorption/challenge fabric.
14. ⬜ Establish evaluation registry + immutable experiment evidence bundles behind the AB5 firewall.
15. ⬜ Implement ModelPort v1 against AB1/AB3/AB23/AB30 contracts.
16. ⬜ Implement reasoning-budget contracts and calibrated uncertainty/abstention.
17. ⬜ Implement trust labels and canonical tool transactions on top of AB6/AB7/AB15/AB33.
18. ⬜ Implement hierarchical context/memory compiler with AB16/AB26/AB29 deletion, isolation and provenance semantics.
19. ⬜ Implement serving scheduler/KV abstraction and hardware profiles with control-plane reserve/backpressure.
20. ⬜ Implement controlled adaptation lanes with data/eval/trust boundaries.
21. ⬜ Implement shadow/canary/rollback scientific promotion with state-compatible rollback.
22. ⬜ Add continuous evidence refresh and architecture-deprecation machinery.
23. ⬜ Implement optimizer contract, stable baseline adapters and ParameterOptimizationMap.
24. ⬜ Add optimizer flight recorder, numerical circuit breakers and atomic optimizer checkpoint binding.
25. 🧪 Run optimizer challengers through equal-token/equal-wall-clock gates.
26. 🧪 Build Track AA forks for sparse attention, hybrid blocks, MoE, long context, low precision and distributed/serving step changes.
27. 🧪 Establish Track AC ExoticCandidate harnesses and reproduce Tier E1 candidates independently.
28. 🧪 Run Tier E2/E3 exotic candidates only inside bounded sandboxes with explicit kill criteria.
29. 🔨 Establish Track AD research saturation: normalize priority sources, verify source/venue status, seed ResearchQuestion records, and bind every research family to reproduction/counterevidence.
30. 🧪 Execute the AD high-information experiment queue plus FD001–FD021 source-verified frontier-delta experiments before expensive full-scale architecture commitments.
31. ⬜ Instantiate RXP001–RXP035 experiment manifests and execute the first-wave protocols in evidence-value order.
32. ⬜ Close or explicitly scope material RDE research debt and resolve/document CX contradictions before default promotion.
33. ⬜ Bind every AB/Z/AA/AC/AD validated or promoted state to timestamped evidence and signed artifact/ADR digests.

Parallel research is allowed where isolation is real. Production-readiness gates are not bypassed to gain speed.

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
