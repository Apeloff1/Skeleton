# Research Source Catalog — Historical Canon, Frontier Inputs, and Anti-Canon

Status: architecture research catalog
Updated: 2026-09-21

This catalog is the reading and evidence map behind Skeleton's SOTA construction plan. It is intentionally broader than a list of currently fashionable LLM papers. The goal is to preserve the strongest historical ideas, understand the systems work that made them practical, and retain negative/failure lessons so the architecture does not repeatedly rediscover old mistakes.

**Important:** inclusion is not endorsement of every claim. Each item enters the ResearchEvidence pipeline and receives local scope, maturity, replication, contradiction, cost, and reproducibility metadata before it can affect architecture.

## 1. Sequence-model foundations

| Work | Identifier | Lasting architectural lesson |
| --- | --- | --- |
| Sutskever et al., *Sequence to Sequence Learning with Neural Networks* | arXiv:1409.3215 | encoder/decoder decomposition; sequence transduction as a reusable interface |
| Bahdanau et al., *Neural Machine Translation by Jointly Learning to Align and Translate* | arXiv:1409.0473 | learned content-dependent attention |
| Vaswani et al., *Attention Is All You Need* | arXiv:1706.03762 | parallel attention-based sequence modeling |
| Devlin et al., *BERT* | arXiv:1810.04805 | bidirectional pretraining and representation transfer |
| Brown et al., *Language Models are Few-Shot Learners* | arXiv:2005.14165 | in-context learning becomes an explicit capability to measure |
| Kaplan et al., *Scaling Laws for Neural Language Models* | arXiv:2001.08361 | model/data/compute performance relationships should be measured |
| Hoffmann et al., *Training Compute-Optimal Large Language Models* | arXiv:2203.15556 | parameter count without sufficient data is not a rational scaling target |

### Skeleton rule

The kernel must not assume that the next best sequence model is a Transformer. These papers inform ModelPort implementations and compute planning, not core authority/state semantics.

## 2. Transformer component evolution

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Ba et al., *Layer Normalization* | arXiv:1607.06450 | normalization is a first-class training stability choice |
| Zhang & Sennrich, *Root Mean Square Layer Normalization* | arXiv:1910.07467 | evaluate cheaper normalization primitives |
| Shazeer, *GLU Variants Improve Transformer* | arXiv:2002.05202 | gated feed-forward variants, including the SwiGLU family |
| Su et al., *RoFormer* | arXiv:2104.09864 | rotary position representation |
| Press et al., *Train Short, Test Long: Attention with Linear Biases* | arXiv:2108.12409 | positional strategy affects extrapolation and memory cost |

### Skeleton rule

Normalization, activation, positional encoding, attention layout, and cache format are versioned model-implementation choices. They do not leak into higher-level task or memory contracts.

## 3. Sparse and alternative model substrates

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Shazeer et al., *Outrageously Large Neural Networks: The Sparsely-Gated Mixture-of-Experts Layer* | arXiv:1701.06538 | conditional computation |
| Lepikhin et al., *GShard* | arXiv:2006.16668 | large sparse expert models plus distributed sharding |
| Fedus et al., *Switch Transformers* | arXiv:2101.03961 | simplified expert routing and sparse scaling |
| Dai et al., *DeepSeekMoE* | arXiv:2401.06066 | fine-grained/shared expert specialization |
| Gu & Dao, *Mamba: Linear-Time Sequence Modeling with Selective State Spaces* | arXiv:2312.00752 | attention is not the only viable sequence substrate |
| Lieber et al., *Jamba* | arXiv:2403.19887 | hybrid attention/SSM/MoE systems are viable |

### Skeleton rule

Keep **system routing** and **model-internal expert routing** separate. A provider/model router cannot depend on the internal expert topology of a candidate model.

