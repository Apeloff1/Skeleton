
# Research Execution Program — 2026

Status: canonical Track AD execution program
Updated: 2026-09-22
Inputs:
- frontier-research-atlas-2026.md
- frontier-research-experiment-protocols-2026.md
- research-dependency-map-2026.md

Authority: planning/execution sequencing only; no production authority

## 0. Objective

Convert the research plane into an ordered program where cheap, decision-changing experiments occur before expensive model training.

The program optimizes for:

```text
expected information gain
× architecture decision value
× blocker-clearing power
× reuse of generated evidence
÷ compute cost
÷ human review cost
÷ irreversible risk
```

This heuristic never overrides hard safety, provenance, or authority gates.

## 1. Wave 0 — Measurement substrate

Goal: make every later result trustworthy.

Required work:
- experiment manifest schema;
- result bundle schema;
- immutable code/config/data identity;
- blind eval custody;
- source/status identity;
- analysis provenance;
- failure retention;
- baseline parity checklist;
- cost accounting.

Protocols:
- RXP040 work identity/status;
- RXP041 evidence independence;
- RXP042 contamination risk;
- RXP043 benchmark retirement;
- RXP044 dynamic benchmark stability;
- RXP050 source-adapter conformance.

Exit:
- research result can be reproduced from artifacts;
- blind promotion eval cannot leak into research selection;
- source/version/status transitions create receipts.

## 2. Wave 1 — Stable reference baselines

Goal: create reference points required by almost every challenger.

Protocols:
- RXP001 dense scaling baseline;
- RXP013 retrieval/context ladder baseline portion;
- RXP010 direct/test-time-compute baseline portion;
- RXP018 colocated serving baseline portion;
- RXP057 code-agent stage baseline;
- RXP029 single-agent equal-compute baseline.

Reference artifacts:
- dense model;
- AdamW/BF16 training;
- BM25+dense hybrid;
- direct decoding;
- colocated serving;
- single-agent workflow;
- code-agent hermetic environment.

Exit:
- baseline manifests locked;
- baseline quality/cost variance known;
- no challenger may use a weaker undocumented reference.

## 3. Wave 2 — Data and optimizer fundamentals

Protocols:
- RXP002 mixture transfer;
- RXP003 synthetic ancestry;
- RXP004 optimizer geometry;
- RXP005 FP8 stability.

Why early:
data and optimizer choices contaminate interpretation of architecture experiments.

Outputs:
- local scaling/mixture prior;
- synthetic-data policy;
- optimizer challenger map;
- precision stability envelope.

## 4. Wave 3 — Retrieval, memory, and context

Protocols:
- RXP008 neural vs external memory;
- RXP013 retrieval ladder full;
- RXP014 belief revision;
- RXP015 prospective memory.

Dependencies:
- Wave 0 evaluation identity;
- Wave 1 retrieval baseline.

Outputs:
- context router evidence;
- memory lifecycle evidence;
- contradiction/supersession semantics;
- intention store decision.

## 5. Wave 4 — Reasoning and verification

Protocols:
- RXP007 recurrent latent depth;
- RXP010 TTS matrix full;
- RXP011 verifier independence;
- RXP012 RLVR causal faithfulness;
- RXP025 semantic fidelity;
- RXP039 formal-prover decomposition;
- RXP061 formal counterfactual reasoning.

Outputs:
- ReasoningBudgetAllocator evidence;
- verifier routing policy;
- formal reasoning architecture;
- causal reasoning gap map.

## 6. Wave 5 — Agent reliability

Protocols:
- RXP016 action horizon;
- RXP017 tool metadata adversary;
- RXP029 multi-agent equal-compute;
- RXP037 trajectory uncertainty;
- RXP045 provider drift canary;
- RXP060 human uncertainty/autonomy.

Outputs:
- horizon abstraction rules;
- tool-selection hardening;
- collaboration policy;
- trajectory confidence model;
- operator confirmation policy.

## 7. Wave 6 — Software-engineering agents

Protocols:
- RXP057 code-agent failure stages;
- RXP058 context retrieval;
- RXP059 patch validation.

Required environment:
- hermetic builds;
- dependency lock;
- flaky-test detection;
- hidden regressions;
- rollback.

Output:
coding-agent promotion contract that distinguishes diagnosis from validated repair.

## 8. Wave 7 — Serving systems

Protocols:
- RXP018 P/D crossover;
- RXP019 KV rate-distortion;
- RXP020 output-length reservation;
- RXP046 portability subset for inference.

Fault campaigns:
- network congestion;
- stale telemetry;
- cache loss;
- node failure;
- overload;
- long-tail output.

Output:
topology-aware serving policy and fallback thresholds.

## 9. Wave 8 — Multimodal and world-model evidence

Protocols:
- RXP031 multimodal regression;
- RXP038 perception-aware post-training;
- RXP047 world-model invariance;
- RXP062 counterfactual shortcut battery.

Output:
multimodal training policy and minimum evidence for world-model claims.

## 10. Wave 9 — Continual adaptation and privacy

Protocols:
- RXP030 unlearning/deletion;
- RXP036 adapter interference;
- RXP049 retain–forget entanglement;
- RXP054 privacy dataflow;
- RXP055 federated/split/DP adaptation;
- RXP056 privacy-budget composition.

Output:
adaptation velocity policy:
- memory;
- adapter;
- temporary weights;
- durable weights;
plus explicit privacy accounting.

## 11. Wave 10 — Compression and deployment families

