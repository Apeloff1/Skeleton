# Skeleton Frontier Research Atlas — 2026-09-21

Status: canonical research synthesis input
Date frozen: 2026-09-21
Scope: architecture, training, data, reasoning, memory, agents, serving, multimodality, evaluation, safety, interpretability, formal methods, hardware, and research automation

This document is a **research synthesis layer**, not a production architecture declaration.

Its purpose is to answer four questions for every major frontier:

1. What does the strongest currently available evidence actually support?
2. What remains uncertain, contradictory, or scale-dependent?
3. Which Skeleton contract or experiment should absorb the result?
4. What evidence would falsify or materially revise the current conclusion?

The canonical machinery for promotion remains:

```text
source
 -> ResearchEvidence
 -> claim graph
 -> local reproduction
 -> baseline
 -> ablation
 -> adversarial/system challenge
 -> ADR
 -> shadow
 -> canary
 -> promoted state
```

No paper, laboratory, benchmark, model card, leaderboard, or research agent bypasses that path.

---

# 1. Evidence interpretation

## 1.1 Source classes

Use these source classes separately from confidence:

- **FOUNDATIONAL** — long-lived result with broad independent reuse.
- **PEER_REVIEWED** — accepted conference/journal work with a stable venue record.
- **OFFICIAL_SYSTEM_EVIDENCE** — deployment/system-card/engineering evidence from an organization operating the system.
- **REPLICATED_FRONTIER** — recent result with independent or multi-scale corroboration.
- **FRONTIER_PREPRINT** — strong recent preprint requiring local replication.
- **WORKSHOP/EMERGING** — useful signal; insufficient for default architecture.
- **SURVEY/SYNTHESIS** — useful for taxonomy; does not itself establish every cited claim.
- **NEGATIVE/COUNTEREVIDENCE** — failed reproduction, null result, limitation, attack, or counterexample.

A venue label does not override experimental scope.

## 1.2 Confidence dimensions

Every conclusion in this atlas separates:

- **mechanism confidence** — evidence that the claimed mechanism exists;
- **scale-transfer confidence** — evidence it survives larger models/tokens/hardware;
- **systems confidence** — evidence theoretical gains become wall-clock/cost gains;
- **portability confidence** — evidence it survives hardware/model-family changes;
- **production confidence** — evidence it remains reliable under failures, concurrency, security boundaries, and recovery.

## 1.3 Status vocabulary

- **ADOPT CONTRACT** — make the interface/measurement permanent.
- **BUILD BASELINE** — implement a stable reference.
- **REPRODUCE** — local reproduction is justified.
- **CHALLENGER** — controlled experiment lane.
- **WATCH** — monitor research; implementation not yet justified.
- **NEGATIVE GUARDRAIL** — preserve as a permanent test/failure case.
- **DO NOT GENERALIZE** — result is real in scope but cannot support a wider claim.

---

# 2. Executive research synthesis

The current frontier does **not** support one universal winning model architecture, optimizer, memory system, reasoning method, serving topology, or agent scaffold.

The strongest cross-domain conclusions are:

### FR001 — Full-system evidence beats isolated benchmark evidence
**Status:** ADOPT CONTRACT
**Confidence:** very high

Many recent gains are highly conditional on hardware, batch size, context distribution, task family, verifier quality, or serving topology. Skeleton should therefore optimize **successful task utility under declared constraints**, not benchmark rank.

Permanent implication:

```text
candidate result
 != isolated metric
 == quality + cost + latency + memory + failure + recovery + security + portability
```

### FR002 — Architecture modularity is more durable than architecture selection
**Status:** ADOPT CONTRACT
**Confidence:** high

Dense Transformers remain strong, while SSMs, recurrent-depth models, sparse attention, MoE, diffusion generation, byte-latent models, and neural-memory systems each occupy different Pareto regions. The stable asset is ModelPort + artifact/eval contracts, not a frozen model family.

### FR003 — Research refresh must be continuous
**Status:** ADOPT CONTRACT
**Confidence:** very high

2025–2026 work is moving simultaneously in training algorithms, serving topology, reasoning protocols, data synthesis, memory and agent evaluation. A static "SOTA list" becomes stale too quickly.

### FR004 — Negative evidence is first-class architecture input
**Status:** ADOPT CONTRACT
**Confidence:** very high

Examples include synthetic-data collapse, RAG-vs-long-context task dependence, agent failures at long horizons, judge/verifier failure, sparse methods whose theoretical FLOP savings fail to become wall-clock gains, and safety monitors that may not generalize.

### FR005 — Reproducibility must include the inference protocol
**Status:** ADOPT CONTRACT
**Confidence:** high

For reasoning systems, the evaluated object is increasingly:

```text
model
+ prompt/system state
+ sampling/search algorithm
+ verifier/reward model
+ tool/environment
+ stopping rule
+ compute budget
```

Reporting only the base model and benchmark is inadequate.

---

# 3. Model architecture and sequence substrate

## FR006 — Dense attention remains the reference architecture
**Status:** BUILD BASELINE
**Evidence maturity:** FOUNDATIONAL
**Confidence:** very high

Dense Transformer attention remains the indispensable reference for quality, optimization maturity, kernel support and portability.

Skeleton implication:

- never delete the dense baseline;
- all sparse/recurrent/hybrid alternatives must compare against a tuned dense implementation;
- dense fallback remains valuable for debug, verification and portability.

## FR007 — Sparse attention is now a serious training-time architecture, not only inference compression
**Status:** CHALLENGER
**Evidence:** Native Sparse Attention, arXiv:2502.11089
**Confidence:** medium-high

NSA is important because it co-designs:

- trainable sparsity;
- token compression;
- token selection;
- hardware arithmetic intensity;
- forward/backward/decode efficiency.

Research conclusion:

Sparse attention deserves a first-class model-family adapter, but Skeleton must measure:

- full training wall-clock;
- long-context quality;
- sparse-kernel portability;
- route/selection instability;
- adversarially important low-salience tokens;
- dense fallback behavior.

## FR008 — Long-context architecture cannot be reduced to attention complexity
**Status:** ADOPT CONTRACT
**Confidence:** high

Useful long context also depends on:

- positional behavior;
- data curriculum;
- sequence parallelism;
- memory pressure;
- KV lifecycle;
- retrieval strategy;
- distraction resistance;
- serving network topology.

Therefore "supports 1M context" is not a ModelPort boolean.

## FR009 — SSM/recurrent substrates remain architecturally relevant
**Status:** CHALLENGER
**Evidence:** Mamba; Jamba; *To Infinity and Beyond: Tool-Use Unlocks Length Generalization in State Space Models* (ICLR 2026 Oral; OpenReview sSfep4udCb)
**Confidence:** medium-high

SSM/recurrent models can provide:

- bounded recurrent state;
- streaming efficiency;
- different long-context scaling;
- architectural diversity from attention.

Open question:

Does tool use / external computation change the effective length-generalization frontier enough that SSMs become particularly attractive for agents?

Required local experiment:

- same training budget;
- same tool API;
- length extrapolation;
- tool-assisted vs tool-disabled;
- streaming latency;
- recurrent-state reset/recovery.

## FR010 — Hybrid architecture should be treated as normal, not exceptional
**Status:** ADOPT CONTRACT
**Confidence:** high

The evidence trend supports composition:

- attention + SSM;
- dense + MoE;
- local + global attention;
- recurrent + attention;
- sparse + dense fallback.

Skeleton should make block topology explicit in the artifact manifest while hiding it behind ModelPort.

## FR011 — MoE remains a systems problem as much as a modeling problem
**Status:** CHALLENGER
**Evidence:** DeepSeekMoE; MegaBlocks; subsequent expert-parallel systems
**Confidence:** high

Research questions that matter more than nominal parameter count:

- active parameters/token;
- expert utilization;
- router entropy;
- hot expert concentration;
- all-to-all volume;
- expert placement;
- capacity/drop policy;
- fault domain;
- checkpoint sharding.

Permanent rule:

System/provider routing and model-internal expert routing remain separate abstractions.

## FR012 — Conditional depth is a plausible compute-allocation primitive
**Status:** REPRODUCE
**Evidence:** Mixture-of-Depths, arXiv:2404.02258
**Confidence:** medium

Potential benefit:

Allocate layer compute by token importance rather than uniformly.

Main risks:

- router errors on rare crucial tokens;
- quality tails hidden by average loss;
- kernel/scheduler fragmentation;
- route instability under distribution shift.

Skeleton experiment:

Compare conditional depth against:

- smaller dense model;
- early exit;
- MoE;
- recurrent depth;
- test-time search.

Use equal wall-clock and equal FLOPs separately.

## FR013 — Recurrent latent depth turns test-time compute into an architectural degree of freedom
**Status:** REPRODUCE
**Evidence:** recurrent-depth work arXiv:2502.05171; Universal YOCO arXiv:2604.01220
**Confidence:** medium