## 4. Distributed training, adaptation, and data quality

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Hinton et al., *Distilling the Knowledge in a Neural Network* | arXiv:1503.02531 | teacher/student transfer as a controlled training primitive |
| Shoeybi et al., *Megatron-LM* | arXiv:1909.08053 | tensor/model parallel training |
| Rajbhandari et al., *ZeRO* | arXiv:1910.02054 | partition optimizer/gradient/parameter memory |
| Hu et al., *LoRA* | arXiv:2106.09685 | parameter-efficient adaptation behind stable base weights |
| Dettmers et al., *QLoRA* | arXiv:2305.14314 | quantized-base parameter-efficient finetuning |
| Lee et al., *Deduplicating Training Data Makes Language Models Better* | arXiv:2107.06499 | data duplication affects memorization, evaluation contamination, and efficiency |
| Kirkpatrick et al., *Overcoming Catastrophic Forgetting in Neural Networks* | arXiv:1612.00796 | continual adaptation requires explicit forgetting/regression controls |

### Skeleton rule

Training is an artifact-producing subsystem. Training never writes directly into a deployed model slot. The result is versioned, evaluated, challenged, canaried, and promoted.

## 5. Retrieval and external memory

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Guu et al., *REALM* | arXiv:2002.08909 | retrieval can participate in pretraining |
| Karpukhin et al., *Dense Passage Retrieval* | arXiv:2004.04906 | dense retrieval as a specialized evidence lookup primitive |
| Khattab & Zaharia, *ColBERT* | arXiv:2004.12832 | late interaction offers a different quality/cost point |
| Lewis et al., *Retrieval-Augmented Generation* | arXiv:2005.11401 | non-parametric evidence can ground generation |
| Borgeaud et al., *Improving Language Models by Retrieving from Trillions of Tokens* | arXiv:2112.04426 | retrieval can trade external memory for parametric scale |
| Gao et al., *Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE)* | arXiv:2212.10496 | generated intermediate retrieval representations can improve zero-shot search |
| Park et al., *Generative Agents* | arXiv:2304.03442 | memory streams, reflection, and retrieval as agent-architecture inspiration |
| Packer et al., *MemGPT* | arXiv:2310.08560 | explicit memory hierarchy and context management |

### Skeleton rule

Retrieval is evidence acquisition, not truth acquisition. Retrieved material keeps provenance, freshness, and trust labels all the way into the context compiler.

## 6. Reasoning and neuro-symbolic execution

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Wei et al., *Chain-of-Thought Prompting Elicits Reasoning in Large Language Models* | arXiv:2201.11903 | deliberate intermediate reasoning can improve selected tasks |
| Wang et al., *Self-Consistency Improves Chain of Thought Reasoning* | arXiv:2203.11171 | multiple trajectories can outperform one greedy path |
| Gao et al., *PAL: Program-aided Language Models* | arXiv:2211.10435 | delegate exact computation to deterministic runtimes |
| Yao et al., *Tree of Thoughts* | arXiv:2305.10601 | explicit bounded search/backtracking |
| Shinn et al., *Reflexion* | arXiv:2303.11366 | episodic feedback can improve repeated attempts without weight updates |
| Madaan et al., *Self-Refine* | arXiv:2303.17651 | generation-feedback-refinement loop as an optional reasoning pattern |
| Snell et al., *Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters* | OpenReview:4FWAwZtd2n | inference compute should be allocated by task/difficulty rather than fixed globally |

### Skeleton rule

These become **budgeted reasoning modes**, never mandatory universal chains. The controller measures whether extra search/critique actually improves task success per unit compute.

## 7. Tool use and action

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Karpas et al., *MRKL Systems* | arXiv:2205.00445 | modular neuro-symbolic routing to expert tools |
| Yao et al., *ReAct* | arXiv:2210.03629 | interleave reasoning, action, and environment observation |
| Schick et al., *Toolformer* | arXiv:2302.04761 | learn when API use is useful |
| Gao et al., *PAL* | arXiv:2211.10435 | use executable tools for exact subproblems |

### Skeleton rule

The model proposes `ToolIntent`. The authority/execution plane validates and executes it. Model competence never implies permission.

