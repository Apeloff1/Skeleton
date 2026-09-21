# Exotic Architecture Laboratory

Status: canonical research architecture manual  
Updated: 2026-09-21  
Track: AC  
Authority: research-only; no direct production promotion

## 1. Mission

Explore architectures that could move Skeleton beyond the standard assumptions of a tokenized, autoregressive, fixed-depth, dense Transformer with immutable inference-time weights.

The laboratory is intentionally broad but mechanically strict.

An exotic candidate is valuable only if it answers:

1. Which current assumption does it challenge?
2. What measurable bottleneck does that assumption create?
3. What is the smallest experiment that could falsify the proposed alternative?
4. What new failure modes appear?
5. What state does the candidate create or mutate?
6. Can the candidate be reset, replayed, checkpointed and isolated?
7. What happens to serving, security, provenance, recovery and tooling?
8. Does the advantage survive equal-cost comparison against a tuned conventional baseline?

Novelty is not an objective.

---

# 2. Architecture coordinate system

Rather than treat each paper as an indivisible architecture, describe a candidate across orthogonal axes.

## 2.1 Representation axis

Candidates:

- fixed subword/token vocabulary;
- raw bytes;
- learned dynamic byte patches;
- characters;
- learned semantic chunks;
- continuous latent vectors;
- modality-specific continuous latents;
- graph/entity/event units;
- hybrid discrete + continuous units.

Required identity:

```text
RepresentationSpec
 -> encoder/version
 -> normalization
 -> segmentation/patching
 -> special/control units
 -> decode semantics
 -> compatibility class
```

The representation axis must be separable from the model-family axis where possible.

## 2.2 Compute-depth axis

Candidates:

- fixed feed-forward depth;
- conditional token depth;
- recurrent shared depth;
- partial recurrence;
- fixed-point/equilibrium depth;
- local iterative update rules;
- architecture-selected dynamic graphs.

Every non-fixed-depth candidate declares:

- max depth/iterations;
- stop/convergence rule;
- minimum work;
- tail behavior;
- non-convergence fallback;
- deterministic debug mode.

## 2.3 Attention/state axis

Candidates:

- dense attention;
- local/window attention;
- hardware-native sparse attention;
- differential attention;
- cross-layer shared routing;
- compressed/latent KV;
- state-space/recurrent state;
- learned long-term neural memory;
- graph relational state;
- hybrid combinations.

## 2.4 Memory/write axis

Candidates:

- no mutable neural state;
- KV/cache only;
- recurrent hidden state;
- bounded learned memory;
- fast weights;
- generated adapters;
- temporary experts;
- external retrieval;
- durable Skeleton memory.

The last item is a separate authority plane.

Internal state never inherits durable-memory trust merely because it persists for more than one token.

## 2.5 Generation axis

Candidates:

- autoregressive token generation;
- multi-token prediction;
- block generation;
- discrete diffusion;
- AR/diffusion hybrid;
- revise-anywhere generation;
- energy/constraint refinement;
- continuous-latent generation;
- hierarchical plan → realization.

All non-AR systems must define tentative and committed output.

## 2.6 Precision/sparsity axis

Candidates:

- FP32/BF16/FP16;
- FP8;
- FP4 experimental;
- ternary / 1.58-bit;
- activation sparsity;
- weight sparsity;
- structured sparsity;
- conditional depth;
- MoE;
- combinations.

The laboratory measures actual hardware utilization, not theoretical operation counts alone.

## 2.7 Planning/cognition axis

Candidates:

- direct latent compute;
- visible reasoning;
- recurrent latent reasoning;
- search;
- world-model rollout;
- explicit belief state;
- typed latent program;
- symbolic execution;
- neuro-symbolic hybrid;
- heterogeneous model federation.

## 2.8 Hardware axis

Candidates:

- generic CPU;
- conventional GPU;
- vendor accelerator/NPU;
- ternary/low-bit specialized kernels;
- neuromorphic/event-driven hardware;
- analog/photonic matrix hardware.

Hardware-specific results are scoped to exact hardware/runtime identity.

---

# 3. ExoticCandidate manifest

