# Frontier Research Atlas — 2026-09-21

Status: canonical research-synthesis input  
Scope: architecture, data, training, reasoning, verification, memory, retrieval, agents, serving, hardware, multimodality, interpretability, safety, evaluation, formal methods, unlearning, and negative evidence  
Authority: evidence input only; never production authority

## 0. Purpose

This atlas is not a leaderboard and not a bibliography.

It answers four questions for every important research family:

1. **What appears to be true right now?**
2. **How strong and transferable is the evidence?**
3. **What evidence contradicts, narrows, or complicates the claim?**
4. **What should Skeleton reproduce locally before architecture promotion?**

Every conclusion is intentionally scoped. A result on one model scale, hardware topology, task population, or benchmark is not generalized without evidence.

Research maturity vocabulary:

- **FOUNDATIONAL** — broad, durable, repeatedly corroborated;
- **REPLICATED** — supported by multiple meaningful reproductions or strong independent convergence;
- **FRONTIER** — compelling and practically relevant, but still recent or context-dependent;
- **EMERGING** — promising but narrow, pre-review, small-scale, or sparsely reproduced;
- **MIXED** — credible evidence points in different directions;
- **NEGATIVE** — useful null/failure/counterexample;
- **SUPERSEDED** — historically important but no longer preferred for current use.

Confidence vocabulary:

- **high** — strong evidence inside the stated scope;
- **medium** — meaningful evidence with important boundary conditions;
- **low** — exploratory conclusion requiring reproduction.

A maturity label is not a ranking. A NEGATIVE result can be one of the most valuable architecture inputs.

---

# 1. Research-thesis registry

Each thesis below is a **dated, falsifiable architecture belief**, not permanent truth.

## RT-001 — Scaling laws are local to data and training regime

**State:** REPLICATED  
**Confidence:** high  
**Scope:** pretraining planning

Evidence from Kaplan-style and Chinchilla-style scaling work established predictable compute/data/model relationships, while later large-model reports and controlled studies show that optimal scaling coefficients change with data quality, mixture, optimizer, architecture, and regime.

**Skeleton conclusion:** never encode a universal parameter/token scaling law. Scaling laws are fitted artifacts tied to a dataset mixture, optimizer family, architecture family, objective, and hardware envelope.

**Counterevidence / limits:** proxy-model fits can transfer poorly after data-quality or architecture changes.

**Local experiment:** fit loss/quality surfaces across at least three model sizes and three token budgets for each materially new data mixture or architecture family.

---

## RT-002 — Data mixture quality is an optimization variable, not a preprocessing detail

**State:** REPLICATED  
**Confidence:** high

DoReMi (arXiv:2305.10429) demonstrated that learned domain reweighting can substantially improve training efficiency. Later work reinforces that data composition changes scaling behavior.

**Skeleton conclusion:** MixtureManifest must be a first-class training artifact. Dataset lineage must retain domain weights, curriculum stage, filtering, and mixture optimizer version.

**Counterevidence / limits:** proxy-derived weights may overfit proxy scale or evaluation assumptions.

**Local experiment:** compare fixed heuristic mixture, temperature mixture, DoReMi-style proxy weighting, and held-out downstream-aware oracle mixtures.

---

## RT-003 — Synthetic pretraining data is conditionally useful, not a universal replacement for natural data

**State:** FRONTIER  
**Confidence:** medium-high

Kang et al., *Demystifying Synthetic Data in LLM Pre-training* (arXiv:2510.01631) reports a large controlled study over >1000 training runs. Rephrased synthetic data mixed with natural data can accelerate learning, while pure generated textbook-style data can degrade broader-domain performance and exhibit collapse-like behavior.

**Skeleton conclusion:** synthetic data must retain generator identity, transformation type, ancestry depth, natural-data anchor ratio, domain distribution, and diversity statistics. "Synthetic" is not one data class.

**Counterevidence / limits:** results depend on synthesis type, model size, budget, and generator.

**Local experiment:** natural-only vs rephrased-mixture vs generated-textbook-mixture across model size and token budget; measure domain generalization, diversity, memorization, and collapse indicators.

---

## RT-004 — Recursive synthetic-data loops require explicit ancestry and diversity controls

**State:** MIXED  
**Confidence:** medium

Model-collapse research and 2025–2026 synthetic-data studies disagree on how quickly recursive generation degrades models; results vary strongly with filtering, real-data anchoring, and synthetic generation process.

**Skeleton conclusion:** every synthetic sample carries generator/model/version, parent source, recursion depth, and diversity metadata. Training policy may cap ancestry depth.

**Falsification:** if repeated generations with strong real-data anchors retain diversity and quality across many cycles, ancestry caps may be relaxed.

---

## RT-005 — Test-time compute works, but no single strategy is universally optimal

**State:** REPLICATED  
**Confidence:** high

Snell et al. (ICLR 2025, OpenReview:4FWAwZtd2n) found adaptive compute allocation can outperform naive fixed compute. *The Art of Scaling Test-Time Compute* (arXiv:2512.02008) reports large-scale comparisons across models and tasks where optimal strategy depends on model type, problem difficulty, and budget.

**Skeleton conclusion:** ReasoningBudgetAllocator chooses strategy, not merely token count. Direct, parallel sampling, sequential revision, decomposition, search, latent recurrence, and verifier-guided modes are different compute allocations.

