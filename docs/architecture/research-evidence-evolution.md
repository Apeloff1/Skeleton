# Research Evidence and Architecture Evolution

Status: canonical architecture input
Updated: 2026-09-21

## Mission

Turn historical and frontier AI research into reproducible, reversible improvements to Skeleton without letting papers, benchmarks, models, or research agents silently rewrite production behavior.

This plane extends the existing SOTA Absorb Engine and Adaptive Absorption Fabric. It does not replace either. Research publications are a specialized evidence source; architecture changes are promoted only through explicit experiments and architecture decisions.

## 1. Non-negotiable separation

```text
RESEARCH SOURCES
    |
    v
ResearchEvidence
    |
    v
Claim + provenance graph
    |
    v
Experiment candidate
    |
    v
Reproduction / prototype / benchmark / ablation / challenge
    |
    v
Architecture Decision Record
    |
    v
Shadow -> canary -> promotion
    |
    v
VERSIONED PRODUCTION CONTRACT

SERVING ------------------------------------------+
  ^                                                 |
  +------ immutable promoted state / receipts ------+
```

Research may propose. Evaluation may measure. Promotion may change production.

No other path is valid.

## 2. ResearchEvidence schema

Every paper, implementation, replication, benchmark, or negative result should normalize into an object with at least:

```text
evidence_id
source_type
title
authors[]
identifier
source_version
published_at
retrieved_at
venue
peer_review_state
canonical_url
artifact_urls[]
claims[]
applies_to[]
baselines[]
datasets[]
task_population
hardware
training_budget
inference_budget
context_length
ablations[]
metrics{}
code_available
weights_available
license
replications[]
contradictions[]
known_limitations[]
maturity
confidence
reproducibility
promotion_status
provenance_digest
```

The schema must preserve the population and experimental conditions of a result. A result on one benchmark or scale is not generalized to another without evidence.

## 3. Evidence states

- `foundational` — long-lived result with broad downstream support.
- `replicated` — independently reproduced or strongly corroborated.
- `frontier` — strong recent evidence, still requiring local validation.
- `emerging` — promising result with limited validation or review.
- `mixed` — credible results disagree.
- `negative` — a null result, counterexample, failure boundary, or disproven assumption.
- `superseded` — retained for lineage but no longer preferred.

Evidence state is not a quality score. A negative result can be extremely valuable because it closes a dangerous design path.

## 4. Source adapters

Initial scientific adapters should cover:

- arXiv metadata and version history;
- OpenReview forum, revision, decision, and review metadata;
- ACL Anthology;
- NeurIPS, ICML, ICLR, CVPR and other official proceedings;
- ACM and IEEE proceedings where relevant;
- peer-reviewed journals;
- official technical reports and model/system cards;
- official or author-linked source repositories;
- reproducibility studies;
- benchmark leaderboards with exact task/version identity;
- errata, retractions, critiques, and negative results.

The adapter must retain the original identifier and version. A revised arXiv paper is a new evidence version, not an invisible overwrite.

## 5. Historical and frontier research map

The following works anchor design families. Inclusion means “must be understood and tested where relevant”, not “must be implemented exactly”.