This is qualitatively different from producing longer chain-of-thought.

Required measurements:

- accuracy vs recurrence;
- latency vs recurrence;
- recurrence allocation by task difficulty;
- overthinking degradation;
- state convergence/oscillation;
- KV/state footprint;
- self-speculation compatibility.

## FR014 — Equilibrium/fixed-point language computation is promising but convergence is the product
**Status:** WATCH/REPRODUCE SMALL
**Evidence:** *Equilibrium Language Models*, OpenReview:lqJT6xmuH3. The research-status audit treats the currently verified under-review copy as emerging evidence unless/until venue acceptance is independently confirmed.
**Confidence:** low-medium

Do not evaluate only final quality.

Measure:

- convergence probability;
- iterations distribution;
- tail iterations;
- non-convergence cases;
- low-precision effects;
- implicit-gradient correctness;
- fallback cost.

## FR015 — Differential attention deserves a noise-suppression experiment, not a default
**Status:** REPRODUCE
**Evidence:** Differential Transformer, arXiv:2410.05258
**Confidence:** medium

The interesting hypothesis is not "new attention is better"; it is:

> explicit subtraction can suppress common-mode irrelevant context and activation outliers.

Test with:

- distractor-heavy retrieval;
- prompt injection;
- repeated near-duplicates;
- extremely long irrelevant prefixes;
- low precision.

---

# 4. Representation and tokenization

## FR016 — Fixed subword tokenization is no longer a safe architectural assumption
**Status:** ADOPT CONTRACT
**Evidence:** Byte Latent Transformer, arXiv:2412.09871
**Confidence:** medium-high for research relevance

BLT-style dynamic byte patches suggest that representation and compute allocation can be coupled.

Skeleton implication:

RepresentationSpec must support:

- fixed vocabulary;
- raw bytes;
- dynamic patching;
- continuous latents;
- modality-specific encodings.

## FR017 — Tokenizer-free does not mean representation-free
**Status:** NEGATIVE GUARDRAIL
**Confidence:** very high

Byte-native systems still require contracts for:

- normalization;
- malformed bytes;
- segmentation/patch boundaries;
- cache identity;
- sequence length accounting;
- structured outputs;
- speculative compatibility.

## FR018 — Representation migrations are model migrations
**Status:** ADOPT CONTRACT
**Confidence:** high

Changing vocabulary/patching affects:

- embeddings;
- output heads;
- training data;
- cache keys;
- adapters;
- speculative models;
- evaluation comparability.

Therefore representation identity is part of ModelArtifactManifest.

---

# 5. Neural memory, external memory and retrieval

## FR019 — Test-time neural memory is a genuine new model-state family
**Status:** REPRODUCE
**Evidence:** Titans arXiv:2501.00663; MIRAS arXiv:2504.13173; 2026 memory follow-up work on OMEGANET/ATLAS
**Confidence:** medium-high

Potential advantage:

A bounded memory module can update from active context instead of storing every token.

Main research risks:

- interference;
- poisoning;
- hidden state drift;
- replay mismatch;
- cross-session leakage;
- inability to preserve provenance.

Skeleton rule:

Model-internal neural memory is **not** durable trusted memory.

## FR020 — Memory management itself is an optimizer problem
**Status:** RESEARCH HYPOTHESIS
**Confidence:** medium

MIRAS-family work reframes recurrent/neural memory using:

- an internal objective;
- retention rules;
- online optimization;
- memory architecture capacity.

This creates a new research dimension:

```text
memory representation
x memory objective
x update optimizer
x retention policy
```

Track Z and AC should share instrumentation here.

## FR021 — Agent memory needs belief revision, not append-only retrieval
**Status:** RESEARCH PRIORITY
**Evidence:** ICLR 2026 MemAgent work and related belief-engine proposals
**Confidence:** medium

Common memory systems retrieve old experiences but often lack principled mechanisms for:

- contradiction;
- correction;
- evidence weighting;
- supersession;
- uncertainty.

Skeleton semantic memory should therefore support:

```text
claim
 + source
 + version
 + confidence
 + contradictions
 + supersedes
 + retraction
```

not only vector chunks.

## FR022 — Multi-granularity memory is credible
**Status:** REPRODUCE
**Evidence:** MemGAS, ICLR 2026 poster
**Confidence:** medium-high

Queries may require:

- exact episode;
- summarized episode;
- thematic cluster;
- user/session-level pattern.

One fixed chunk size is unlikely to dominate.

## FR023 — Conversational memory and document reasoning are a joint retrieval problem
**Status:** BUILD EVAL
**Evidence:** MemoryDocDataSet, arXiv:2606.04442
**Confidence:** medium

A realistic system may need:

conversation -> identify document -> retrieve document evidence -> answer.

Separate memory/document retrieval scores can miss this composition failure.

## FR024 — RAG vs long context has no universal winner
**Status:** NEGATIVE GUARDRAIL
**Evidence:** LaRA, arXiv:2502.09977
**Confidence:** high

Routing depends on:

- model;
- task;
- context length;
- retrieval quality;
- chunk characteristics;
- latency/cost.

Therefore Track T should learn/benchmark routing rather than hard-code RAG or full-context preference.

## FR025 — Retrieval confidence must include retrieval failure modes
**Status:** ADOPT CONTRACT
**Confidence:** high

Track:

- miss;
- false positive;
- source conflict;
- stale source;
- unsupported answer;
- encoder/index version mismatch;
- long-context distraction after retrieval.

---

# 6. Training data and mixture research

## FR026 — Data mixture optimization is a genuine optimization problem
**Status:** REPRODUCE
**Evidence:** Data Mixture Optimization, NeurIPS 2025, OpenReview:Kvsa8ZXd0W
**Confidence:** medium-high

Multi-fidelity/multi-scale experimentation can reduce the cost of searching domain mixtures.

Skeleton implication:

Data mixture belongs in the experiment registry with:

- mixture vector;
- model scale;
- training steps;
- downstream metric vector;
- uncertainty;
- transfer-to-scale evidence.

## FR027 — Data quality and diversity are not interchangeable
**Status:** ADOPT CONTRACT
**Confidence:** high

Aggressive quality filtering can:

- increase token efficiency;
- reduce long-tail coverage;
- shrink total corpus;
- alter domain distribution.

Track W must record both quality signals and coverage/diversity.

## FR028 — Synthetic data is conditional, not universally beneficial
**Status:** NEGATIVE GUARDRAIL + CHALLENGER
**Evidence:** ToEdit / model-collapse work; Synthetic Bootstrapped Pretraining ICLR 2026; DATA-FM synthesis literature
**Confidence:** high that effects are conditional

Supported synthesis:

- synthetic data can help in verifiable or targeted domains;
- naive synthetic replacement can reduce diversity/coverage;
- fully synthetic pretraining may inherit teacher limitations;
- anchored/edited/bootstrapped generation can behave differently from unconstrained model-generated corpora.

Permanent data fields:

- generator model/version;
- generation prompt/policy;
- seed/source ancestry;
- verifier;
- synthetic ancestry depth;
- real-data anchor ratio;
- diversity metrics;
- downstream drift.

## FR029 — Synthetic-data compute can become a first-order training cost
**Status:** ADOPT MEASUREMENT
**Confidence:** medium-high

Do not report only final training FLOPs.

Include:

- generation compute;
- judge/verifier compute;
- filtering;
- transformation;
- deduplication;
- storage;
- regeneration cost.

## FR030 — Programmatically verifiable synthetic data is especially attractive
**Status:** CHALLENGER
**Confidence:** high

Code, math, tools and formal domains offer deterministic/strong external verification.

Skeleton should prioritize synthetic experiments where labels can be independently checked.

## FR031 — Synthetic-data ancestry must be acyclic and observable
**Status:** ADOPT CONTRACT
**Confidence:** high

Track:

```text
human/source document
 -> teacher A
 -> synthetic corpus v1
 -> student B
 -> generated corpus v2
 -> student C
```

This is required to detect self-distillation loops and coverage collapse.

## FR032 — Multilingual mixture conclusions remain scale- and dataset-dependent
**Status:** WATCH
**Evidence:** 2026 multilingual mixture work, OpenReview:IKJyRyHpHV (rejected submission)
**Confidence:** low-medium

Useful signal:

absolute quantity and quality of low-resource-language data may matter more than simplistic percentage balancing.

But Skeleton must not promote this as a large-scale law without stronger replication.

---

# 7. Optimization and numerical training

## FR033 — AdamW remains the indispensable training reference
**Status:** BUILD BASELINE
**Confidence:** very high

Every optimizer challenger should compare to a properly tuned AdamW baseline.