**Counterevidence / limits:** gains can saturate or reverse; harder-looking tasks do not always benefit from more tokens.

**Local experiment:** quality/cost curves by task family, difficulty, and model family; record where extra compute hurts.

---

## RT-006 — Verification deserves its own test-time compute budget

**State:** FRONTIER  
**Confidence:** medium-high

Recent 2026 deep-research work studies generator-side and evaluator-side scaling and finds that allocating compute to verification can be more efficient when candidate verification is materially easier than candidate generation.

**Skeleton conclusion:** ReasoningBudget must split generation, search, evidence acquisition, and verification budgets. Verification is not a zero-cost postscript.

**Counterevidence / limits:** asymmetry of verification is task-dependent; some tasks are nearly as hard to verify as solve.

**Local experiment:** derive empirical solve-cost / verify-cost ratios per task family and route compute accordingly.

---

## RT-007 — Outcome rewards alone do not guarantee faithful or causally important reasoning

**State:** FRONTIER  
**Confidence:** medium-high

Yu et al., *Outcome Rewards Do Not Guarantee Verifiable or Causally Important Reasoning* (arXiv:2604.22074) reports that RLVR can improve answer accuracy without reliably improving causal importance or sufficiency of generated reasoning.

**Skeleton conclusion:** never infer reasoning faithfulness from outcome accuracy. Store outcome correctness, process sufficiency, causal perturbation evidence, and verifier evidence separately.

**Counterevidence:** other RLVR work argues correct reasoning is incentivized under better metrics; the area remains contested.

**Local experiment:** perturb or remove reasoning segments and measure causal effect; verify whether the trace is sufficient to reconstruct the result.

---

## RT-008 — RLVR generalization is domain- and reward-structure-dependent

**State:** MIXED  
**Confidence:** medium-high

LongRLVR (arXiv:2603.02146) argues long-context RL needs explicit verifiable context-grounding rewards. Li et al. (arXiv:2603.20799) report that gains on verifiable tasks do not automatically transfer to general QA.

**Skeleton conclusion:** RLVR is a training family behind a contract, not the universal post-training default. Reward schema must declare what is verifiable and what behavior it fails to supervise.

**Local experiment:** evaluate transfer separately on math/code, retrieval-grounded tasks, general QA, tools, memory, and multimodal tasks.

---

## RT-009 — Strong verifiers can be more valuable than more search, but verifier errors compound

**State:** FRONTIER  
**Confidence:** medium-high

Recent test-time scaling and verifier work shows efficient gains from better candidate evaluation. Aletheia (2026 ACL ARR) also finds verifier training recipes vary by scale and that inference compute cannot substitute for missing core training ingredients.

**Skeleton conclusion:** maintain a plural verifier registry with independence metadata. Do not treat verifier score as truth.

**Kill condition:** if candidate diversity collapses around verifier biases or adversarial examples exploit the verifier, revert to deterministic/external checks where possible.

---

## RT-010 — Formal verification is qualitatively different evidence from model judgment

**State:** FOUNDATIONAL  
**Confidence:** high

Proof assistants and deterministic execution can certify narrow properties that learned judges cannot. 2025–2026 theorem-proving systems increasingly combine LLM generation with Lean/Isabelle verification rather than replacing formal checkers.

**Skeleton conclusion:** where a task can be formalized economically, compiler/type checker/SMT/proof-assistant evidence outranks model self-evaluation for the verified property.

**Limit:** formalization itself can be wrong or incomplete.

---

## RT-011 — Memory evaluation requires retrieval, update, forgetting, and prospective behavior

**State:** FRONTIER  
**Confidence:** high for the evaluation need

MemBench (arXiv:2506.21605), MemoryAgentBench (arXiv:2507.05257), and PM-Bench (arXiv:2607.12385) expose different failure modes: factual/reflective memory, incremental updating/selective forgetting, and future-intention execution.

**Skeleton conclusion:** memory cannot be reduced to "vector recall accuracy." Evaluate:
- retrieval;
- consolidation;
- contradiction/update;
- selective forgetting;
- prospective intentions;
- latency/capacity;
- poisoning;
- privacy;
- action consequences.

**Local experiment:** permanent memory regression suite must contain all of the above.

---

## RT-012 — Durable agent memory should be treated as belief revision, not append-only accumulation

**State:** FRONTIER synthesis  
**Confidence:** medium

Recent memory surveys and benchmarks consistently identify contradiction handling, consolidation, forgetting, and update semantics as unresolved weaknesses.

**Skeleton conclusion:** semantic memory stores claims with provenance/version/contradictions rather than replacing old claims in place.

**Falsification:** an append-only retrieval design that consistently outperforms explicit revision on temporal/contradictory tasks would narrow this requirement.

---

## RT-013 — Prospective memory is a distinct capability

**State:** FRONTIER  
**Confidence:** medium-high

PM-Bench 2026 shows future-intention execution remains challenging even with modern agents.

**Skeleton conclusion:** future tasks/intents are not normal semantic memories. They require condition/time triggers, durable state, revalidation, expiry, and action authority.

---

## RT-014 — Long context and RAG are complementary; routing must be empirical

**State:** REPLICATED / MIXED on optimal route  
**Confidence:** high