## 8. Post-training and preference learning

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Schulman et al., *Proximal Policy Optimization Algorithms* | arXiv:1707.06347 | stable policy optimization primitive |
| Ouyang et al., *Training Language Models to Follow Instructions with Human Feedback* | arXiv:2203.02155 | instruction tuning + preference feedback can strongly alter model behavior |
| Bai et al., *Constitutional AI: Harmlessness from AI Feedback* | arXiv:2212.08073 | machine-generated critique/preference data can participate in alignment pipelines |
| Wang et al., *Self-Instruct* | arXiv:2212.10560 | synthetic instruction generation as a data-expansion method |
| Rafailov et al., *Direct Preference Optimization* | arXiv:2305.18290 | preference optimization without an explicit RL loop |

### Skeleton rule

No single post-training algorithm is constitutional. SFT, DPO-family methods, reward modeling, RL, distillation, and future methods sit behind the same dataset/evaluation/promotion contract.

## 9. Inference and serving systems

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Dao et al., *FlashAttention* | arXiv:2205.14135 | IO-aware exact attention can change the systems bottleneck |
| Dao, *FlashAttention-2* | arXiv:2307.08691 | work partitioning and hardware utilization matter as much as asymptotics |
| Yu et al., *Orca: A Distributed Serving System for Transformer-Based Generative Models* | OSDI 2022 / arXiv:2206.02658 | iteration-level scheduling and continuous serving batches |
| Kwon et al., *Efficient Memory Management for Large Language Model Serving with PagedAttention* | arXiv:2309.06180 | page/block-managed KV cache reduces fragmentation and improves serving |
| Leviathan et al., *Fast Inference from Transformers via Speculative Decoding* | arXiv:2211.17192 | exact-distribution speculative execution can accelerate autoregressive decoding |
| Agrawal et al., *Sarathi* | arXiv:2308.16369 | chunked prefill helps manage prefill/decode interference |

### Skeleton rule

Inference owns scheduling, cache, batching, kernels, and hardware utilization. It does not own cognition policy, tool authority, durable memory, or application state.

## 10. Evaluation and benchmark discipline

| Work / benchmark | Identifier | Construction relevance |
| --- | --- | --- |
| Hendrycks et al., *MMLU* | arXiv:2009.03300 | broad academic knowledge/capability slice |
| Lin et al., *TruthfulQA* | arXiv:2109.07958 | test imitative falsehoods/truthfulness failure |
| Srivastava et al., *BIG-bench* | arXiv:2206.04615 | broad task diversity and emergent failure discovery |
| Liang et al., *HELM* | arXiv:2211.09110 | multi-metric holistic model evaluation |
| Liu et al., *AgentBench* | arXiv:2308.03688 | agent behavior across interactive environments |
| Mialon et al., *GAIA* | arXiv:2311.12983 | real-world assistant tasks combining reasoning, tools, web, and multimodality |
| Jimenez et al., *SWE-bench* | arXiv:2310.06770 | repository-level software engineering |
| Xie et al., *OSWorld* | arXiv:2404.07972 | realistic computer-use tasks |

### Skeleton rule

Benchmarks are **sensors**, not objectives. Never declare a universal winner from one score. Store exact benchmark version, task population, contamination risk, runtime configuration, and raw evidence.

## 11. Security and instruction-boundary research

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Greshake et al., *More than you've asked for: A Comprehensive Analysis of Novel Prompt Injection Threats to Application-Integrated Large Language Models* | arXiv:2302.12173 | indirect prompt injection is a system integration problem |
| Zhan et al., *InjecAgent* | arXiv:2403.02691 | tool-integrated agents require adversarial indirect-injection evaluation |
| Wallace et al., *The Instruction Hierarchy* | arXiv:2404.13208 | explicit privilege ordering between instruction sources |

### Skeleton rule

Authority metadata is carried structurally. The model is never asked to infer privilege solely from prose.

## 12. What to extract from each paper

A paper is not represented only by title/abstract.

Extraction must include:

1. problem definition;
2. exact claimed contribution;
3. baseline;
4. task population;
5. dataset/version;
6. model size/family;
7. training and inference budget;
8. hardware and systems assumptions;
9. metrics;
10. uncertainty/significance where reported;
11. ablations;
12. negative results;
13. limitations;
14. code/weights availability;
15. license;
16. later replications;
17. contradictions/critiques;
18. applicability to Skeleton;
19. cheapest meaningful reproduction;
20. architecture contract potentially affected.