## FR034 — Muon/SOAP-class optimizers now have stronger large-scale evidence
**Status:** HIGH-PRIORITY CHALLENGER
**Evidence:** SOAP, Muon, and Beyond, arXiv:2607.20548
**Confidence:** medium-high

Important 2026 evidence includes:

- multi-billion-parameter scale;
- trillion-token regimes;
- large batch behavior;
- explicit stability issues;
- distributed optimizer implementation;
- fairer update-RMS matching.

Skeleton experiments should reproduce:

- update-RMS matching;
- loss spikes;
- orthogonalization quality;
- batch scaling;
- communication hiding;
- layerwise distributed state.

## FR035 — Optimizer comparisons without update-scale normalization are suspect
**Status:** ADOPT EXPERIMENT RULE
**Confidence:** medium-high

Learning-rate semantics differ across optimizer geometries.

Record:

- raw LR;
- update RMS;
- update/weight ratio;
- per-layer update norm;
- effective trust ratio.

## FR036 — Low-rank optimizer state is an active frontier
**Status:** CHALLENGER
**Evidence:** GaLore; ICLR 2026 LoRA-Pre
**Confidence:** medium

Measure whether memory reduction merely moves cost into:

- reconstruction;
- QR/SVD;
- communication;
- instability;
- extra steps.

## FR037 — Minimalist optimizers deserve skeptical replication
**Status:** WATCH/REPRODUCE SMALL
**Evidence:** SCALE ICLR 2026 submission; related memory-efficient optimizer work
**Confidence:** low-medium

Interesting hypothesis:

much of Adam's state may not be essential if normalization and selected momentum are used strategically.

Do not generalize from small scales until larger-token replications exist.

## FR038 — Precision is part of the optimizer
**Status:** ADOPT CONTRACT
**Confidence:** high

Optimizer state precision, accumulation precision, stochastic rounding, scaling and outlier policy can change training stability.

## FR039 — Long-horizon low-precision validation is mandatory
**Status:** NEGATIVE GUARDRAIL
**Evidence:** FP8 trillion-token research and FP4 frontier work
**Confidence:** high

A method that survives a short run can still fail at trillion-token horizon.

---

# 8. Test-time reasoning and verification

## FR040 — "Test-time compute" is not one algorithm
**Status:** ADOPT CONTRACT
**Evidence:** arXiv:2608.04001 and broader TTS literature
**Confidence:** high

At minimum distinguish:

- sequential single trajectory;
- independent completed samples + aggregation;
- prefix/tree search;
- verifier-guided search;
- tool-assisted exploration;
- latent recurrent compute.

Each has different cost and failure semantics.

## FR041 — The inference protocol is the evaluated system
**Status:** ADOPT CONTRACT
**Confidence:** very high

An eval record needs:

- base model;
- prompts/system instructions;
- decoding;
- sample count;
- branching;
- verifier;
- reduction rule;
- stopping;
- total tokens/FLOPs/time;
- tool calls.

## FR042 — No test-time scaling strategy universally dominates
**Status:** NEGATIVE GUARDRAIL
**Evidence:** 2025–2026 comparative TTS literature
**Confidence:** medium-high

Optimal method depends on:

- model;
- task difficulty;
- verifier quality;
- compute budget.

ReasoningBudgetAllocator must therefore be adaptive.

## FR043 — Reward-tail structure may help compute allocation
**Status:** REPRODUCE
**Evidence:** arXiv:2602.01485
**Confidence:** medium

Potential use:

Estimate whether additional candidates/search are likely to improve the best result before spending the full budget.

Risk:

reward-model tail estimates can be wrong or exploited.

## FR044 — Process reward models are becoming generative reasoners
**Status:** CHALLENGER
**Evidence:** GenPRM arXiv:2504.00891
**Confidence:** medium

Rather than scalar judging only, verifiers may:

- reason;
- call deterministic checks;
- generate critiques.

This increases capability but also correlated-error and cost risks.

## FR045 — Verifier training recipe is scale-dependent
**Status:** RESEARCH PRIORITY
**Evidence:** Aletheia, ACL ARR 2026
**Confidence:** medium

Reported finding:

different components such as on-policy training, negative samples and reasoning traces matter differently by verifier scale.

Skeleton implication:

Verifier registry needs training recipe/version, not only model id.

## FR046 — Verifier independence must be measured, not counted
**Status:** ADOPT CONTRACT
**Confidence:** very high

Five judges trained from the same base model/data are not five independent verifiers.

Record independence axes:

- model family;
- training data;
- provider;
- evidence;
- algorithm;
- deterministic vs learned.

## FR047 — Formal/execution feedback remains the strongest verifier where available
**Status:** ADOPT CONTRACT
**Evidence:** code execution, Lean, model checking, theorem-prover systems
**Confidence:** very high

Prefer:

formal checker > deterministic execution > schema/property checker > learned judge

when the stronger mechanism covers the claim.

---

# 9. Formal reasoning and proof

## FR048 — Formal verifier loops are a strong pattern for high-stakes reasoning
**Status:** BUILD OPTIONAL VERIFIER ADAPTERS
**Evidence:** Goedel-Prover-V2 arXiv:2508.03613; Leanabell-Prover-V2 arXiv:2507.08649; Hilbert arXiv:2509.22819
**Confidence:** high in theorem-proving scope

Architecture pattern:

```text
informal reasoner
 -> formalization/prover
 -> deterministic verifier
 -> counterexample/error
 -> repair
```

Skeleton should generalize the pattern beyond mathematics where possible.

## FR049 — Natural-language reasoning and formal verification are complementary
**Status:** ADOPT DESIGN PRINCIPLE
**Confidence:** high

Formal systems give exact verification but often lack flexible problem decomposition.

LLMs can propose/decompose; formal engines decide validity in their domain.

## FR050 — Autoformalization must preserve semantics, not only syntax
**Status:** NEGATIVE GUARDRAIL
**Evidence:** PAT-Agent and formal-agent research
**Confidence:** high

A formally valid theorem/model can encode the wrong natural-language problem.

Required checks:

- premise equivalence;
- conclusion equivalence;
- assumptions introduced;
- unit/domain constraints.

---

# 10. Agents and long-horizon action

## FR051 — Long-horizon task length is itself a training variable
**Status:** RESEARCH PRIORITY
**Evidence:** ICML 2026 horizon-length study
**Confidence:** medium-high

Agents trained on short horizons cannot be assumed to extrapolate to long workflows.

Evaluation should stratify by:

- actions;
- wall-clock duration;
- environment state changes;
- number of tool domains;
- recovery events.

## FR052 — Agent competence is not reducible to base-model competence
**Status:** ADOPT CONTRACT
**Confidence:** very high

Agent outcome depends on:

- planner;
- memory;
- tool descriptions;
- action schema;
- environment;
- retry/recovery;
- horizon;
- state representation.

## FR053 — Tool descriptions are an attack surface
**Status:** NEGATIVE GUARDRAIL
**Evidence:** ToolTweak, ICLR 2026 submission
**Confidence:** medium

A model can be biased toward a tool through manipulated names/descriptions.

Skeleton implications:

- separate tool discovery ranking from tool authority;
- normalize descriptions where possible;
- functional equivalence testing;
- monitor provider/tool-selection skew.

## FR054 — Deterministic retrieval layers can sharply improve scientific agents
**Status:** ADOPT DESIGN PRINCIPLE
**Evidence:** Anthropic 2026 biology-agent study
**Confidence:** medium-high

For structured scientific databases, deterministic adapters can outperform free-form navigation and substantially reduce extraction errors.

## FR055 — Current autonomous research agents remain brittle on realistic implementation
**Status:** NEGATIVE GUARDRAIL
**Evidence:** RExBench negative results; FIRE-Bench; scientific-agent research
**Confidence:** medium

Do not equate:

paper-summary ability
with
independent research implementation.

Evaluation needs:

- hypothesis;
- code;
- experiment;
- debugging;
- result interpretation;
- reproducibility.

## FR056 — Scientific agents need structured execution state
**Status:** RESEARCH PRIORITY
**Evidence:** El Agente Gráfico and related scientific-agent work
**Confidence:** medium

Research workflows benefit from:

- execution DAGs/graphs;
- typed dependencies;
- artifact edges;
- evidence links;
- retryable nodes;
- provenance.

This aligns strongly with Skeleton's receipt/evidence architecture.

## FR057 — Computer-use evaluation must remain execution-grounded
**Status:** ADOPT EVAL PRINCIPLE
**Evidence:** OSWorld; GUI-360; newer GUI-agent research
**Confidence:** high

Screenshot/text similarity is insufficient.

Prefer state-based success predicates whenever available.

## FR058 — Long-horizon software benchmarks should be separate from snippet coding
**Status:** ADOPT EVAL FAMILY
**Evidence:** SWE-bench; SWE-Bench Pro
**Confidence:** high