LaRA (arXiv:2502.09977) reports no universal winner between long context and RAG. Results depend on task, context length, model, and retrieval quality.

**Skeleton conclusion:** context compiler dynamically chooses direct context, retrieval, graph lookup, compression, or mixed strategies.

**Anti-pattern:** "context window is large enough, therefore retrieval is obsolete."

---

## RT-015 — Complex RAG can lose to strong lexical retrieval

**State:** EMERGING but important negative evidence  
**Confidence:** medium

A 2026 controlled scaling study, *Which RAG Paradigm Wins at Scale?* (arXiv:2607.26497), reports BM25 on the Pareto frontier across its tested corpus scales and large cost/accuracy failures for some graph/agentic designs.

**Skeleton conclusion:** BM25/lexical retrieval remains a mandatory baseline. Graph/agentic RAG must justify construction and query cost.

**Local experiment:** corpus-size ladder with fixed relevant/adversarial documents, measuring quality, build cost, query tokens, latency, and maintenance.

---

## RT-016 — Reasoning-intensive retrieval remains weak

**State:** REPLICATED  
**Confidence:** high

BRIGHT (arXiv:2407.12883) demonstrates that retrieval requiring multi-step reasoning remains hard even when source text exists in the corpus.

**Skeleton conclusion:** separate retrieval relevance from reasoning-enhanced retrieval. Query expansion/reasoning may help, but must be measured independently.

---

## RT-017 — Serving bottlenecks increasingly include KV movement and network topology

**State:** FRONTIER  
**Confidence:** high

P/D-Serve and 2026 work such as Prefill-as-a-Service (arXiv:2604.15039), NetKV (arXiv:2606.03910), and load-aware prefill deflection (arXiv:2607.02043) demonstrate that disaggregated serving creates explicit network/KV scheduling problems.

**Skeleton conclusion:** serving scheduler consumes compute load, prefix locality, KV bytes, network topology, bandwidth, queue delay, and SLOs.

**Anti-pattern:** route only on GPU utilization.

---

## RT-018 — Prefill/decode disaggregation is workload-dependent, not automatically superior

**State:** FRONTIER  
**Confidence:** medium-high

Disaggregation can improve isolation and utilization, but KV transfer and queueing can dominate TTFT.

**Skeleton conclusion:** keep colocated, disaggregated, deflected, and hybrid modes behind a measured serving policy.

---

## RT-019 — KV cache is a rate-distortion problem, not just a dtype choice

**State:** FRONTIER  
**Confidence:** medium-high

Recent work including *KV Cache Compression Through the Lens of Transform Coding* (arXiv:2608.14191) argues that attention-aware error allocation can outperform uniform cache quantization.

**Skeleton conclusion:** cache compression policy may depend on layer/head/channel/token importance and measured downstream distortion, not only a global bit width.

**Local experiment:** equal-memory comparison across uniform quantization, eviction, latent compression, attention-aware coding, and retrieval/recompute.

---

## RT-020 — Speculative decoding has a regime boundary

**State:** REPLICATED  
**Confidence:** high

Speculative decoding helps when acceptance is high enough and verification overhead is amortized. Work such as Speculative Verification studies adaptive verification because low acceptance or high batch/concurrency can erase gains.

**Skeleton conclusion:** enable speculation through measured policy using acceptance rate, batch size, draft cost, target cost, and concurrency.

---

## RT-021 — Model-internal memory, external retrieval, and durable user memory are different authorities

**State:** FOUNDATIONAL architecture synthesis  
**Confidence:** high

Titans/MIRAS-style neural memory and agent memory research make this distinction increasingly important.

**Skeleton conclusion:** model-internal state is MODEL_GENERATED/ephemeral unless explicitly promoted through external memory policy.

---

## RT-022 — Sparse/conditional computation must prove realized speedup

**State:** REPLICATED  
**Confidence:** high

MoE, Mixture-of-Depths, activation sparsity, and sparse attention can reduce nominal active computation, but routing, communication, padding, irregular memory access, and kernels determine actual speed.

**Skeleton conclusion:** no sparse FLOP claim becomes a system claim without wall-clock, utilization, memory, communication, and tail-latency evidence.

---

## RT-023 — MoE routing is both a model-quality and distributed-systems problem

**State:** REPLICATED  
**Confidence:** high

Expert Choice, Switch/GShard, DeepSeekMoE, MegaBlocks and later fine-grained/shared-expert designs all highlight load balance and dispatch cost.

**Skeleton conclusion:** model-internal router telemetry includes token/expert load, dropped tokens, hot experts, all-to-all time, capacity overflow, specialization, and dead experts.

---

## RT-024 — Low-bit architectures should be evaluated as native training families and deployment formats separately

**State:** FRONTIER  
**Confidence:** medium-high

BitNet-style ternary training and later low-bit/sparse work suggest train-from-scratch low-bit architectures may behave differently from post-training quantization.

**Skeleton conclusion:** keep:
1. native low-bit architecture experiments;
2. post-training quantization;
3. low-bit optimizer state;
4. low-bit KV cache
as separate evidence classes.

---

## RT-025 — Behavioral parity does not prove internal-mechanism parity after compression

**State:** FRONTIER  
**Confidence:** medium