## 13. Anti-canon — failures we preserve deliberately

The anti-canon is as important as the canon. These are failure patterns the architecture should make difficult.

### Bigger model = better system

False as a construction rule. Model scale competes with data, training compute, inference cost, memory, latency, tool quality, retrieval, and lifetime workload.

### More context = memory solved

False. Context is transient working state. Durable memory needs identity, provenance, retrieval policy, contradiction handling, expiry, deletion, and promotion.

### More search = better reasoning

False. Search can amplify weak heuristics, correlated verifier mistakes, or reward hacking. Search needs budgets, deduplication, stop rules, and independent checks.

### More agents = more intelligence

False. Additional agents can add coordination overhead and correlated error. Add agents only when specialization, parallelism, diversity, or fault isolation is measured.

### Majority vote = truth

False. Ten correlated instances of one model are not ten independent witnesses. Verifier and evidence independence must be represented explicitly.

### RAG result = fact

False. Retrieval is source selection. The retrieved item may be stale, poisoned, irrelevant, contradictory, or wrong.

### Tool-capable model = authorized actor

False. Capability to emit an action string does not grant permission to execute it.

### Passing tests = correct in all relevant ways

False. Tests provide scoped evidence. Property tests, fuzzing, differential checks, adversarial evaluation, formal methods, and runtime monitoring may be required.

### Benchmark rank = architecture truth

False. Benchmarks have populations, versions, contamination risks, measurement noise, and incentives. A useful benchmark result becomes one edge in the evidence graph.

### Live self-training = continuous learning solved

False. Uncontrolled updates create forgetting, poisoning, drift, irreproducibility, and rollback problems. Adaptation velocities remain separated.

### Confidence score = calibrated certainty

False. Confidence requires empirical calibration against observed outcomes and may drift by task/domain.

### Paper prestige = reproducibility

False. Venue/source reputation is metadata, not a substitute for local reproduction and challenge.

## 14. Research expansion queues

The catalog should keep expanding in parallel lanes rather than as one unbounded reading list.

### Architecture lane

- new attention variants;
- state-space/recurrent hybrids;
- sparse conditional compute;
- memory-augmented architectures;
- multimodal fusion;
- modular neural systems.

### Training lane

- data quality and mixture optimization;
- optimizer/stability improvements;
- distributed training;
- low-precision training;
- parameter-efficient adaptation;
- continual learning;
- distillation/compression.

### Reasoning lane

- adaptive compute;
- search;
- verifier-guided inference;
- program/symbolic assistance;
- uncertainty estimation;
- decomposition;
- planning.

### Systems lane

- KV/cache architectures;
- disaggregated prefill/decode;
- prefix sharing;
- continuous batching;
- speculative decoding;
- quantization;
- kernel fusion;
- heterogeneous hardware.

### Memory/retrieval lane

- hybrid sparse+dense retrieval;
- reranking;
- graph retrieval;
- temporal retrieval;
- memory consolidation;
- provenance;
- long-context routing.

### Agent/tool lane

- tool learning;
- computer use;
- multi-agent coordination;
- permissions;
- durable workflow state;
- transactionality;
- recovery.

### Evaluation/safety lane

- realistic task environments;
- process/outcome verification;
- calibration;
- prompt injection;
- data poisoning;
- capability elicitation;
- benchmark contamination;
- formal correctness.


## 15. Optimizer internals canon and challenger set

These sources seed Track Z. Inclusion means “must be reproducibly evaluated where relevant,” not “make default.”