Protocols:
- RXP024 interpretability after compression;
- RXP032 ternary/sparse kernel;
- RXP046 cross-hardware portability;
- RXP051 scratch vs family derivation;
- RXP052 teacher/student error transfer;
- RXP053 compression factorial.

Output:
model-family derivation and compression policy.

## 12. Wave 11 — Interpretability and monitorability

Protocols:
- RXP021 monitorability drift;
- RXP022 detector OOD;
- RXP023 interpretability usefulness;
- RXP024 compression portability.

Run after representative training/compression variants exist.

Output:
diagnostic usefulness and monitorability matrix, not one universal safety score.

## 13. Wave 12 — Research automation

Protocols:
- RXP026 anti-cheating;
- RXP027 implementation benchmark;
- RXP035 freshness automation;
- RXP040 work identity;
- RXP050 source adapters.

Measure:
- accepted useful results per human+compute cost;
- invalid experiment rate;
- cheating/exploit rate;
- independent recompute agreement;
- oversight burden.

Only after these measurements may research-agent autonomy increase.

## 14. Wave 13 — Exotic architecture falsification

Protocol:
- RXP034 minimal exotic falsification.

Candidate-specific expansions only after cheap falsification passes:
- byte latent;
- recurrent depth;
- neural test-time memory;
- diffusion generation;
- equilibrium;
- native ternary/sparse;
- generated adapters;
- world-model planner.

No large exotic training before:
- baseline stability;
- eval firewall;
- artifact identity;
- local failure budget.

## 15. Compute classes

### C0 — metadata / analysis only
No training required.

Examples:
- source identity;
- benchmark custody;
- evidence independence;
- static code/security validation.

### C1 — micro / toy
Single workstation or small accelerator budget.

Use for:
- schema/convergence falsification;
- byte-latent prototypes;
- formal verification;
- small retrieval/memory tests.

### C2 — controlled small-model
Multi-run tuning/seed studies.

Use for:
- optimizer geometry;
- synthetic-data factorial;
- recurrent depth;
- RLVR causal studies.

### C3 — medium confirmation
Confirms scale transfer.

Required before claiming:
- optimizer default;
- architecture-family gain;
- compression family derivation;
- precision stability.

### C4 — systems-scale
Multi-node/fleet-like workload.

Use for:
- serving topology;
- distributed training;
- network-aware scheduling.

### C5 — expensive frontier confirmation
Reserved for candidates that survived prior waves.

A C5 run requires signed decision-value review and explicit abort criteria.

## 16. Evidence reuse

One experiment should retire multiple debts where justified.

Examples:
- RXP013 can inform retrieval router, provenance, latency, graph-RAG value;
- RXP018 informs scheduler, KV transfer, queueing, network telemetry;
- RXP021 informs monitorability, detector placement, trajectory logging;
- RXP051–053 inform compression, interpretability transfer, hardware portability.

Evidence reuse must preserve scope. A reused result is not reinterpreted outside tested conditions.

## 17. Stop rules

Stop a research branch when:
- central hypothesis is falsified;
- stronger simple baseline dominates;
- required systems support is unavailable;
- architecture violates non-negotiable AB invariants;
- full-stack gain is below equivalence threshold;
- cost exceeds decision value;
- evidence cannot be reproduced.

Keep negative result and artifacts.

## 18. Fast-track rule

A candidate may move faster when:
- deterministic checker proves the target property;
- implementation is isolated/reversible;
- no new authority surface appears;
- baseline/eval are mature;
- change is cheap to roll back.

Fast-track still does not bypass artifact/provenance/signoff.

## 19. Slow-track rule

Automatic slow-track for:
- mutable inference-time neural state;
- new tool authority;
- privacy-sensitive adaptation;
- new trust roots;
- irreversible external side effects;
- distributed state format change;
- research-agent autonomy expansion;
- large architecture morph.

## 20. Parallelism policy

Safe parallel research:
- independent domains;
- shared immutable baseline;
- separate eval budgets;
- no shared mutable benchmark answers.

Avoid parallelizing experiments that both change:
- data mixture;
- optimizer;
- architecture;
- evaluation
unless factorial design explicitly handles confounding.

## 21. Research queue scheduling

Priority score is advisory.

Hard prerequisites dominate score.

Scheduler inputs:
- open RDE debt;
- blocked architecture decisions;
- protocol prerequisites;
- compute availability;
- human review availability;
- freshness deadline;
- source-status change;
- risk.

Scheduler outputs:
- next protocol;
- resource envelope;
- required reviewers;
- expected blocker cleared;
- abort rule.

## 22. Result-to-plan update

After each completed RXP:
1. verify result bundle;
2. classify result state;
3. update evidence graph;
4. update CX contradictions;
5. retire/reopen RDE debt;
6. update affected RQ;
7. propose ADR if decision changes;
8. refresh dependency map;
9. never auto-promote production.

## 23. Research execution accountability

Each run signs:

```text
protocol_id
manifest_digest
started_at
completed_at
result_state
evidence_ids
debt_changes
question_changes
decision_changed
reviewer
artifact_digest
```

## 24. Planning checkpoint

```text
checkpoint_id: PLAN-20260922-RESEARCH-EXECUTION-PROGRAM
created_at: 2026-09-22
waves: 0..13
protocol_range: RXP001..RXP062
domain_count: 24
production_authority_granted: false
cheap_falsification_before_scale: true
baseline_before_challenger: true
measurement_before_promotion: true
```