2026 interpretability work reports that quantization/pruning can alter SAE/interpretable features even when task metrics remain close.

**Skeleton conclusion:** interpretability-derived safety/steering claims must be revalidated on the actual deployed compressed artifact.

---

## RT-026 — Mechanistic interpretability is useful but incomplete

**State:** FRONTIER  
**Confidence:** high for the limitation

Circuit Tracing and *On the Biology of a Large Language Model* (2025) demonstrate increasingly rich causal hypotheses and perturbation validation, but explicitly note missing computation, reconstruction error, graph complexity, and incomplete global understanding.

**Skeleton conclusion:** interpretability output is evidence, not proof. Require causal interventions and behavioral validation.

---

## RT-027 — Simple neuron-level circuits may remain informative

**State:** EMERGING  
**Confidence:** medium

*Language Model Circuits Are Sparse in the Neuron Basis* (arXiv:2601.22594) reports sparse causal circuits in native MLP neurons for selected tasks.

**Skeleton conclusion:** compare SAE/transcoder and raw-neuron baselines. Do not assume a learned dictionary is always necessary.

---

## RT-028 — Computer-use agents require executable-state evaluation

**State:** REPLICATED  
**Confidence:** high

OSWorld and AndroidWorld emphasize controllable executable environments and state-based evaluators rather than static imitation datasets alone.

**Skeleton conclusion:** computer-use promotion requires environment state validation, not screenshot/text similarity only.

---

## RT-029 — Agent evaluation must include recovery and partial progress, not only final success

**State:** FRONTIER synthesis  
**Confidence:** medium-high

Interactive agent benchmarks reveal long trajectories, environment stochasticity, cross-app dependencies, and action errors that one final binary metric obscures.

**Skeleton conclusion:** record:
- final outcome;
- subgoal completion;
- invalid actions;
- reversions;
- retries;
- state corruption;
- side-effect safety;
- recovery;
- cost;
- time.

---

## RT-030 — Prompt injection is an authority/dataflow problem

**State:** REPLICATED  
**Confidence:** high

AgentSecBench (arXiv:2605.26269) formalizes instruction integrity, retrieval confidentiality, and capability integrity around authorized projections and observes that prompt annotations alone do not enforce boundaries.

**Skeleton conclusion:** untrusted content cannot acquire authority through natural-language instructions. Capability restrictions and data projection happen outside generation.

---

## RT-031 — Learned safety filters cannot be the only security boundary

**State:** FOUNDATIONAL architecture conclusion  
**Confidence:** high

Adversarial prompting, prompt injection, distribution shift, and model disagreement mean model classifiers provide probabilistic evidence, not hard authorization.

**Skeleton conclusion:** deterministic capability/policy checks gate side effects.

---

## RT-032 — Data poisoning must be tested at training, retrieval, memory, and feedback boundaries

**State:** REPLICATED threat class  
**Confidence:** high

Poisoning/backdoor research plus agent memory/retrieval systems shows multiple persistence paths.

**Skeleton conclusion:** one poisoning suite spans:
- corpus;
- synthetic generator;
- preference/reward data;
- retrieval;
- memory;
- tool output;
- user corrections;
- teacher trajectories.

---

## RT-033 — Unlearning is not solved by one forgetting metric

**State:** REPLICATED negative evidence  
**Confidence:** high

MUSE (arXiv:2407.06460) and OpenUnlearning (arXiv:2506.12618) show tradeoffs across memorization, privacy leakage, retained utility, scale, and repeated removal requests.

**Skeleton conclusion:** deletion from runtime stores and approximate weight unlearning are separate problems. Never promise weight-level erasure from a memory deletion.

---

## RT-034 — Model editing and unlearning require versioned collateral-damage evaluation

**State:** REPLICATED  
**Confidence:** high

Localized edits can affect unrelated behavior and repeated unlearning may degrade utility.

**Skeleton conclusion:** every edit/unlearning candidate produces:
- target effect;
- locality;
- general capability;
- privacy extraction;
- downstream safety;
- sequential-edit stability;
- rollback artifact.

---

## RT-035 — Citation/factuality validation should be externally grounded

**State:** REPLICATED  
**Confidence:** high

Large-scale 2026 analysis of non-existent scientific citations (arXiv:2605.07723) underscores the persistence of fabricated citations in real-world knowledge production.

**Skeleton conclusion:** exact references are verified against source indexes when consequence warrants; a fluent citation string is not evidence of existence.

---

## RT-036 — Calibration is task- and population-specific

**State:** FOUNDATIONAL  
**Confidence:** high

Confidence scores drift across domains and models. Current research on uncertainty/selective prediction reinforces that one universal confidence threshold is invalid.

**Skeleton conclusion:** calibration artifacts bind task population, model/runtime version, evaluator, and date.

---

## RT-037 — Multimodal reasoning needs modality-specific provenance and evaluation

**State:** FRONTIER  
**Confidence:** high

Multimodal CoT/reasoning work spans image, video, audio, 3D, and structured input, each with different failure modes.

**Skeleton conclusion:** a shared model interface does not erase modality-specific coordinate/time/codec provenance.

---

## RT-038 — Multimodal post-training can distort perception as well as language behavior

**State:** FRONTIER  
**Confidence:** medium

Recent studies compare SFT, DPO/RL, and vision-encoder adaptation and indicate post-training may reshape visual representations, not merely response style.