Measure:

- repository navigation;
- build/test loops;
- multi-file edits;
- regression avoidance;
- persistence over long task state.

---

# 11. Agent memory and procedural learning

## FR059 — Procedural memory is distinct from semantic memory
**Status:** ADOPT CONTRACT
**Confidence:** high

Store:

- successful tool workflows;
- prerequisites;
- failure signatures;
- recovery paths;
- environment/version compatibility.

Do not store arbitrary successful trajectories as trusted procedure without verification.

## FR060 — Memory writes need a promotion gate
**Status:** ADOPT CONTRACT
**Confidence:** very high

A successful outcome does not prove every intermediate step was good.

Procedure promotion should require:

- outcome;
- causality/ablation where practical;
- safety;
- current compatibility;
- dedupe/generalization.

## FR061 — Memory retrieval should expose granularity and source selection
**Status:** REPRODUCE
**Confidence:** medium-high

One retrieval function over one flat memory pool hides important decisions.

Expose:

- source class;
- granularity;
- time range;
- confidence;
- trust.

---

# 12. Serving and inference systems

## FR062 — KV cache is now a distributed systems object
**Status:** ADOPT CONTRACT
**Confidence:** very high

KV decisions affect:

- HBM;
- host memory;
- network;
- prefix reuse;
- prefill/decode placement;
- latency;
- fairness;
- quality if compression is lossy.

## FR063 — Disaggregated prefill/decode is valuable but network-limited
**Status:** HIGH-PRIORITY CHALLENGER
**Evidence:** P/D-Serve; SmartGen arXiv:2607.28150; load-aware prefill deflection arXiv:2607.02043; NetKV arXiv:2606.03910
**Confidence:** high that topology matters

Research conclusion:

The scheduler needs a **network cost model**, not only GPU utilization.

Inputs:

- KV bytes;
- route bandwidth;
- congestion;
- locality;
- queue;
- prefix hit;
- decode SLO.

## FR064 — KV transfer can dominate TTFT
**Status:** ADOPT MEASUREMENT
**Confidence:** high

Measure TTFT decomposition:

```text
queue
+ prefill compute
+ KV movement
+ decode admission
+ first decode
```

## FR065 — Decode nodes can sometimes absorb prefill work
**Status:** REPRODUCE
**Evidence:** 2026 load-aware prefill deflection
**Confidence:** medium

Potentially useful under asymmetric burst load.

Need guardrails for time-between-token SLOs.

## FR066 — KV selection/compression/eviction should be jointly optimized
**Status:** CHALLENGER
**Evidence:** EVICPRESS arXiv:2512.14946; broader KV literature
**Confidence:** medium-high

Independent compression and eviction policies can be globally suboptimal.

## FR067 — Output-length uncertainty should enter admission and memory planning
**Status:** CHALLENGER
**Evidence:** robust KV management arXiv:2607.16892
**Confidence:** medium

Do not treat max_tokens as predicted consumption.

Use:

- request class;
- historical distribution;
- uncertainty;
- preemption cost;
- memory cost.

## FR068 — Prefix caching needs fairness protection
**Status:** ADOPT CONTRACT
**Evidence:** distributed prompt scheduling research
**Confidence:** high

Pure locality scheduling can starve low-cache-hit workloads.

Track:

- cache gain;
- wait age;
- tenant fairness;
- SLO class.

## FR069 — Speculation should be measured under real acceptance distributions
**Status:** ADOPT EXPERIMENT RULE
**Confidence:** high

Report:

- draft cost;
- verifier cost;
- acceptance length distribution;
- memory;
- concurrency;
- workload shift.

High isolated acceptance rate is not enough.

---

# 13. Distributed training systems

## FR070 — Extreme-scale training is an observability and fault-recovery problem
**Status:** ADOPT CONTRACT
**Evidence:** MegaScale and large-cluster literature
**Confidence:** high

At scale, include:

- stragglers;
- silent hardware errors;
- collectives;
- filesystem/object-store pressure;
- checkpoint lag;
- restart/repartition cost.

## FR071 — Asynchronous checkpointing is useful only with a declared recovery point
**Status:** CHALLENGER
**Evidence:** DataStates-LLM arXiv:2406.10707
**Confidence:** medium-high

"Checkpoint returned" and "durable recoverable checkpoint" must be different states.

## FR072 — Topology-aware placement should be an optimizer input
**Status:** ADOPT CONTRACT
**Confidence:** high

Parallelism dimensions interact with real:

- NVLink/NVSwitch;
- PCIe;
- NIC;
- rack topology;
- storage;
- heterogeneous GPUs.

## FR073 — Training optimizer and cluster scheduler cannot be completely independent
**Status:** RESEARCH PRIORITY
**Confidence:** medium-high

Higher-order optimizers may change:

- communication;
- memory;
- compute overlap;
- sharding.

The compute planner should model optimizer topology.

---

# 14. Multimodal and world-model research

## FR074 — Multimodal "unification" requires representation contracts
**Status:** ADOPT CONTRACT
**Confidence:** high

Text tokens, image patches, audio frames, continuous latents and actions have different semantics.

Do not hide these differences behind a generic "token" type.

## FR075 — Continuous latent multimodal generation is a credible architecture direction
**Status:** REPRODUCE SMALL
**Evidence:** LatentLM arXiv:2412.08635
**Confidence:** medium

Potential advantage:

one causal backbone can operate over discrete text and continuous modality latents.

Required provenance:

- original modality;
- codec/encoder;
- time/space coordinates;
- transformations.

## FR076 — World models should be treated as predictors, not observations
**Status:** ADOPT AUTHORITY RULE
**Confidence:** very high

Simulated future state remains MODEL_GENERATED.

Tool/environment receipts outrank it.

## FR077 — World-model value depends on action-conditioned predictive calibration
**Status:** BUILD EVAL
**Evidence:** World Action Model literature; 2026 world-model research
**Confidence:** medium

Measure:

- state prediction;
- action consequence prediction;
- uncertainty by rollout horizon;
- counterfactual ranking;
- simulator exploitation.

## FR078 — Current LLMs should not be assumed to possess robust implicit world models
**Status:** NEGATIVE GUARDRAIL
**Evidence:** 2026 grid-world spatial-world-model evaluation
**Confidence:** medium

Good output behavior can be representation/prompt-specific rather than evidence of stable internal simulation.

## FR079 — GUI agents may benefit from learned environment dynamics
**Status:** CHALLENGER
**Evidence:** UI-Oceanus, ACL ARR 2026
**Confidence:** medium

Executed transition prediction is an interesting self-supervised objective because it grounds models in environment changes rather than only demonstration imitation.

---

# 15. Evaluation science

## FR080 — Static public benchmarks are insufficient for frontier claims
**Status:** ADOPT CONTRACT
**Confidence:** very high

Risks:

- contamination;
- saturation;
- prompt overfitting;
- leaderboard optimization;
- answer leakage through tools/retrieval.

## FR081 — Dynamic evaluation is promising but not automatically valid
**Status:** RESEARCH PRIORITY
**Evidence:** 2025 survey on contamination-resistant dynamic benchmarks
**Confidence:** high

A dynamic benchmark still needs:

- reproducible generation;
- difficulty calibration;
- answer validity;
- distribution definition;
- leakage controls.

## FR082 — Blind promotion holdouts need an access budget
**Status:** ADOPT CONTRACT
**Confidence:** high

Repeated architecture search against a hidden set converts it into a training signal.

Track query count and decision use.

## FR083 — Evaluator version is part of the result
**Status:** ADOPT CONTRACT
**Confidence:** very high

LLM judges, reward models and formal tools evolve.

Comparison across versions without re-evaluation is invalid.

## FR084 — Benchmark success should be decomposed by failure class
**Status:** ADOPT CONTRACT
**Confidence:** high

Example categories:

- knowledge miss;
- reasoning error;
- retrieval failure;
- tool failure;
- format failure;
- timeout;
- memory failure;
- security refusal;
- environment mismatch.

## FR085 — Research-agent evaluation needs novelty/implementation checks
**Status:** BUILD EVAL
**Evidence:** FIRE-Bench, RExBench, scientific-agent literature
**Confidence:** medium-high

Research evaluation should distinguish:

- rediscover known result;
- formulate hypothesis;
- implement;
- debug;
- run;
- analyze;
- produce reproducible extension.

---

# 16. Safety, security and monitorability research

## FR086 — Agentic safety must evaluate actions, not only final text
**Status:** ADOPT CONTRACT
**Evidence:** OpenAI agent monitoring work; Anthropic agentic-misalignment simulations
**Confidence:** very high

Monitor:

- code changes;
- tool calls;
- hidden state transitions;
- labels/judgments;
- attempted side effects;
- concealment.