```yaml
candidate_id: ACX-...
version: ...
title: ...
tier: E1 | E2 | E3

hypothesis:
  challenged_assumption: ...
  claimed_advantage: ...
  falsification_test: ...
  kill_criteria: [...]

architecture:
  representation: ...
  compute_depth: ...
  attention_state: ...
  memory_write: ...
  generation: ...
  precision_sparsity: ...
  planning: ...
  hardware: ...

state:
  mutable_at_inference: false
  owner: ...
  scope: request | workflow | session | experiment
  ttl: ...
  reset_semantics: ...
  serialization: ...
  integrity_digest: ...
  deletion_semantics: ...

execution:
  max_iterations: ...
  convergence_rule: ...
  tentative_output: ...
  commit_rule: ...
  fallback: ...

evidence:
  source_ids: [...]
  strongest_baseline: ...
  reproduction_status: ...
  ablations: [...]
  negative_evidence: [...]

system_effects:
  training: ...
  serving: ...
  cache: ...
  distributed: ...
  security: ...
  tool_authority: ...
  provenance: ...
  recovery: ...

promotion:
  track_ab_compatible: false
  track_aa_candidate: false
  signed_decision: null
```

---

# 4. Candidate families

## 4.1 Test-time neural memory

Central question:

> Can a learned memory update during inference provide more useful long-horizon state than attention, retrieval, or fixed recurrent state at equal resource cost?

Isolation modes:

- request-local;
- workflow-local;
- session-local research;
- never-global-by-default.

Experiments:

- long-context recall;
- distributed facts;
- contradiction/update tasks;
- poisoning;
- repeated topic interference;
- state reset;
- deterministic replay;
- cross-session leakage;
- memory capacity curves.

## 4.2 Dynamic byte latent

Central question:

> Can learned patch boundaries allocate compute based on information complexity while improving robustness enough to justify abandoning a fixed tokenizer?

Hard cases:

- arbitrary bytes;
- rare Unicode;
- source code;
- binary-like text;
- typos/noise;
- homoglyphs;
- multilingual switching;
- machine schemas.

## 4.3 Diffusion/refinement language models

Central question:

> Can global/parallel refinement outperform sequential decoding on real serving workloads?

System questions:

- when can text stream?
- what state can downstream consumers trust?
- can already-emitted bytes be revised?
- how are JSON/tool calls committed?
- how are safety/policy constraints applied across iterations?
- what happens if iteration budget ends mid-refinement?

## 4.4 Recurrent latent depth

Central question:

> Can hidden recurrence provide quality scaling with test-time compute more efficiently than extra model size, visible reasoning tokens, or external search?

Failure probes:

- oscillation;
- overthinking degradation;
- recurrence count sensitivity;
- hidden-state attractors;
- adversarial stop criteria;
- per-token depth imbalance.

## 4.5 Equilibrium computation

Central question:

> Can fixed-point hidden computation provide effective implicit depth without unacceptable convergence cost?

Measure distribution of iterations, not only mean.

## 4.6 Conditional depth

Central question:

> Which tokens deserve expensive computation?

Adversarial examples deliberately hide crucial information in superficially simple tokens.

## 4.7 Differential attention

Central question:

> Can explicitly subtractive attention improve signal/noise enough to change long-context robustness?

Test against distractors, injection content, repeated near-duplicates and high-frequency irrelevant tokens.

## 4.8 Native ternary architecture

Central question:

> If ternary arithmetic is a training-time architectural choice rather than a compression afterthought, does a different efficiency scaling law emerge on real hardware?

Test CPU as well as accelerators.

## 4.9 Fully sparse activation

Central question:

> Can most activation work disappear while preserving rare/tail capabilities?

Tail cases are mandatory because average perplexity can hide sparse-routing failures.

## 4.10 Cross-layer route reuse

Central question:

> How much layer-to-layer routing redundancy exists, and when is reusing an earlier route harmful?

Record route divergence as a function of layer, task and context length.

## 4.11 Latent multimodal language

Central question:

> Can continuous modality latents and discrete text share one causal backbone without forcing all modalities into an artificial token vocabulary?

Every latent preserves original modality/time/coordinate provenance.

## 4.12 Reversible blocks

Central question:

> Can activation storage be replaced by reconstruction without unstable low-precision error or intolerable recomputation?