**Skeleton conclusion:** multimodal post-training regression checks must test perception/grounding, not only textual preference scores.

---

## RT-039 — Formal reasoning agents benefit from generator + prover decomposition

**State:** FRONTIER  
**Confidence:** medium-high

Recent Lean/Isabelle systems increasingly coordinate natural-language strategy generation, formal proof generation, and deterministic proof checking.

**Skeleton conclusion:** formal tasks should expose proof-state/prover feedback as typed tool observations.

---

## RT-040 — Synthetic formal data is unusually valuable where verification is exact

**State:** FRONTIER  
**Confidence:** medium-high

Theorem-proving research shows synthetic proof-state exploration can create large verified corpora.

**Skeleton conclusion:** prioritize synthetic data where an independent checker can label correctness cheaply and exactly.

---

## RT-041 — Benchmark contamination changes what "progress" means

**State:** REPLICATED  
**Confidence:** high

Static web-available benchmarks can enter pretraining or tuning corpora. BRIGHT and newer dynamic/controlled evaluations illustrate attempts to reduce this.

**Skeleton conclusion:** EvaluationRegistry records contamination risk and separates public development sets from blind promotion holdouts.

---

## RT-042 — Benchmark saturation is different from contamination

**State:** FOUNDATIONAL evaluation principle  
**Confidence:** high

A clean benchmark can cease to discriminate models if nearly all candidates score similarly.

**Skeleton conclusion:** monitor variance, headroom, task realism, and error diversity; retire or downweight saturated benchmarks.

---

## RT-043 — Negative results must be first-class research assets

**State:** FOUNDATIONAL scientific principle  
**Confidence:** high

Architecture research repeatedly rediscoveries methods when failures are undocumented.

**Skeleton conclusion:** failed reproductions, no-gain ablations, instability, and portability failures remain queryable in the evidence graph.

---

## RT-044 — Cross-paper consensus must account for shared lineage

**State:** FOUNDATIONAL evidence principle  
**Confidence:** high

Papers may share code, benchmarks, base models, data, authors, or hidden provider dependencies.

**Skeleton conclusion:** evidence independence is a graph property, not citation count.

---

## RT-045 — Provider/model semantic drift can invalidate old experiments without an API change

**State:** REPLICATED systems principle  
**Confidence:** high

Hosted models can change routing, safety layers, decoding, or backend revisions.

**Skeleton conclusion:** remote-provider experiment evidence records provider model identifier, observed version where available, date, config, and semantic canaries.

---

# 2. Architecture research map

## 2.1 Dense Transformer baseline — FOUNDATIONAL

Still mandatory as a stable baseline because:
- mature kernels;
- mature parallelism;
- broad hardware support;
- strong reproduction base;
- understood cache model.

Research debt:
- current repo needs an explicit baseline configuration family against which exotic/sparse/hybrid candidates can be compared.

## 2.2 Sparse attention — FRONTIER

Research axes:
- fixed/local windows;
- block sparse;
- content-routed sparse;
- hierarchical compression/selection;
- hardware-native sparse patterns;
- shared cross-layer routing.

Key risks:
- retrieval miss;
- route overhead;
- irregular kernels;
- long-range degradation;
- difficult debugging;
- route instability.

Mandatory experiment:
exact-attention control at equal token budget and equal wall-clock.

## 2.3 State-space/recurrent families — FRONTIER

Mamba-style selective state-space models and hybrid architectures demonstrate credible alternatives to pure attention.

Research questions:
- where is recurrence superior under streaming?
- how much global attention remains necessary?
- how does hidden state survive reset/migration?
- what is the long-range associative-memory quality?
- how does state corruption recover?

Skeleton hook:
ModelPort must not assume KV-cache-only sequence state.

## 2.4 Hybrid attention + recurrence — FRONTIER

Strong candidate because hybrid models can retain occasional global attention while reducing cache/compute.

Experiment matrix:
- attention ratio by layer;
- state size;
- latency;
- long-context retrieval;
- generation quality;
- streaming;
- state reset;
- tool/structured output.

## 2.5 MoE — REPLICATED

Open questions:
- expert granularity;
- shared experts;
- routing objective;
- capacity;
- expert parallel topology;
- expert lifecycle;
- load balancing under real traffic.

System measurement:
expert all-to-all time often matters as much as active FLOPs.

## 2.6 Recurrent depth / equilibrium — EMERGING/FRONTIER

Potentially changes test-time scaling by allowing hidden computation to deepen without emitting extra tokens.

Unknowns:
- convergence;
- overthinking;
- training stability;
- interpretability;
- tail latency;
- checkpoint semantics.

Keep in Track AC until reproduced.

---

# 3. Data research map

## 3.1 Source quality

Research consensus:
quality filtering helps, but filters encode bias and can remove rare/high-value data.

Required logging:
- source;
- language;
- quality filter version;
- removed fraction;
- reason distribution;
- downstream domain effect.

## 3.2 Deduplication

Benefits:
- less memorization;
- less benchmark overlap;
- better token efficiency.

Risks:
- false positives remove legitimate repeated structures;
- semantic duplicates survive lexical dedupe;
- aggressive dedupe changes frequency priors.

Experiment:
exact, MinHash, semantic-near-dedupe, and no-dedupe controls.