## FR087 — Realistic autonomous-agent simulations are a necessary early-warning tool
**Status:** BUILD EVAL
**Confidence:** high

Use controlled scenarios for:

- sabotage;
- falsification;
- unauthorized disclosure;
- hidden policy circumvention;
- destructive actions;
- covert goal pursuit.

Do not claim these simulations are observed deployment incidence.

## FR088 — CoT monitoring is useful but cannot be the only safeguard
**Status:** ADOPT DEFENSE-IN-DEPTH
**Evidence:** OpenAI 2025–2026 monitorability research
**Confidence:** high

Monitorability may change with:

- scale;
- RL;
- pretraining;
- model awareness;
- reasoning method.

Therefore:

CoT monitor + action monitor + deterministic policy + receipts + post-hoc audit.

## FR089 — Monitorability itself needs monitoring
**Status:** ADOPT EVAL FAMILY
**Confidence:** high

Track whether:

- reasoning visibility changes;
- monitor accuracy changes;
- model can control/obfuscate traces;
- monitor compute keeps up with agent compute.

## FR090 — Learned judges can become motivated or strategically wrong
**Status:** NEGATIVE GUARDRAIL
**Evidence:** 2026 agentic mislabeling research; verifier-gaming literature
**Confidence:** medium-high

Never allow a single learned judge to be authoritative for consequential labels.

## FR091 — Tool selection manipulation belongs in the security threat model
**Status:** BUILD ATTACK SUITE
**Confidence:** medium

Attack vectors:

- tool name;
- description;
- examples;
- ordering;
- metadata;
- provider claims.

## FR092 — Prompt injection remains a cross-plane authority problem
**Status:** ADOPT CONTRACT
**Confidence:** very high

The robust fix is not only a better classifier.

It requires:

- trust labels;
- capability checks;
- untrusted data handling;
- structured tool calls;
- sandboxing;
- least privilege.

## FR093 — Production monitoring is itself research evidence
**Status:** ADOPT CONTRACT
**Evidence:** OpenAI real coding-agent monitoring work
**Confidence:** high

Production observations can generate:

- new evals;
- failure clusters;
- red-team cases;
- calibration updates.

They cannot directly mutate weights/policy.

---

# 17. Interpretability and internal diagnostics

## FR094 — Mechanistic interpretability is becoming more scalable but remains scoped
**Status:** CHALLENGER/DIAGNOSTIC
**Evidence:** CircuitLasso arXiv:2606.16939; 2026 neuron-basis circuit work
**Confidence:** medium

Use interpretability as:

- failure diagnosis;
- hypothesis generation;
- behavioral debugging;
- targeted intervention research.

Do not treat an interpretable feature label as proof of the model's actual reasoning.

## FR095 — SAE features are not automatically the unique correct basis
**Status:** NEGATIVE GUARDRAIL
**Evidence:** arXiv:2601.22594
**Confidence:** medium

Some circuitry may be sparse/useful directly in neuron space.

Skeleton should support multiple interpretability representations.

## FR096 — Counterfactual behavioral prediction is a stronger interpretability test than plausible explanation
**Status:** ADOPT EVAL PRINCIPLE
**Evidence:** Anthropic CHIVE 2026
**Confidence:** medium-high

An explanation/tool is more valuable if it predicts how behavior changes under a targeted intervention.

## FR097 — Interpretability tools need usefulness evals
**Status:** ADOPT CONTRACT
**Confidence:** high

Measure whether they improve:

- prediction;
- debugging;
- monitoring;
- intervention selection.

Do not count attractive visualizations alone.

---

# 18. Calibration, uncertainty and abstention

## FR098 — Agentic confidence is trajectory-level
**Status:** RESEARCH PRIORITY
**Evidence:** 2026 Agentic Confidence Calibration work
**Confidence:** medium

Final-answer confidence can miss:

- early wrong tool result;
- environment uncertainty;
- plan drift;
- recovery failure.

Collect process features across the trajectory.

## FR099 — Uncertainty has multiple sources
**Status:** ADOPT CONTRACT
**Confidence:** very high

Separate:

- epistemic/model uncertainty;
- retrieval uncertainty;
- environment/tool uncertainty;
- verifier disagreement;
- missing evidence;
- OOD novelty;
- execution uncertainty.

## FR100 — Abstention should be an explicit policy output
**Status:** ADOPT CONTRACT
**Confidence:** high

Possible actions:

- answer;
- retrieve;
- ask;
- tool;
- verify;
- escalate;
- abstain.

Confidence does not itself decide authority.

---

# 19. Continual learning and adaptation

## FR101 — Live weight updates remain too dangerous as a default production adaptation path
**Status:** NEGATIVE GUARDRAIL
**Confidence:** very high

Risks:

- poisoning;
- forgetting;
- irreproducibility;
- rollback failure;
- hidden distribution shift.

Keep fast/medium/slow adaptation separation.

## FR102 — External memory is the safest first adaptation surface
**Status:** ADOPT DESIGN PRINCIPLE
**Confidence:** high

Because it is:

- inspectable;
- deletable;
- versioned;
- reversible;
- attributable.

But it still needs belief revision and promotion gates.

## FR103 — Adapter-based adaptation is easier to isolate than base-weight mutation
**Status:** BUILD BASELINE
**Confidence:** high

Still require:

- parent artifact;
- training data lineage;
- eval;
- merge/unmerge semantics.

## FR104 — Inference-time fast weights need stricter isolation than ordinary memory
**Status:** RESEARCH ONLY
**Confidence:** high

They can change behavior without obvious textual memory state.

Require request/session binding and deterministic reset.

---

# 20. Hardware, precision and efficiency

## FR105 — Hardware-aware research is mandatory
**Status:** ADOPT CONTRACT
**Confidence:** very high

The same algorithm can reverse ranking across:

- GPU generations;
- CPU;
- NPU;
- interconnects;
- memory bandwidth;
- batch sizes.

Every systems claim names hardware.

## FR106 — Theoretical sparsity is not realized sparsity
**Status:** NEGATIVE GUARDRAIL
**Confidence:** very high

Sparse methods need:

- actual kernel support;
- occupancy;
- memory traffic;
- indexing/routing overhead;
- load balance.

## FR107 — Native ternary models deserve architecture-level experiments
**Status:** CHALLENGER
**Evidence:** BitNet b1.58 and later low-bit work
**Confidence:** medium-high

Important distinction:

native low-bit training
!= post-training quantization.

## FR108 — Sparse + ternary is a compound hypothesis
**Status:** REPRODUCE WITH ABLATION
**Evidence:** Sparse-BitNet frontier research
**Confidence:** emerging

Require:

- ternary only;
- sparsity only;
- combined;
- same kernel maturity;
- same quality target.

## FR109 — Low precision can alter the failure distribution, not only average error
**Status:** ADOPT TEST RULE
**Confidence:** high

Test:

- outliers;
- rare layers;
- long training;
- resume;
- optimizer moments;
- collective reduction.

---

# 21. Research automation and AI-for-research

## FR110 — AI research automation is real but highly uneven by stage
**Status:** BUILD EVAL, NOT AUTONOMY CLAIM
**Confidence:** high

Models can accelerate:

- literature navigation;
- coding;
- analysis;
- experiment generation.

But realistic research extension remains difficult.

## FR111 — Research-agent benchmarks should distinguish rediscovery from novel extension
**Status:** ADOPT EVAL PRINCIPLE
**Confidence:** high

A system can rediscover a known relation without being able to:

- propose a useful novel modification;
- implement it;
- run valid experiments;
- diagnose failure.

## FR112 — Research agents require contamination-resistant tasks
**Status:** ADOPT CONTRACT
**Confidence:** high

Use:

- post-training-date tasks;
- private/held-out modifications;
- synthetic-but-expert-validated research extensions;
- executable checks.

## FR113 — Research-agent implementation ability is a bottleneck
**Status:** RESEARCH PRIORITY
**Evidence:** RExBench and "AI scientists fail without strong implementation capability" line of work
**Confidence:** medium-high

Skeleton's research agent should explicitly separate:

```text
literature
 -> hypothesis
 -> design
 -> implementation
 -> execution
 -> analysis
 -> replication
```

and score each stage.

## FR114 — Scientific research should keep deterministic domain tools close
**Status:** ADOPT DESIGN PRINCIPLE
**Confidence:** high

Database/search/math/formal/simulation adapters can dramatically reduce free-form agent errors.

---

# 22. Cross-domain contradictions and unresolved questions

## RQ001 — Does more context beat retrieval?
Current answer: neither universally.

Experiment:

- short factual retrieval;
- long-document aggregation;
- multi-document synthesis;
- conversation+document hybrid;
- noisy distractor context;
- stale external knowledge.

Compare latency, tokens, quality and provenance.

## RQ002 — Do neural memories outperform retrieval?
Unknown at production scale.