## 4.13 Fast weights / generated adapters

Central question:

> Can bounded temporary parameter updates outperform context-only adaptation?

They are treated as temporary state, not as a promoted model.

## 4.14 Dynamic experts

Central question:

> Can expert topology itself evolve without losing optimizer/checkpoint/reproducibility semantics?

## 4.15 World models

Central question:

> Can an internal simulator predict action consequences well enough to reduce real-world tool mistakes?

Predictions remain model-generated data.

## 4.16 Typed/neuro-symbolic execution

Central question:

> Can a model emit an intermediate program whose semantics are easier to verify than unconstrained language?

## 4.17 Graph-native computation

Central question:

> Does representing entities/events/relations directly reduce repeated textual reconstruction and improve relational reasoning?

## 4.18 Continuous/event-driven state

Central question:

> Do irregular asynchronous streams benefit from time-native state rather than forcing events into uniformly spaced token sequences?

## 4.19 Neuromorphic/analog substrate

Central question:

> Is there a meaningful task/cost regime where event-driven or analog hardware changes the system frontier?

Simulation-only gains do not count as hardware evidence.

## 4.20 Error-correcting neural compute

Central question:

> Can selective redundant computation detect silent accelerator or numerical faults at a fraction of full replication cost?

---

# 5. Exotic combination matrix

Combination experiments start only after individual mechanisms have baseline evidence.

High-interest pairings:

| A | B | Hypothesis |
| --- | --- | --- |
| byte latent | recurrent depth | allocate representation and reasoning compute adaptively |
| byte latent | neural memory | tokenizer-free long-term sequence memory |
| recurrent depth | neural memory | more compute and more adaptive memory at inference |
| recurrent depth | self-speculation | shallow recurrence drafts, deep recurrence verifies |
| diffusion | block autoregression | retain KV/cache benefits while parallelizing within/across blocks |
| diffusion | revise-anywhere | explicit iterative global correction |
| ternary | activation sparsity | minimize both stored and active arithmetic |
| ternary | conditional depth | low-bit model plus token-dependent compute |
| ternary | MoE | low-bit expert specialization |
| sparse attention | shared routing | amortize routing overhead across layers |
| sparse attention | compressed KV | attack compute and memory together |
| world model | typed planner | simulate candidates then execute verified symbolic actions |
| graph state | neural memory | persistent relational latent state |
| latent multimodal | diffusion head | common causal backbone with continuous output refinement |
| fast weights | retrieval | adapt temporary state from externally verified evidence |
| equilibrium | conditional compute | stop hidden iteration based on convergence/difficulty |
| reversible blocks | low precision | minimize both activation and numeric storage costs |
| belief state | heterogeneous federation | exchange typed uncertainty rather than free-text votes |

Forbidden shortcut:

> "Both mechanisms won separately, therefore the combination wins."

Every pair gets an interaction ablation.

Three-or-more-mechanism combinations are allowed only after pairwise interactions are characterized.

---

# 6. Exotic commit protocol

Some exotic architectures produce unstable intermediate state.

Canonical states:

```text
PROPOSED_STATE
 -> ITERATING
 -> CANDIDATE_STATE
 -> VERIFIED_STATE
 -> COMMITTED_OUTPUT
```

Side exits:

```text
NON_CONVERGED
BUDGET_EXHAUSTED
INVALID
REJECTED
RESET
```

Rules:

- tools consume only states explicitly authorized for tool planning;
- irreversible tools require committed/verified action objects;
- tentative text may be exposed only through interfaces that label it tentative;
- revision cannot silently rewrite a side effect that already occurred;
- reset clears all ephemeral neural state declared by the candidate.

---

# 7. Mutable neural state protocol

For Titans-like memory, fast weights, generated adapters and temporary experts:

```text
EphemeralNeuralState
  state_id
  candidate_id
  model_artifact_id
  tenant_id
  owner_principal
  workflow/session scope
  created_at
  expires_at / max_steps
  parent_state
  digest
  mutation_count
  resource_bytes
  reset_version
```

Prohibited:

- implicit cross-user state sharing;
- state without an owner;
- unbounded lifetime;
- tool authority encoded inside neural state;
- silent conversion into durable Skeleton memory;
- promotion without provenance/evaluation.