## 3.3 Data mixtures

Treat weights as learned/validated hyperparameters.

Never:
- infer mixture quality from dataset size;
- change mixture without creating a new manifest;
- compare models whose mixtures differ without noting it.

## 3.4 Curriculum

Candidate axes:
- quality;
- difficulty;
- domain;
- sequence length;
- synthetic/natural ratio;
- modality;
- code/math density.

Research maturity: MIXED. Curriculum gains are often regime-dependent.

## 3.5 Synthetic data

Separate:
- rephrasing;
- textbook generation;
- reasoning traces;
- verified code/proofs;
- self-instruction;
- adversarial cases;
- preference pairs;
- simulated tool trajectories.

Each has different collapse and contamination behavior.

---

# 4. Training and optimization research map

## 4.1 Stable optimizer baseline

AdamW remains the mandatory reference for most Transformer-like experiments.

## 4.2 Structure-aware optimizers

Shampoo/SOAP/Sophia/Muon/GaLore families deserve controlled evaluation but not universal default status.

Research questions:
- quality at equal tokens;
- wall-clock;
- optimizer memory;
- communication;
- scale transfer;
- sensitivity;
- checkpoint complexity.

## 4.3 Precision

Separate:
- compute precision;
- activation precision;
- gradient precision;
- optimizer-state precision;
- communication precision;
- KV precision.

A system saying "FP8 training" is incomplete unless all six are described.

## 4.4 Distributed training

Research axes:
- data parallel;
- tensor parallel;
- pipeline;
- sequence/context;
- expert;
- optimizer/state sharding.

The optimal composition depends on model architecture and physical network topology.

---

# 5. Post-training research map

## 5.1 SFT — FOUNDATIONAL

Strengths:
- stable;
- interpretable dataset link;
- good for behavior acquisition.

Weaknesses:
- can memorize traces;
- distribution mismatch;
- limited exploration.

## 5.2 Preference optimization — REPLICATED but method-dependent

DPO and related methods simplify preference training but remain sensitive to preference distribution and reference policy.

Skeleton rule:
algorithm is plugin; preference data lineage is first-class.

## 5.3 RLVR — FRONTIER

High-value where reward is independently checkable:
- math;
- code;
- formal proof;
- constrained tool tasks.

Less certain:
- general factual QA;
- subjective writing;
- open-ended planning.

## 5.4 Reward models — MIXED

Risks:
- style bias;
- reward hacking;
- distribution shift;
- correlated failure with policy;
- overconfidence.

Use RewardBench/RM-style challenge sets and independent deterministic checks where possible.

---

# 6. Reasoning/test-time compute map

Reasoning strategies are categorized along four dimensions:

1. **breadth** — independent candidates;
2. **depth** — sequential revision or recurrence;
3. **decomposition** — subproblem structure;
4. **verification** — candidate scoring/checking.

Every method is a point in this space.

Research rule:
do not compare "reasoning" methods at unequal total compute without reporting both quality and resource use.

Required metrics:
- success;
- compute;
- latency;
- tokens;
- tool calls;
- verifier calls;
- candidate diversity;
- calibration;
- failure type;
- marginal gain per extra compute unit.

---

# 7. Retrieval and context map

Mandatory baselines:
- BM25;
- dense retrieval;
- hybrid sparse+dense;
- long context with no retrieval.

Optional challengers:
- reranking;
- query decomposition;
- reasoning-enhanced retrieval;
- graph RAG;
- agentic/file-system search.

Research rule:
complex retrieval must beat simple lexical/hybrid baselines on a corpus-size ladder.

---

# 8. Memory map

Memory lifecycle:

```text
observe
 -> candidate
 -> classify
 -> validate
 -> write
 -> consolidate
 -> retrieve
 -> revise
 -> forget/tombstone
```

Evaluation families:
- factual recall;
- reflective/procedural memory;
- temporal update;
- contradiction;
- selective forgetting;
- prospective intentions;
- capacity;
- privacy;
- poison resistance.

Research debt:
Skeleton needs a benchmark that combines memory with consequential tool actions.

---

# 9. Agent research map

## 9.1 Tool-use agents

Evaluate:
- correct tool selection;
- correct arguments;
- recovery;
- authority;
- idempotency;
- observation interpretation.

## 9.2 Computer-use agents

Executable environment required.

Measure:
- task success;
- steps;
- invalid actions;
- state damage;
- time;
- recovery;
- cross-app behavior.

## 9.3 Multi-agent systems

Evidence for benefits is highly task-dependent.

Risks:
- duplicated work;
- correlated errors;
- communication overhead;
- authority amplification;
- deadlock;
- social consensus around wrong answer.

Mandatory baseline:
single strong agent with equal total compute.

---

# 10. Serving research map

## 10.1 Scheduler

Inputs:
- prompt length;
- predicted generation length;
- cache locality;
- KV bytes;
- prefill load;
- decode load;
- network distance/congestion;
- tenant/QoS;
- model/adapter locality.

## 10.2 KV management

Candidates:
- paging;
- prefix caching;
- quantization;
- transform coding;
- latent KV;
- eviction;
- offload;
- recompute.

## 10.3 Disaggregation

Compare:
- colocated;
- static P/D;
- dynamic P/D;
- prefill deflection;
- cross-cluster prefill.