| Family | Anchor | Identifier | Skeleton implication |
| --- | --- | --- | --- |
| Attention | Vaswani et al., *Attention Is All You Need* | arXiv:1706.03762 | Transformer-compatible model substrate; attention remains an implementation, not a kernel invariant |
| Scaling | Kaplan et al., *Scaling Laws for Neural Language Models* | arXiv:2001.08361 | explicit model/data/compute accounting |
| Compute-optimal training | Hoffmann et al., *Training Compute-Optimal Large Language Models* | arXiv:2203.15556 | training planner balances parameters and data rather than maximizing parameter count |
| Retrieval generation | Lewis et al., *Retrieval-Augmented Generation* | arXiv:2005.11401 | retrieval is a first-class knowledge path with provenance |
| Retrieval pretraining | Borgeaud et al., *Improving language models by retrieving from trillions of tokens* | arXiv:2112.04426 | external memory can substitute for some parametric capacity |
| Reasoning diversity | Wang et al., *Self-Consistency Improves Chain of Thought Reasoning* | arXiv:2203.11171 | multi-trajectory reasoning is an optional budgeted mode |
| Reason + action | Yao et al., *ReAct* | arXiv:2210.03629 | reasoning and tool observations form an explicit loop |
| Learned tool use | Schick et al., *Toolformer* | arXiv:2302.04761 | models may propose tools; authority remains external |
| Search over thoughts | Yao et al., *Tree of Thoughts* | arXiv:2305.10601 | bounded search/backtracking mode for suitable tasks |
| Instruction tuning / RLHF | Ouyang et al., *Training language models to follow instructions with human feedback* | arXiv:2203.02155 | post-training is a distinct, evaluated stage |
| Preference optimization | Rafailov et al., *Direct Preference Optimization* | arXiv:2305.18290 | preference algorithms sit behind a training contract |
| Serving memory | Kwon et al., *Efficient Memory Management for Large Language Model Serving with PagedAttention* | arXiv:2309.06180 | KV memory is explicitly scheduled and measured |
| State-space models | Gu & Dao, *Mamba* | arXiv:2312.00752 | model contract must permit non-attention sequence substrates |
| Hybrid architecture | Lieber et al., *Jamba* | arXiv:2403.19887 | hybrid attention/SSM/MoE implementations must fit the same ModelPort |
| Sparse experts | Dai et al., *DeepSeekMoE* | arXiv:2401.06066 | distinguish model-internal expert routing from system/provider routing |
| Instruction privilege | Wallace et al., *The Instruction Hierarchy* | arXiv:2404.13208 | context carries explicit trust/authority labels |
| Software agents | Jimenez et al., *SWE-bench* | arXiv:2310.06770 | evaluate repository-level engineering, not only snippets |
| Computer agents | Xie et al., *OSWorld* | arXiv:2404.07972 | evaluate long-horizon computer interaction in realistic environments |
| Adaptive inference | Snell et al., *Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters* | OpenReview:4FWAwZtd2n | allocate inference compute by difficulty and verifier reliability |

New work is added to the registry through evidence ingestion, not by hand-editing a “SOTA” label into production code.

## 6. Model substrate contract

The architecture must remain agnostic to dense Transformer, sparse Transformer, SSM, hybrid, MoE, adapter-heavy, and future model families.

A future `ModelPort` should expose capabilities comparable to:

```python
prefill(...)
decode(...)
score(...)
embed(...)
estimate_compute(...)
estimate_memory(...)
inspect_cache(...)
checkpoint(...)
restore(...)
capabilities(...)
```

Optional model-internal operations such as expert routing must not leak into system-level routing semantics.

### Promotion requirements

A new model family or kernel is promoted only when evaluated on:

- task quality;
- calibration;
- long-context behavior;
- tool/structured-output behavior;
- latency and time-to-first-token;
- decode throughput;
- peak and steady-state memory;
- cache behavior;
- concurrency;
- hardware portability;
- failure and recovery;
- cost per successful task.

## 7. Compute and scaling planner

Training and inference must have separate budgets.

The planner tracks at minimum:

- training tokens;
- parameter count / active parameter count;
- optimizer and activation memory;
- training FLOPs;
- post-training FLOPs;
- inference prefill FLOPs;
- decode FLOPs;
- memory bandwidth;
- interconnect/communication;
- KV-cache bytes;
- storage;
- wall-clock latency;
- energy when observable;
- monetary cost;
- expected lifetime inference volume.

The optimization target is system utility under constraints, not parameter count.

## 8. Adaptive reasoning controller

Reasoning depth must be selected, not assumed.

Required modes:

- direct;
- single deliberate trajectory;
- self-consistency;
- decomposition;
- parallel candidates;
- search/backtracking;
- verifier-guided search;
- tool-assisted investigation;
- mixed strategy.

`ReasoningBudgetAllocator` inputs should include:

- task class;
- estimated difficulty;
- uncertainty;
- consequence/risk;
- evidence availability;
- verifier reliability;
- latency SLO;
- token/compute ceiling;
- tool cost;
- previous failed attempts.

Outputs control breadth, depth, retries, candidate count, tool allowance, and verification strength.

A harder-looking task does not automatically deserve unlimited compute. Additional compute must demonstrate marginal value.