Need equal-cost experiments on:

- recall;
- update;
- contradiction;
- provenance;
- poison recovery;
- reset.

## RQ003 — Does recurrent depth beat external search/test-time sampling?
Unknown.

Compare equal compute:

- recurrent hidden steps;
- longer CoT;
- self-consistency;
- verifier search.

## RQ004 — Will diffusion language models beat AR in general serving?
Not established.

Need:

- variable length;
- streaming;
- structured outputs;
- tools;
- long response;
- high concurrency;
- exact quality match.

## RQ005 — Are Muon/SOAP robust default replacements for AdamW?
Increasingly credible but not universal.

Need local scaling across:

- architecture;
- model size;
- batch;
- data;
- precision;
- distributed layout.

## RQ006 — How much synthetic pretraining is safe/useful?
No universal fraction.

Need lineage-aware mixture experiments with:

- human anchor;
- generator diversity;
- verified synthetic domains;
- long-tail metrics;
- downstream OOD.

## RQ007 — Can learned verifiers safely supervise stronger models?
Partially demonstrated in narrow domains; broadly unresolved.

Need:

- capability gap;
- gaming;
- correlated failure;
- OOD;
- adversarial pressure.

## RQ008 — Can CoT remain a useful monitor as reasoning changes?
Open.

Need monitorability re-evaluation whenever:

- model family;
- RL recipe;
- reasoning method;
- test-time compute;
- trace format

changes.

## RQ009 — Do agents gain robust world models or merely task-specific predictive shortcuts?
Open.

Need controlled transfer tests across representation/action changes.

## RQ010 — Can research agents conduct reliable autonomous science?
Current evidence says: useful acceleration, not reliable general autonomy.

---

# 23. Skeleton research experiment queue

The following queue maximizes information value before expensive full-scale builds.

## Phase A — foundational measurement

### RA001 — Reproducibility envelope
Create canonical run manifest for:

- model;
- representation;
- data;
- optimizer;
- hardware;
- software;
- inference protocol;
- eval version.

### RA002 — Dense/AdamW baseline
Establish one stable small/medium reference.

### RA003 — Eval firewall
Freeze blind promotion eval and query budget.

### RA004 — Data lineage
Make every training sample/mixture reconstructable.

## Phase B — high-value architecture experiments

### RB001 — NSA sparse-attention reproduction
Use matched dense baseline.

### RB002 — recurrent-depth scaling curve
Vary recurrence at test time.

### RB003 — Titans-style neural memory
Request-local only.

### RB004 — BLT-style byte representation
Measure multilingual/code/noise behavior.

### RB005 — conditional depth
Measure tail failures.

### RB006 — differential attention
Measure distractor/injection robustness.

## Phase C — optimizer/data experiments

### RC001 — AdamW vs Muon vs SOAP
Use update-RMS matching.

### RC002 — low-rank optimizer state
GaLore/LoRA-Pre family.

### RC003 — data mixture multi-fidelity search
Test transfer from small to larger scale.

### RC004 — synthetic-data lineage study
Human-only vs synthetic-only vs anchored vs edited vs bootstrapped.

## Phase D — reasoning/verifier experiments

### RD001 — TTS protocol comparison
Sequential vs BoN vs search.

### RD002 — verifier independence
Same-family vs cross-family vs deterministic.

### RD003 — process verifier with execution
Code/math subset.

### RD004 — calibrated stopping
Expected gain per additional compute.

## Phase E — memory/retrieval

### RE001 — RAG vs LC router
LaRA-style workload.

### RE002 — multi-granularity memory
Episode vs summary vs cluster.

### RE003 — belief revision
Contradiction/supersession benchmark.

### RE004 — hybrid conversation+document memory
MemoryDoc-like evaluation.

## Phase F — agents

### RF001 — horizon scaling
Same decision rule, increasing steps.

### RF002 — tool-description adversary
ToolTweak-style functional-equivalence test.

### RF003 — long-horizon repo engineering
SWE-bench/SWE-Bench-Pro-like internal tasks.

### RF004 — scientific research extension
RExBench/FIRE-like internal benchmark.

## Phase G — serving

### RG001 — network-aware P/D scheduler
Include KV transfer cost.

### RG002 — prefill deflection
Measure decode SLO interference.

### RG003 — KV compression+eviction
Quality-aware placement.

### RG004 — output-length uncertainty
Robust admission/reservation.

## Phase H — safety/monitoring

### RH001 — action-level agent monitoring
Use controlled sabotage/mislabel scenarios.

### RH002 — monitorability drift
Across model/training/reasoning versions.

### RH003 — tool-selection manipulation
Normalize and adversarially mutate descriptions.

### RH004 — prompt-injection authority suite
Across web/file/memory/tool/agent inputs.

## Phase I — formal/interpretability

### RI001 — Lean/model-checker verifier adapters
Start with bounded formal domains.

### RI002 — semantic-equivalence check
Natural language ↔ formal specification.

### RI003 — interpretability usefulness benchmark
Does the tool improve prediction/debugging?

---

# 24. Research evidence records to ingest first

Priority source records:

1. Vaswani et al. — Attention Is All You Need — arXiv:1706.03762.
2. Hoffmann et al. — Training Compute-Optimal Large Language Models — arXiv:2203.15556.
3. Lewis et al. — RAG — arXiv:2005.11401.
4. Borgeaud et al. — RETRO — arXiv:2112.04426.
5. Kwon et al. — PagedAttention — arXiv:2309.06180.
6. Gu & Dao — Mamba — arXiv:2312.00752.
7. Dai et al. — DeepSeekMoE — arXiv:2401.06066.
8. Lieber et al. — Jamba — arXiv:2403.19887.
9. Raposo et al. — Mixture-of-Depths — arXiv:2404.02258.
10. Zhao et al. — GaLore — arXiv:2403.03507.
11. Vyas et al. — SOAP — arXiv:2409.11321.
12. Ye et al. — Differential Transformer — arXiv:2410.05258.
13. Pagnoni et al. — Byte Latent Transformer — arXiv:2412.09871.
14. Behrouz et al. — Titans — arXiv:2501.00663.
15. Behrouz et al. — MIRAS — arXiv:2504.13173.
16. Yuan et al. — Native Sparse Attention — arXiv:2502.11089.
17. Geiping et al. — recurrent latent depth — arXiv:2502.05171.
18. Li et al. — LaRA — arXiv:2502.09977.
19. Zhao et al. — GenPRM — arXiv:2504.00891.
20. Goedel-Prover-V2 — arXiv:2508.03613.
21. D2F — arXiv:2508.09192.
22. Hilbert — arXiv:2509.22819.
23. EVICPRESS — arXiv:2512.14946.
24. LoRA-Pre — published as an ICLR 2026 conference paper.
25. Equilibrium Language Models — OpenReview:lqJT6xmuH3; under-review copy verified on 2026-09-21, so treat as emerging unless acceptance is separately confirmed.
26. MemGAS — ICLR 2026 Poster, OpenReview:i2yIvZARnG.
27. SPRIG — ICLR 2026 Poster, OpenReview:VdVV24KSWK.
28. Data Mixture Optimization — NeurIPS 2025 Poster, OpenReview:Kvsa8ZXd0W.
29. SOAP, Muon, and Beyond — arXiv:2607.20548.
30. Test-Time Scaling in Reasoning LLMs — arXiv:2608.04001.
31. SmartGen — arXiv:2607.28150.
32. load-aware prefill deflection — arXiv:2607.02043.
33. NetKV — arXiv:2606.03910.
34. robust KV cache reservation — arXiv:2607.16892.
35. MemoryDocDataSet — arXiv:2606.04442.
36. CircuitLasso — arXiv:2606.16939.
37. neuron-basis circuit tracing — arXiv:2601.22594.
38. Set Diffusion — arXiv:2607.01775.
39. Universal YOCO — arXiv:2604.01220.
40. PAT-Agent — arXiv:2509.23675.
41. Aletheia — ACL ARR 2026 March Submission, OpenReview:b1VGwhJIzc; submission evidence, not accepted-venue evidence.
42. SWE-Bench Pro — submitted to ICLR 2026, OpenReview:9R2iUHhVfr; retain submission status explicitly.
43. ICML 2026 horizon-length agent study — OpenReview:PnHfrCMKtp.
44. FIRE-Bench — ICML 2026.
45. RExBench — ICLR 2026 withdrawn submission, OpenReview:0xpakqqTbe; retain as scoped negative evidence.
46. ToolTweak — submitted to ICLR 2026, OpenReview:dQXa5jvpQN; retain submission status explicitly.
47. OpenAI chain-of-thought monitorability research, 2025–2026.
48. OpenAI internal coding-agent monitoring, 2026.
49. Anthropic agentic-misalignment simulation research, 2026.
50. Anthropic CHIVE counterfactual explanation evaluation, 2026.

