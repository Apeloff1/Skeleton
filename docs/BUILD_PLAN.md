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
Introduce monotonic local deadlines, lease epochs, fencing tokens, sequence/correlation/causation IDs and explicit dedupe windows.
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

### AB36. Trust-root bootstrap — ⬜
Boot verifies keys, policy roots, manifests and trusted code before loading mutable models/plugins/policies.

### AB37. Combined fault campaigns — ⬜
Run the audit matrix across state, network, worker, artifact, authority, resource and observability axes.

Requirements:
- every P0 path: all single-axis faults;
- every P0 side effect: pairwise state × network × authority;
- promotion/rollback: state × artifact × observability;
- distributed training/serving: network × worker × resource;
- periodic selected three-axis campaigns.

**Exit gate for AB:** every P0 audit finding has a canonical contract, owner, machine invariant, tests, fault injection, observability, recovery semantics and signed evidence. No subsystem with an applicable open P0 may claim production-grade status.

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
9. ⬜ AB37: combined single-, pairwise- and selected three-axis fault campaigns.
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
27. ⬜ Bind every AB/Z/AA validated or promoted state to timestamped evidence and signed artifact/ADR digests.

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