---

# 8. Exotic falsification battery

Every candidate receives tests designed to make its central idea fail.

## Memory candidates

- conflicting updates;
- poisoned facts;
- stale facts;
- long distractor streams;
- repeated overwrites;
- scope reset;
- cross-tenant/session probes.

## Recurrence/equilibrium

- adversarial non-convergence;
- oscillatory hidden state;
- easy tasks with excessive looping;
- hard tasks with premature stopping;
- low-precision instability.

## Sparse/conditional compute

- crucial rare token;
- long-tail entity;
- arithmetic/code token;
- adversarial router overload;
- repeated route ties;
- route collapse.

## Diffusion/revision

- exact JSON;
- code syntax;
- long coherent generation;
- streaming cancellation;
- tool call inside tentative text;
- final-step budget exhaustion.

## Byte representations

- invalid byte sequences;
- Unicode normalization;
- mixed scripts;
- rare identifiers;
- code indentation;
- structured protocols.

## Generated weights/adapters

- malicious demonstrations;
- adversarial state initialization;
- repeated generation variance;
- reset failure;
- out-of-distribution task.

## World model

- simulator distribution shift;
- deceptive model confidence;
- environment surprise;
- adversarially selected actions that exploit simulator error.

---

# 9. Exotic scorecard

No universal scalar ranking.

Report:

- quality / task success;
- training tokens;
- training wall-clock;
- inference FLOPs;
- realized latency;
- throughput;
- tail latency;
- memory;
- state growth;
- energy where measured;
- hardware specialization;
- failure rate;
- reset/replay fidelity;
- implementation complexity;
- maintenance burden;
- portability;
- security impact;
- observability burden;
- migration complexity;
- rollback cost.

Also report:

- **abstraction gain** — what complexity disappears from the rest of the system?
- **abstraction tax** — what new contracts/failure modes are introduced?
- **novelty dependence** — does the benefit disappear when the baseline receives equivalent tuning/kernels?
- **compound fragility** — how sensitive is the candidate to other architecture choices?

---

# 10. Kill criteria

Default kill conditions:

- no advantage against a tuned baseline at equal resources;
- advantage exists only on a microbenchmark;
- unbounded or unpredictable state growth;
- unstable recurrence/convergence;
- cross-tenant/session state leak;
- inability to reset/replay;
- cannot checkpoint;
- incompatible with authority/tool boundaries;
- requires unreviewable arbitrary code during load;
- no safe fallback;
- tail latency is operationally unacceptable;
- only one brittle hardware backend supports it;
- complexity cost exceeds measurable benefit;
- quality gain vanishes at larger scale;
- gain disappears after contamination-safe evaluation;
- composition breaks P0 hardening invariants.

Kill means "retain as negative evidence," not delete history.

---

# 11. Graduation ladder

```text
idea
 -> source/evidence ingestion
 -> ExoticCandidate manifest
 -> smallest falsification experiment
 -> independent reproduction
 -> controlled scaling
 -> systems prototype
 -> component ablation
 -> hostile Track AB compatibility
 -> Track AA candidate
 -> shadow
 -> canary
 -> normal production promotion
```

There is no AC → production shortcut.

---

# 12. Initial execution queue

First exotic experiments should maximize information per cost.

1. BLT-style representation toy benchmark against current tokenizer on code/Unicode/rare-byte cases.
2. Recurrent-depth miniature model with variable recurrence and explicit overthinking/non-convergence curves.
3. Mixture-of-Depths token routing baseline.
4. Titans-style request-local neural-memory prototype with poison/reset/replay tests.
5. Diffusion or masked iterative decoder with strict tentative/commit semantics.
6. Ternary/BitNet inference micro-runtime on CPU plus accelerator comparison.
7. Activation sparsity kernel-realization experiment.
8. Differential attention distraction/retrieval benchmark.
9. Cross-layer routing reuse prototype.
10. Equilibrium/fixed-point numerical stability toy model.
11. Reversible-block activation-memory benchmark.
12. Latent multimodal provenance proof-of-concept.
13. Only after those: high-value compound pairings.

This queue is intentionally cheaper than immediately training a giant exotic model. The goal is to destroy weak hypotheses early.