## 10.4 Speculation

Policy inputs:
- draft acceptance;
- sequence length;
- batch size;
- target saturation;
- memory;
- network;
- draft/target placement.

---

# 11. Evaluation research map

Evaluation must separate:

- capability;
- robustness;
- calibration;
- safety/security;
- latency/cost;
- recovery;
- long-horizon behavior;
- contamination.

Evaluation evidence classes:

1. deterministic execution/checker;
2. curated benchmark;
3. dynamic benchmark;
4. simulation;
5. blind internal holdout;
6. production observation;
7. human evaluation;
8. learned evaluator.

None is sufficient alone for all claims.

---

# 12. Interpretability research map

Current credible techniques:
- probing;
- causal intervention;
- activation patching;
- sparse autoencoders;
- transcoders;
- attribution graphs;
- circuit tracing;
- neuron/circuit sparsity analysis.

Required distinction:
- correlational feature;
- causally influential feature;
- sufficient mechanism;
- complete mechanism.

Skeleton must never collapse these labels.

Deployment caveat:
quantization/pruning/architecture surgery can invalidate interpretability maps.

---

# 13. Security/privacy research map

Threat families:
- direct prompt injection;
- indirect prompt injection;
- capability escalation;
- retrieval poisoning;
- memory poisoning;
- tool-output poisoning;
- secret extraction;
- membership inference;
- training-data extraction;
- malicious files/parsers;
- cross-tenant cache leakage;
- agent impersonation;
- supply-chain compromise.

Research conclusion:
security boundary lives in policy/capability/dataflow enforcement, not in a prompt telling the model to behave.

---

# 14. Unlearning and deletion map

Four distinct operations:

1. delete from active context;
2. delete from external memory/index;
3. prevent use through policy/routing;
4. modify model weights to reduce learned influence.

These are not equivalent.

Weight-level unlearning evidence reports:
- target forgetting;
- extraction attack;
- retained utility;
- privacy leakage;
- sequential requests;
- scale;
- retraining baseline where feasible.

---

# 15. Multimodal map

Representation classes:
- tokenized discrete;
- continuous latent;
- patch/frame;
- event/temporal;
- graph/3D.

Evaluation:
- perception;
- grounding;
- temporal reasoning;
- cross-modal consistency;
- hallucination;
- tool/action;
- provenance retention.

A text-quality win cannot compensate for perception regression.

---

# 16. Formal methods map

Formal verification opportunities in Skeleton:

- config invariants;
- state machines;
- tool transaction protocol;
- migration compatibility;
- resource bounds;
- workflow safety properties;
- generated code;
- selected algorithmic answers;
- theorem proving.

Use strongest economical evidence:
schema/type → property test → fuzz → model check → SMT/proof assistant.

---

# 17. Research anti-canon

The following statements are explicitly unsupported as universal truths:

- larger model always beats better data;
- synthetic data can replace natural data without conditions;
- more reasoning tokens always improve accuracy;
- RLVR always creates better reasoning;
- verifier score is truth;
- long context makes retrieval obsolete;
- graph RAG always beats lexical retrieval;
- more agents beat one agent;
- sparse FLOPs equal wall-clock speed;
- quantized model behavior parity means same internal mechanisms;
- prompt instructions enforce security boundaries;
- deleting external memory erases model knowledge;
- one benchmark establishes SOTA;
- one successful reproduction proves scale transfer;
- a frontier paper is production-ready;
- a negative result is unimportant.

---

# 18. Contradiction register

## CR-001 — Does RLVR create genuinely improved reasoning?

Supporting:
- many task-accuracy gains;
- CoT-Pass@K work argues RLVR can incentivize correct reasoning.

Contradicting/narrowing:
- arXiv:2604.22074 finds outcome reward does not guarantee causally important/sufficient reasoning;
- arXiv:2603.20799 finds general-QA transfer is weak.

Resolution status: **MIXED**.

Skeleton experiment:
train matched SFT/RLVR variants and evaluate answer accuracy, process correctness, causal perturbation, diversity, calibration, and cross-domain transfer.

## CR-002 — Is long context better than retrieval?

Supporting LC:
- avoids retrieval miss;
- retains global context.

Supporting RAG:
- lower input cost;
- explicit provenance;
- selective freshness;
- may outperform at scale.

Resolution: **task-conditional**.

## CR-003 — Does synthetic data cause model collapse?

Supporting risk:
- recursive/pure generated distributions can narrow support.

Narrowing:
- rephrased synthetic mixtures with real anchors can improve efficiency.

Resolution: **generation-process and mixture dependent**.

## CR-004 — Are sparse autoencoders necessary for circuits?

Supporting:
- useful interpretable feature decomposition and circuit tracing.

Narrowing:
- arXiv:2601.22594 reports native neuron basis can be sparse enough for selected circuits.

Resolution: **method/task dependent**.

## CR-005 — Is P/D disaggregation the serving default?

Supporting:
- resource isolation and independent scaling.

Narrowing:
- KV/network transfer and queueing can dominate; deflection/colocation may win.

Resolution: **workload/topology dependent**.

---

# 19. Research debt register

Research debt is a claim Skeleton currently relies on conceptually but has not yet validated locally.