| Work | Identifier | Construction relevance |
| --- | --- | --- |
| Gupta et al., *Shampoo: Preconditioned Stochastic Tensor Optimization* | arXiv:1802.09568 / ICML 2018 | tensor-structure-aware preconditioning; measure decomposition/preconditioner cost |
| Dettmers et al., *8-bit Optimizers via Block-wise Quantization* | arXiv:2110.02861 | optimizer-state quantization and memory reduction with stability mechanisms |
| Chen et al., *Symbolic Discovery of Optimization Algorithms* (Lion) | arXiv:2302.06675 / NeurIPS 2023 | sign-momentum family; lower optimizer state and large-batch behavior |
| Liu et al., *Sophia: A Scalable Stochastic Second-order Optimizer for Language Model Pre-training* | arXiv:2305.14342 | lightweight curvature-aware optimization candidate |
| Mishchenko & Defazio, *Prodigy: An Expeditiously Adaptive Parameter-Free Learner* | arXiv:2306.06101 / ICML 2024 | learning-rate adaptation / reduced tuning burden candidate |
| Zhao et al., *GaLore: Memory-Efficient LLM Training by Gradient Low-Rank Projection* | arXiv:2403.03507 | full-parameter training with low-rank gradient projection to reduce optimizer memory |
| Defazio et al., *The Road Less Scheduled* | arXiv:2405.15682 | schedule-free optimization; removes dependence on a predeclared stop step |
| Vyas et al., *SOAP: Improving and Stabilizing Shampoo using Adam* | arXiv:2409.11321 | combines Shampoo-style bases with Adam-like moment adaptation |
| Jordan et al., *Muon: An optimizer for hidden layers in neural networks* | 2024 technical writeup / official implementation | orthogonalized momentum candidate for compatible matrix parameters; evaluate separately from AdamW-managed parameters |
| Fishman et al., *Scaling FP8 training to trillion-token LLMs* | arXiv:2409.12517 | long-horizon FP8 stability, Smooth-SwiGLU, and FP8 Adam-moment evidence |
| Peng et al., *FP8-LM: Training FP8 Large Language Models* | arXiv:2310.18313 | FP8 compute, gradients, optimizer state, and distributed communication design |

### Skeleton optimizer rule

No optimizer family becomes constitutional. The permanent architecture is the optimizer **contract, telemetry, checkpoint/migration semantics, parameter-class policy, and promotion gate**.

Required optimizer evidence includes:

- exact parameter classes using each update rule;
- state bytes/parameter and total checkpoint footprint;
- quality at equal tokens;
- quality at equal wall-clock;
- convergence/stability distribution across seeds;
- update and gradient diagnostics;
- sensitivity to batch/sequence/model scale;
- precision interaction;
- communication cost;
- checkpoint/resume fidelity;
- failure/recovery behavior;
- downstream task quality;
- rollback path.

Optimizer results from small proxy models are discovery evidence. They are not sufficient proof for frontier-scale transfer.

## 16. Massive-upgrade source seeds

These sources seed Track AA and should be expanded through ResearchEvidence adapters.

| Work | Identifier | Massive-upgrade question |
| --- | --- | --- |
| Gale et al., *MegaBlocks: Efficient Sparse Training with Mixture-of-Experts* | arXiv:2211.15841 | can dropless/block-sparse expert execution improve MoE efficiency without padding/token-drop compromises? |
| Wang et al., *FP8-LM* | arXiv:2310.18313 | can low-precision training reduce compute/memory/communication at preserved quality? |
| Jiang et al., *MegaScale: Scaling Large Language Model Training to More Than 10,000 GPUs* | OpenReview:8l8K2ABUDx | full-stack co-design, observability, fault tolerance, and straggler control at extreme scale |
| Fang & Zhao, *USP: A Unified Sequence Parallelism Approach for Long Context Generative AI* | arXiv:2405.07719 | hybrid sequence-parallel strategies for very long context |
| Gu et al., *LoongTrain: Efficient Training of Long-Sequence LLMs with Head-Context Parallelism* | arXiv:2406.18485 | 2D head/context parallelism and long-sequence scaling |
| Wang et al., *DataStates-LLM: Lazy Asynchronous Checkpointing for Large Language Models* | arXiv:2406.10707 | asynchronous checkpoint staging and recovery-point tradeoffs |
| P/D-Serve authors, *Serving Disaggregated Large Language Model at Scale* | arXiv:2408.08147 | prefill/decode disaggregation, KV transfer, dynamic placement, and scaling |
| Fishman et al., *Scaling FP8 training to trillion-token LLMs* | arXiv:2409.12517 | long-duration numerical pathologies can differ from short-run FP8 demonstrations |
| Wang et al., *Optimizing Large Language Model Training Using FP4 Quantization* | arXiv:2501.17116 | experimental FP4 training with mixed-precision/outlier compensation |
| Yuan et al., *Native Sparse Attention: Hardware-Aligned and Natively Trainable Sparse Attention* | arXiv:2502.11089 | end-to-end trainable sparse attention co-designed with hardware |