## 9. Hierarchical memory and context compiler

Skeleton should distinguish:

- **working memory** — active context for the current operation;
- **episodic memory** — prior attempts, interactions, observations, and outcomes;
- **semantic memory** — distilled facts, concepts, entities, and relations;
- **procedural memory** — verified methods, workflows, skills, and tool sequences.

No class silently overwrites another.

The context compiler chooses among:

- direct parametric knowledge;
- retrieval;
- long-context inclusion;
- compression;
- summaries;
- tool lookup;
- abstention / further research.

Every inserted context item carries provenance and trust.

## 10. Trust and instruction hierarchy

Recommended trust labels:

```text
SYSTEM_AUTHORITY
DEVELOPER_POLICY
USER_INTENT
TRUSTED_TOOL_DATA
UNTRUSTED_EXTERNAL_DATA
MODEL_GENERATED
MEMORY_UNVERIFIED
MEMORY_VERIFIED
```

Trust labels describe authority, not factual correctness.

Retrieved webpages, papers, files, tool output, model output, and memory cannot acquire system authority merely by containing imperative text.

## 11. Tool execution contract

The canonical side-effect sequence is:

```text
ToolIntent
  -> capability check
  -> policy / authorization
  -> argument validation
  -> risk / approval gate
  -> ValidatedToolCall
  -> execution
  -> ToolExecutionReceipt
  -> observation
  -> verification
```

Required properties:

- least privilege;
- explicit identity and capability;
- idempotency where feasible;
- bounded retry;
- cancellation;
- timeout;
- resource budget;
- durable receipt for meaningful side effects;
- output treated as observation;
- replay-safe recovery.

## 12. Verifier architecture

No single learned verifier becomes a truth oracle.

Verifier evidence classes include:

- compiler/type checker;
- schema validation;
- deterministic algorithmic checker;
- unit/integration tests;
- property tests;
- fuzzing;
- simulator;
- source/provenance validation;
- independent model critic;
- process verifier;
- outcome verifier;
- formal proof / model checking where justified;
- human approval for configured high-impact operations.

Each result should record:

```text
verifier_id
verifier_version
verification_scope
evidence
verdict
confidence
failure_modes
independence_class
cost
```

Multiple verifiers derived from one base model or one shared evidence source do not count as fully independent evidence.

## 13. Inference and serving architecture

The serving decomposition should support:

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
 -> receipt / telemetry
```

Hardware adapters may include CPU, CUDA, ROCm, DirectML/Windows, remote providers, and future accelerators.

The runtime chooses profiles from measured capability and policy rather than hard-coding one hardware assumption.

## 14. Three adaptation velocities

### Fast

May update:

- working context;
- episodic memory;
- routing choice;
- temporary procedure selection.

Does not change model weights.

### Medium

May update after validation:

- retrieval indexes;
- semantic/procedural memory;
- prompts;
- skills;
- adapters;
- routing policies;
- caches.

### Slow

May update through controlled training:

- base weights;
- continual pretraining;
- supervised fine-tuning;
- preference optimization;
- reinforcement learning;
- distillation.

Production interaction never directly mutates deployed weights.

## 15. Experiment contract

Every architecture experiment declares before execution:

```text
experiment_id
hypothesis
target_contract
candidate
baseline
datasets/tasks
population
metrics
hard_floors
resource_budget
seed_policy
hardware/software environment
ablation_plan
adversarial_plan
stop_conditions
rollback_plan
owner
```

Results must retain raw evidence or reproducible references to it.

A benchmark win that violates a hard floor is a failed candidate.

## 16. Evaluation matrix

Evaluation spans capability and system behavior.

### Capability

- knowledge/retrieval;
- reasoning;
- code/repository work;
- tool use;
- multimodal behavior where supported;
- long-context;
- planning;
- memory;
- instruction following.

### System

- correctness;
- calibration;
- latency;
- throughput;
- concurrency;
- memory;
- cost;
- energy when available;
- cancellation;
- retries;
- crash recovery;
- provider outage;
- partial dependency outage;
- malformed model output;
- stale cache/state;
- context overflow;
- prompt injection;
- retrieval poisoning;
- privilege escalation;
- infinite loops;
- runaway test-time compute;
- verifier collusion/correlated error.

### Regression

Every promoted change receives a permanent regression case for the behavior that justified it and any important failure discovered during challenge.

## 17. Promotion state machine

```text
DISCOVERED
  -> NORMALIZED
  -> TRIAGED
  -> REPRODUCTION_PENDING
  -> REPRODUCED | REPRODUCTION_FAILED
  -> PROTOTYPED
  -> BENCHMARKED
  -> CHALLENGED
  -> ADR_ACCEPTED
  -> SHADOW
  -> CANARY
  -> PROMOTED