## RD-001 — ModelPort portability
Need at least two materially different model families running the same conformance suite.

## RD-002 — Retrieval routing
Need corpus-size ladder across BM25/dense/hybrid/LC/graph/agentic.

## RD-003 — Reasoning allocator
Need measured difficulty→strategy policy.

## RD-004 — Verifier independence
Need explicit lineage graph and correlated-failure tests.

## RD-005 — Memory revision
Need contradiction, temporal update, forgetting, prospective-intention benchmark.

## RD-006 — Agent authority
Need indirect-injection and capability-integrity testbed.

## RD-007 — Serving topology
Need colocated vs disaggregated vs deflected benchmark.

## RD-008 — KV compression
Need downstream attention-aware quality tests, not reconstruction error alone.

## RD-009 — Optimizer challenger transfer
Need small→medium scale transfer matrix.

## RD-010 — Low-precision long-horizon stability
Need full-duration FP8/experimental FP4 stability runs.

## RD-011 — Interpretability portability
Need compare full precision vs quantized/pruned artifact explanations.

## RD-012 — Unlearning
Need explicit promise boundary between runtime deletion and weight unlearning.

## RD-013 — Synthetic data
Need ancestry-depth and mixture-ratio experiments.

## RD-014 — Formal verification
Need select high-value state machines suitable for model checking/proof.

## RD-015 — Exotic architecture
Need cheap falsification queue before large-scale training.

---

# 20. Local reproduction ladder

Every frontier claim enters one of these stages:

```text
R0 source verified
R1 implementation inspected
R2 toy reproduction
R3 matched baseline reproduction
R4 scale-transfer reproduction
R5 systems/full-stack reproduction
R6 adversarial/failure reproduction
R7 independent environment/hardware reproduction
R8 promotion evidence
```

No claim is called "locally reproduced" from R0/R1 only.

---

# 21. Evidence independence graph

Record edges:

- same authors;
- same codebase;
- same benchmark;
- same base model;
- same training corpus;
- same evaluator;
- same provider;
- same hardware/runtime;
- direct derivative method;
- copied result.

Consensus score must discount correlated evidence.

---

# 22. Research experiment templates

## Template A — algorithm claim

- hypothesis;
- strongest tuned baseline;
- equal-token result;
- equal-wall-clock result;
- memory;
- sensitivity;
- seed variance;
- scale transfer;
- negative cases.

## Template B — systems claim

- topology;
- workload distribution;
- concurrency;
- tail latency;
- throughput;
- memory;
- network;
- cost;
- failure recovery;
- overload.

## Template C — agent claim

- environment;
- task population;
- tool authority;
- success;
- invalid actions;
- side effects;
- recovery;
- injection;
- cost;
- long-horizon drift.

## Template D — memory claim

- write policy;
- retrieval;
- update;
- contradiction;
- forgetting;
- prospective memory;
- privacy;
- poison;
- latency;
- capacity.

## Template E — safety/security claim

- threat model;
- attacker capability;
- protected assets;
- policy boundary;
- benign-control cost;
- attack success;
- adaptive attack;
- failure mode;
- residual risk.

---

# 23. Research priority queue

Priority is expected information gain for Skeleton, not hype.

## P0-R — architecture-foundation experiments

1. BM25/dense/hybrid/LC retrieval ladder.
2. memory contradiction/update/forgetting/prospective benchmark.
3. test-time compute strategy curves with verifier-budget split.
4. indirect prompt-injection/capability-integrity suite.
5. colocated vs disaggregated serving with network-aware scheduling.
6. synthetic/natural data mixture study.
7. optimizer baseline vs Muon/Shampoo/GaLore challenger matrix.
8. KV compression downstream-quality study.
9. state/schema rollback fault campaign.
10. evaluator contamination/firewall verification.

## P1-R — frontier systems

11. recurrent-depth toy model;
12. request-local Titans-style neural memory;
13. byte-latent representation prototype;
14. ternary/sparse kernel reality check;
15. differential/sparse attention comparison;
16. formal workflow-state verification;
17. quantization-vs-interpretability transfer study;
18. unlearning benchmark integration;
19. multimodal provenance conformance;
20. multi-agent vs single-agent equal-compute comparison.

---

# 24. Research refresh cadence

Research is rechecked when:

- 90 days pass for a frontier/emerging default recommendation;
- new independent replication appears;
- major critique or retraction appears;
- code/weights become available;
- benchmark correction is published;
- hardware generation changes;
- a local reproduction fails;
- a stronger baseline appears;
- production telemetry contradicts experiment assumptions.

High-volatility areas receive shorter refresh windows:

- test-time reasoning;
- RLVR/post-training;
- agents;
- serving;
- low precision;
- exotic architecture.

Foundational results refresh less frequently but are still revisited if the surrounding system changes.

---

# 25. Research completion standard

The research pass is complete for a domain only when Skeleton has:

- foundational anchors;
- current frontier sources;
- negative results;
- contradiction register;
- evidence maturity;
- implementation hooks;
- strongest baseline;
- local falsification experiment;
- scale/hardware scope;
- security/authority consequences;
- refresh trigger.

"Read a lot of papers" is not completion.

The intended output is a **living scientific control plane**: fast at discovering ideas, skeptical when interpreting them, aggressive about cheap falsification, and slow about promoting architectural truth.