### Massive-upgrade research rule

A result enters Track AA only if it could materially alter at least one of:

- capability envelope;
- useful context length;
- training cost/time;
- inference cost/latency;
- memory footprint;
- cluster scale;
- operational reliability;
- architecture-family viability.

A microbenchmark speedup is insufficient. Track AA requires full-path measurement from training or model artifact through serving and failure recovery.

### Negative-evidence obligations for Z / AA

The catalog must intentionally retain cases where:

- optimizer gains disappear after proper tuning of the baseline;
- memory savings shift cost to communication or checkpointing;
- low precision passes short runs and fails late;
- sparse attention loses important long-range behavior;
- MoE routing collapses or concentrates load;
- long-context claims fail useful retrieval/aggregation/reasoning tests;
- distributed speedups vanish on a different interconnect topology;
- speculative decoding adds overhead under low acceptance or high concurrency;
- kernel autotuning chooses a numerically invalid fast path;
- learned optimizer/meta-controller fails under scale or distribution shift.

These negative cases are architecture assets because they narrow unsafe or wasteful promotion regions.


## 17. Exotic architecture canon

These sources seed Track AC. They are selected because they challenge one or more default assumptions of current LLM stacks: fixed tokenization, fixed depth, left-to-right decoding, dense activation, conventional weight precision, static inference-time memory, or modality-specific generation.

| Work | Identifier | Exotic architectural question |
| --- | --- | --- |
| Behrouz et al., *Titans: Learning to Memorize at Test Time* | arXiv:2501.00663 / NeurIPS 2025 | can a bounded neural memory learn during sequence processing and outperform fixed-state recurrent or attention-only memory? |
| Behrouz et al., *It's All Connected: A Journey Through Test-Time Memorization, Attentional Bias, Retention, and Online Optimization* (MIRAS) | arXiv:2504.13173 | can sequence architectures be systematically designed as associative memories with explicit retention and online-learning rules? |
| Pagnoni et al., *Byte Latent Transformer: Patches Scale Better Than Tokens* | arXiv:2412.09871 | can raw-byte dynamic patching remove fixed-vocabulary tokenization while preserving or improving scaling and inference efficiency? |
| Yu et al., *Discrete Diffusion in Large Language and Multimodal Models: A Survey* | arXiv:2506.13759 | what system contracts change when generation is iterative denoising rather than strictly autoregressive? |
| Wang et al., *Diffusion LLMs Can Do Faster-Than-AR Inference via Discrete Diffusion Forcing* | arXiv:2508.09192 | can AR/diffusion hybrids exploit parallel generation without losing practical KV/cache efficiency? |
| Geiping et al., *Scaling up Test-Time Compute with Latent Reasoning: A Recurrent Depth Approach* | arXiv:2502.05171 / NeurIPS 2025 | can test-time compute scale through hidden recurrence instead of longer visible reasoning traces? |
| Sun et al., *Universal YOCO for Efficient Depth Scaling* | arXiv:2604.01220 | can parameter-shared recursive depth coexist with efficient constant-global-KV architectures? |
| *Equilibrium Language Models* | OpenReview:lqJT6xmuH3 / ICLR 2026 | can repeated layers be replaced by fixed-point computation with implicit depth? |
| Raposo et al., *Mixture-of-Depths* | arXiv:2404.02258 | can a model route only selected tokens through expensive depth while keeping aggregate compute predictable? |
| Ye et al., *Differential Transformer* | arXiv:2410.05258 / MSR-TR-2024-42 | can paired/differential attention suppress irrelevant-context noise and outliers? |
| Ma et al., *The Era of 1-bit LLMs: All Large Language Models are in 1.58 Bits* | arXiv:2402.17764 | can ternary weights define a native train-from-scratch architecture and new hardware regime rather than merely a quantization format? |
| Ma et al., *BitNet b1.58 2B4T Technical Report* | arXiv:2504.12285 | does native 1.58-bit training remain competitive at multi-trillion-token scale? |
| Wang et al., *BitNet a4.8* | arXiv:2411.04965 | how far can low-bit activations/KV and sparse computation extend the ternary architecture? |
| Wang et al., *Q-Sparse: All Large Language Models can be Fully Sparsely-Activated* | arXiv:2407.10969 | can activation sparsity become a general model substrate rather than only expert sparsity? |
| Zhang et al., *Sparse-BitNet* | arXiv:2603.05168 / Microsoft Research | do native ternary weights and semi-structured sparsity combine unusually well under real kernels? |
| Sun et al., *You Only Index Once: Cross-Layer Sparse Attention with Shared Routing* | arXiv:2606.06467 | can one sparse routing/index decision be reused across layers to amortize long-context routing cost? |
| Sun et al., *Multimodal Latent Language Modeling with Next-Token Diffusion* (LatentLM) | arXiv:2412.08635 | can continuous visual/audio/video latents and discrete text share one causal language-model substrate? |
| Gomez et al., *The Reversible Residual Network* | arXiv:1707.04585 | can exact/reconstructable hidden transformations reduce activation storage enough to justify reversible blocks in modern foundation models? |