```

Side exits:

```text
REJECTED
CONTESTED
SUPERSEDED
RETRACTED
QUARANTINED
```

Promotion requires a reproducible evidence bundle and rollback target.

## 18. Architecture Decision Record requirements

An ADR generated from research must contain:

- problem and current limitation;
- candidate and alternatives;
- evidence graph;
- replication status;
- local experiment results;
- ablation results;
- contradictory evidence;
- system-level tradeoffs;
- security implications;
- compatibility/migration plan;
- rollback;
- monitoring;
- expiration/review date.

This converts “we saw a paper” into an auditable engineering decision.

## 19. Continuous scientific refresh

Research evidence decays operationally even when the paper itself does not change.

Refresh triggers include:

- new paper version;
- venue decision;
- independent replication;
- major critique;
- benchmark correction;
- code release;
- model release;
- hardware generation change;
- dependency or API change;
- internal regression;
- cheaper/better competing method.

A refresh can strengthen, weaken, supersede, or retract an architecture recommendation.

## 20. Definition of SOTA inside Skeleton

“SOTA” is not a permanent badge.

For Skeleton it means:

> the best currently validated choice for a named objective, population, hardware/software envelope, risk policy, and cost budget, measured against explicit alternatives.

Every SOTA statement therefore needs:

- scope;
- date;
- evidence version;
- baseline;
- metric;
- constraints;
- uncertainty;
- refresh policy.

This definition prevents benchmark fashion from becoming architecture debt.


## 21. Exotic architecture evidence contract

Track AC candidates receive additional evidence fields because conventional model evidence is insufficient for architectures with mutable inference state, non-autoregressive decoding, dynamic depth, implicit convergence, generated weights, or unusual hardware.

Required fields:

```text
exotic_candidate_id
challenged_assumption
architecture_family
evidence_tier
persistent_state
ephemeral_state
inference_time_mutation
mutation_scope
reset_semantics
convergence_or_stop_rule
tentative_output_semantics
commit_rule
representation_dependency
hardware_specialization
strongest_conventional_baseline
falsification_test
kill_criteria
compound_components[]
component_ablation_status
track_ab_compatibility
track_aa_graduation_status
```

### Exotic evidence defaults

- a new exotic idea begins as `emerging` or `mixed`, not `frontier` by declaration;
- a microbenchmark cannot raise evidence maturity by itself;
- theoretical asymptotic improvement without measured hardware benefit is scoped as theory/system-potential evidence;
- mutable inference-time state requires replay/reset evidence before any persistent use;
- non-autoregressive or revise-anywhere generation must prove commit semantics before tool/action integration;
- recursive/equilibrium methods must record non-convergence and tail-iteration behavior, not only average quality;
- compound candidates must report component ablations;
- architecture-search outputs inherit the evidence maturity of their evaluation procedure and cannot validate themselves.

### Graduation rule

```text
Track AC research
 -> reproduced candidate
 -> falsification survived
 -> full-stack systems evidence
 -> Track AB compatibility
 -> Track AA candidate
 -> normal shadow/canary/promotion state machine
```

There is no direct AC → production edge.

## 22. Research refresh for exotic candidates

Exotic evidence receives additional refresh triggers:

- new independent scale reproduction;
- failure to transfer to a larger scale;
- new kernel/hardware support;
- revised convergence analysis;
- new cross-session/state leakage finding;
- tokenizer/representation incompatibility;
- new conventional baseline that removes the claimed advantage;
- composition failure with another promoted subsystem;
- architecture simplification showing the exotic component was unnecessary.

A simpler architecture that matches an exotic candidate's measured benefit is preferred unless the exotic candidate retains another material full-stack advantage.