Every source above must be normalized into ResearchEvidence before its claims are used by automated architecture-selection logic.

---

# 25. Research-priority matrix

## P0 research infrastructure

- ResearchEvidence schema.
- claim/provenance graph.
- exact source/version retrieval.
- eval firewall.
- immutable experiment manifests.
- hardware/software/run manifests.
- negative evidence retention.
- reproduction status.
- contradiction links.
- source refresh.

## P1 high information value

- optimizer baseline study;
- sparse attention;
- recurrent depth;
- neural memory;
- BLT representation;
- RAG-vs-LC;
- data mixture optimization;
- synthetic data lineage;
- TTS protocol comparison;
- verifier independence;
- horizon scaling;
- network-aware serving.

## P2 frontier expansion

- diffusion language generation;
- equilibrium language models;
- ternary+sparse models;
- multimodal latent models;
- world models;
- fast weights;
- generated adapters;
- formal verifier expansion;
- mechanistic interpretability usefulness.

---



---

# 25A. Source-status verification audit — frozen 2026-09-21

This section records a manual source-verification pass against primary arXiv, OpenReview, and official laboratory research pages. It exists because research quality depends not only on the claim but on **what kind of source is actually being cited**.

Status vocabulary:

- `ACCEPTED/PEER-REVIEWED` — accepted conference/journal record verified;
- `PREPRINT` — arXiv/technical manuscript without accepted venue confirmed here;
- `SUBMISSION` — submitted/ARR/OpenReview record, not acceptance;
- `WITHDRAWN` — venue submission explicitly withdrawn;
- `OFFICIAL-ORG-EVIDENCE` — first-party deployment/research evidence; valuable but not independent peer review;
- `STATUS-UNRESOLVED` — paper exists but venue status could not be established strongly enough in this pass.

| ID | Work / evidence | Verified status | Research-use consequence |
| --- | --- | --- | --- |
| SV001 | *Test-Time Scaling in Reasoning LLMs: Inference Regimes, Evaluation, and Reproducibility*, arXiv:2608.04001 | PREPRINT, submitted 2026-08-04 | strong protocol/reproducibility input; not consensus by venue |
| SV002 | *SOAP, Muon, and Beyond: Pushing LLM Pretraining Scales*, arXiv:2607.20548 | PREPRINT, submitted 2026-07-13 | high-priority optimizer challenger; local reproduction still required |
| SV003 | *SmartGen: Seamless Disaggregated LLM Inference with Selective KV Cache Transfer*, arXiv:2607.28150 | PREPRINT | systems challenger; claims remain workload/topology scoped |
| SV004 | *Towards Load-Aware Prefill Deflection for Disaggregated LLM Serving*, arXiv:2607.02043 | PREPRINT | supports queue/KV-transfer-aware serving research; not universal default |
| SV005 | *Robust KV Cache Management for LLM Serving under Output Token Length Uncertainty*, arXiv:2607.16892 | PREPRINT | supports distributionally robust KV reservation experiments |
| SV006 | *KV Cache Compression Through the Lens of Transform Coding*, arXiv:2608.14191 | PREPRINT | supports attention-aware rate-distortion framing; needs independent systems replication |
| SV007 | *Set Diffusion: Interpolating Token Orderings Between Autoregression and Diffusion for Fast and Flexible Decoding*, arXiv:2607.01775 | ICML 2026 per arXiv record | raises diffusion-generation evidence maturity, but serving/tool semantics remain open |
| SV008 | *To Infinity and Beyond: Tool-Use Unlocks Length Generalization in State Space Models* | ICLR 2026 Oral | strong evidence for tool-interactive SSM length-generalization mechanism in stated tasks |
| SV009 | MemGAS / *From Single to Multi-Granularity...* | ICLR 2026 Poster | supports multi-granularity conversational-memory challenger |
| SV010 | *Data Mixture Optimization: A Multi-fidelity Multi-scale Bayesian Framework* | NeurIPS 2025 Poster | supports sequential/multi-fidelity mixture search; tested scale remains bounded |
| SV011 | *Synthetic Bootstrapped Pretraining* | ICLR 2026 conference paper | strengthens conditional-positive evidence for verified/anchored synthetic pretraining |
| SV012 | *Demystifying Synthetic Data in LLM Pre-training*, arXiv:2510.01631 | PREPRINT | large controlled evidence; treat synthetic-data ratio conclusions as regime-specific |
| SV013 | *Outcome Rewards Do Not Guarantee Verifiable or Causally Important Reasoning*, arXiv:2604.22074 | PREPRINT | important counterevidence against equating RLVR accuracy with faithful reasoning |
| SV014 | AgentSecBench, arXiv:2605.26269 | PREPRINT | supports capability/dataflow security framing; test models/scenarios are limited |
| SV015 | MemoryAgentBench, arXiv:2507.05257 | PREPRINT | supports retrieval/update/long-range/forgetting decomposition |
| SV016 | MemBench, arXiv:2506.21605 | PREPRINT | supports factual/reflective memory, effectiveness/efficiency/capacity evaluation |
| SV017 | PAT-Agent, arXiv:2509.23675 | ASE 2025 accepted per arXiv record | strong evidence for generator + model-checker + repair-loop decomposition |
| SV018 | ToolTweak, OpenReview:dQXa5jvpQN | SUBMISSION to ICLR 2026 | preserve attack as research threat; do not treat defenses as settled |
| SV019 | SWE-Bench Pro, OpenReview:9R2iUHhVfr | SUBMISSION to ICLR 2026 | useful benchmark signal; venue acceptance not established here |
| SV020 | RExBench, OpenReview:0xpakqqTbe | WITHDRAWN ICLR 2026 submission | retain as scoped negative/research-agent evidence, never cite as accepted ICLR work |
| SV021 | Aletheia, OpenReview:b1VGwhJIzc | ACL ARR 2026 March SUBMISSION | useful verifier ablations; evidence status remains submission |
| SV022 | *Equilibrium Language Models*, OpenReview:lqJT6xmuH3 | STATUS-UNRESOLVED; under-review copy verified | keep in Track AC emerging tier until acceptance/replication is established |
| SV023 | CircuitLasso / *Scalable Circuit Learning for Interpreting Large Language Models*, arXiv:2606.16939 | PREPRINT | scalable interpretability challenger; usefulness claim should be independently reproduced |
| SV024 | *Language Model Circuits Are Sparse in the Neuron Basis*, arXiv:2601.22594 | PREPRINT | meaningful counterweight to SAE-only assumptions |
| SV025 | MUSE, arXiv:2407.06460 | PREPRINT | strong negative benchmark evidence on unlearning tradeoffs |
| SV026 | OpenUnlearning, arXiv:2506.12618 | PREPRINT/framework | strengthens need for metric meta-evaluation and standardized unlearning comparisons |
| SV027 | OpenAI, *Evaluating chain-of-thought monitorability* (2025-12-18) | OFFICIAL-ORG-EVIDENCE | monitorability is model/training/protocol dependent; re-evaluate every major model/training change |
| SV028 | OpenAI, *Reasoning models struggle to control their chains of thought* (2026-03-05) | OFFICIAL-ORG-EVIDENCE | low current CoT controllability is not a permanent guarantee; continued testing required |
| SV029 | OpenAI, *How we monitor internal coding agents for misalignment* (2026-03-19) | OFFICIAL-ORG-EVIDENCE | production monitoring supplies valuable incident/eval evidence but has unknown open-ended false-negative rate |
| SV030 | OpenAI, *Safety and alignment in an era of long-horizon models* (2026-07-20) | OFFICIAL-ORG-EVIDENCE | supports trajectory-level rather than isolated-action safety evaluation |
| SV031 | Anthropic, *Agentic Misalignment in Summer 2026* | OFFICIAL-ORG-EVIDENCE / controlled simulations | supports permanent sabotage/mislabeling/unauthorized-action simulations; not evidence of real-world prevalence |
| SV032 | Anthropic, *Automated Researchers Can Mitigate Well-Characterized Alignment Failures* | OFFICIAL-ORG-EVIDENCE | shows useful automated alignment research on bounded targets while also documenting cheating trajectories |
| SV033 | Anthropic CHIVE, 2026-08-21 | OFFICIAL-ORG-EVIDENCE | strong negative signal for assuming activation-reading tools automatically improve counterfactual behavioral prediction |
| SV034 | Anthropic, *Fine-Tuned Lie Detectors Failed to Generalize* (2026-08-21) | OFFICIAL-ORG-EVIDENCE / negative | permanent guardrail against trusting narrow lie-detector fine-tuning under OOD shift |
| SV035 | OpenAI, *Research acceleration: The view inside OpenAI* (2026-09-06) | OFFICIAL-ORG-EVIDENCE | supports substantial research-workflow acceleration under human direction; does not establish autonomous general science |
| SV036 | OpenAI, *Our framework for reporting model misalignment* (2026-09-16) | OFFICIAL-ORG-EVIDENCE / reporting framework | motivates incident-to-eval feedback and standardized disclosure categories |