### Exotic-source interpretation rule

The research above has very different evidence strength, model scales, hardware assumptions, and maturity. Skeleton must not flatten these into an "exotic SOTA" ranking.

For each candidate record:

- assumption being challenged;
- implementation maturity;
- largest credible scale demonstrated;
- training-token scale;
- real hardware/kernel support;
- quality baseline;
- wall-clock baseline;
- serving baseline;
- long-horizon stability;
- portability;
- unresolved failure modes;
- compatibility with Track AB invariants.

### Track AC anti-canon

The following claims are explicitly forbidden without evidence:

- "tokenizer-free" means representation problems disappear;
- inference-time learning is equivalent to durable trustworthy memory;
- latent reasoning is inherently safer because it is hidden;
- diffusion is inherently faster because tokens are predicted in parallel;
- recurrent depth gives unlimited intelligence by looping longer;
- fixed-point convergence is guaranteed because a training loss decreased;
- sparse FLOPs imply real wall-clock or energy savings;
- 1-bit weights imply the entire runtime is 1-bit;
- multimodal latent unification preserves provenance automatically;
- generated adapters or experts are safe because they are small;
- a world model's prediction is an observation;
- architecture search can validate its own search objective;
- two exotic mechanisms that each work independently will compose cleanly.

### Exotic reproduction order

Default reproduction order for Tier E1:

1. token/byte representation microbenchmarks and BLT-style toy scaling;
2. recurrent-depth and conditional-depth small-model experiments;
3. test-time neural-memory isolation/replay experiments;
4. diffusion/AR-hybrid serving prototype with tentative-output semantics;
5. ternary + sparse-kernel measurement;
6. differential/sparse attention retrieval and distraction tests;
7. latent multimodal representation/provenance prototype;
8. equilibrium/reversible-block numerical tests;
9. only then compound architectures.

The point is to find **which abstraction actually changes the Pareto frontier**, not to maximize the number of exotic mechanisms in one model.

## 18. Promotion rule


The catalog may grow aggressively. Production may not.

A catalog entry can become a production architecture change only through:

```text
catalog
 -> ResearchEvidence
 -> scoped claim
 -> local reproduction
 -> candidate implementation
 -> baseline comparison
 -> ablation
 -> adversarial/system evaluation
 -> ADR
 -> shadow
 -> canary
 -> promoted immutable version
 -> monitoring
```

This asymmetry is intentional: **fast research intake, slow evidence-based promotion**.