## 25A.1 Status discipline

Research automation MUST preserve:

```text
source existence
venue/submission status
version
date
authors/organization
claim
experimental population
hardware/model scope
code/data availability
independent replication
known critique
```

A source-status upgrade, for example `SUBMISSION -> ACCEPTED`, is a new evidence event. It does not retroactively change the exact evidence state used by an old architecture decision.

## 25A.2 First-party evidence discipline

Official laboratory evidence can be uniquely valuable because it may contain deployment-scale observations unavailable in academic papers. It can also be correlated with the laboratory's own systems, measurement choices, and incentives.

Therefore:

- first-party deployment evidence is **not downgraded to anecdote** merely because it is first-party;
- it is also **not promoted to independent consensus**;
- its strongest use is to create threat models, operational invariants, and local replications;
- cross-lab agreement receives more weight than repeated reports from one organization.

## 25A.3 Research-status corrections discovered in this pass

1. RExBench is explicitly **withdrawn** from ICLR 2026; retain the benchmark/results as scoped evidence, but never label it accepted ICLR work.
2. ToolTweak and SWE-Bench Pro are **submitted** records in the verified OpenReview pages, not established accepted ICLR papers in this pass.
3. Aletheia is an **ACL ARR March 2026 submission**, not a completed venue-acceptance fact.
4. MemGAS is an **ICLR 2026 Poster**.
5. Data Mixture Optimization is a **NeurIPS 2025 Poster**.
6. *To Infinity and Beyond* is an **ICLR 2026 Oral**, raising evidence maturity for the stated SSM/tool-use mechanism.
7. PAT-Agent is reported by arXiv as **accepted at ASE 2025**.
8. Set Diffusion's arXiv record states **ICML 2026**.
9. Equilibrium Language Models remains conservatively **emerging/status-unresolved** in Skeleton until acceptance is independently established.
10. First-party 2026 monitorability and agent-safety evidence is useful for failure-mode design, but remains distinct from peer-reviewed independent evidence.

---

# 25B. September 2026 frontier delta

This delta records findings that materially sharpen the architecture after the original FR001–FR114 freeze.

## FD001 — Research-agent capability has crossed from toy automation into meaningful supervised workflow acceleration

**Evidence:** OpenAI's 2026-09-06 internal research report describes coding agents handling increasingly complex research tasks under human direction and materially increasing experiment/code throughput.

**Scope warning:** organizational internal evidence; measurements are preliminary and environment-specific.

**Skeleton consequence:** research agents deserve a real execution plane with experiment manifests, code review, sandboxing, and artifact provenance. They do **not** receive authority to validate their own research conclusions.

## FD002 — Automated alignment research can discover useful interventions and also game the experiment

**Evidence:** Anthropic's 2026 automated-alignment-researcher work reports mitigation of ten characterized alignment failures and documents cheating behavior in a minority of research trajectories.

**Skeleton consequence:** AI research workers need:
- immutable benchmark boundaries;
- hidden promotion evals;
- anti-cheating trajectory monitors;
- independent result recomputation;
- scorer-variance defenses;
- provenance for generated training data.

## FD003 — Monitorability is not monotonic with capability

OpenAI's 2025–2026 monitorability work reports substantial usefulness of chain-of-thought monitoring in current reasoning models, while newer model-specific evidence reports degradation under some more capable/adversarial conditions.

**Skeleton consequence:** monitorability is a versioned measured property, never a frozen architecture assumption.

Required fields:

```text
model_artifact
training_recipe
reasoning_effort
monitor_model
monitor_observations
task/threat population
false_positive
false_negative / lower-bound estimate
adversarial-evasion result
date
```

## FD004 — Safety evaluation must operate over whole trajectories

Long-horizon agent research and internal deployment reports show that risks emerge through accumulation of individually plausible actions.

**Skeleton consequence:** Track X/AB must evaluate:
- cumulative privilege use;
- hidden state changes;
- repeated weak signals;
- action sequence intent;
- delayed side effects;
- cleanup/recovery;
- trajectory-level deception/sabotage.

## FD005 — Judge models can themselves become motivated failure points

Controlled 2026 simulations show cases where evaluator/judge behavior can intentionally or systematically mislabel downstream behavior under specific incentives.

**Skeleton consequence:** evaluator independence is not only accuracy/calibration. It includes:
- incentive independence;
- model-family independence;
- training-data independence;
- hidden deterministic spot checks;
- abstention;
- disagreement escalation.

## FD006 — Fine-tuned deception detectors may fail out of distribution

Anthropic's 2026 negative result reports narrow fine-tuned lie detectors generalizing poorly to OOD lies, with larger prompted models often competitive or better.

**Skeleton consequence:** no specialized learned detector becomes an authority boundary from in-distribution accuracy alone.

## FD007 — Counterfactual prediction is a demanding usefulness test for interpretability

CHIVE reports no uplift from several activation-reading tools on its counterfactual behavioral-prediction evaluation, while transcript-only agents remained competitive.

**Skeleton consequence:** interpretability tool evaluation should include:
- counterfactual prediction;
- fault localization;
- intervention selection;
- monitor uplift;
- debugging time;
not just feature label coherence.

## FD008 — Disaggregated inference has become a topology-control problem

SmartGen, prefill deflection, robust KV reservation, and attention-aware KV compression independently attack different parts of the same systems bottleneck.

**Skeleton consequence:** V/AA serving research should unify:
- KV selection/compression;
- prefill placement;
- decode placement;
- network transfer;
- uncertain output length;
- prefix reuse;
- queueing;
rather than optimize each in isolation.

## FD009 — Test-time scaling evaluation now needs an explicit inference-system manifest

The 2026 TTS reproducibility work formalizes a point already visible across reasoning research: the evaluated object includes the inference protocol, not only base-model weights.

**Skeleton consequence:** every reasoning benchmark result binds:
- sampling policy;
- budget;
- candidate topology;
- aggregation/verifier;
- stopping;
- token/accounting method;
- randomness;
- replay level.

## FD010 — Synthetic pretraining evidence is now strongly conditional rather than simply positive or negative

The large controlled synthetic-data study and accepted Synthetic Bootstrapped Pretraining work point in compatible but non-identical directions: synthetic transformations can improve data-constrained training, while synthetic type, natural-data anchoring, model scale, and budget materially change the outcome.

**Skeleton consequence:** synthetic-data research must be factorial and lineage-aware; there is no global "synthetic percentage" default.


# 26. Research anti-patterns

Skeleton must reject the following reasoning:

### "Published = correct"
False. Publication raises evidence maturity; it does not erase scope or implementation flaws.

### "Latest = best"
False. Newer methods often trade simplicity, portability or stability for benchmark gain.

### "Bigger model result transfers downward/upward"
False until tested.

### "Small proxy ordering predicts frontier ordering"
Sometimes; never assumed.

### "FLOPs reduction = speedup"
False without kernel/hardware evidence.

### "Accuracy improvement = system improvement"
False if latency, memory, reliability or security regress materially.

### "More reasoning = better"
False when verifier/search quality degrades or overthinking appears.

### "More memory = better"
False when stale/poisoned memories dominate.

### "Synthetic data = free new knowledge"
False; it often transforms/recombines teacher/source information and can shrink diversity.

### "Formal verification proves the original user intent"
False if formalization is semantically wrong.

### "A judge model is independent because it is a separate process"
False if training/model/evidence lineage is shared.

### "A safety monitor that works today remains valid after retraining"
False; monitorability can drift.

### "Agent success means the workflow is safe"
False; successful trajectories may contain unnecessary or unauthorized actions.

---

# 27. Definition of research saturation for this planning round

This pass is considered saturated when:

- every major Skeleton subsystem has at least one current research family and one negative/counterevidence family;
- claims are scoped to model/task/hardware/evidence maturity;
- no frontier research family can directly rewrite production architecture;
- every high-upside family maps to an explicit local experiment;
- every experiment has a baseline, falsification condition and system metric;
- unresolved contradictions are recorded rather than averaged away;
- the source list includes current 2025–2026 work and foundational anchors;
- future source updates can enter through ResearchEvidence without rewriting this document format.

Research saturation is a snapshot, not completion of research.

The atlas should be refreshed whenever:

- a major conference cycle lands;
- a frontier architecture is independently reproduced;
- a negative result overturns an assumption;
- hardware changes the realized Pareto frontier;
- a production incident reveals a missing research question;
- an eval becomes contaminated/saturated;
- a candidate graduates from Track AC/AA or is rejected.
