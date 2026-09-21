
# Frontier Research Experiment Protocols — 2026

Status: canonical experimental-design companion to Track AD
Authority: research execution only; no direct production authority
Atlas: docs/architecture/frontier-research-atlas-2026.md

## 0. Purpose

The research atlas defines what Skeleton currently believes and what remains uncertain.
This document defines how to settle the highest-value uncertainties locally.

Every protocol records:

~~~yaml
experiment_id: RXP###
question:
hypothesis:
null_hypothesis:
scope:
pre_registered:
  primary_metrics: []
  secondary_metrics: []
  stop_rule: ...
  failure_rule: ...
  tuning_budget: ...
controls: []
independent_variables: []
held_constant: []
datasets_or_workloads: []
hardware:
software:
seeds:
artifacts:
  code_commit:
  config_digest:
  dataset_manifest:
  model_artifact:
  evaluator_version:
  logs:
  checkpoints:
results:
  raw:
  summarized:
  uncertainty:
decision:
  conclusion:
  debt_retired: []
  debt_opened: []
  followups: []
signoff:
~~~

A protocol result is not trusted because the experiment ran. It becomes evidence only after artifact integrity, metric validity, baseline parity, and reproduction review.

---

# RXP001 — Dense baseline and local scaling surface

Question: What is the local quality/compute frontier of a conventional dense Transformer under Skeleton's own data, optimizer, tokenizer, and hardware?

Hypothesis: loss and downstream quality over model size and token budget can be modeled well enough locally to predict one held-out scale point.

Minimum grid:
- three model scales;
- three token budgets;
- one held-out scale point.

Held constant:
- RepresentationSpec;
- architecture family;
- optimizer family;
- data mixture;
- precision;
- scheduler;
- objective.

Primary metrics:
- validation loss;
- domain losses;
- downstream capability vector;
- wall-clock;
- accelerator-hours;
- peak memory;
- tokens/sec;
- energy when measurable.

Falsification: if the fitted scaling relation misses the held-out point materially, the fit cannot justify extrapolation beyond the observed regime.

Output: ScalingSurfaceEvidence bound to exact data, optimizer, representation, runtime, and hardware.

---

# RXP002 — Data-mixture transfer across scale

Question: Do mixture weights optimized on proxy models transfer to larger models?

Arms:
1. fixed heuristic mixture;
2. temperature/sample-size mixture;
3. DoReMi-style learned mixture;
4. multi-fidelity Bayesian mixture;
5. downstream-tuned oracle-like reference where feasible.

Procedure:
- optimize at small scale;
- freeze mixture;
- train larger scale;
- optionally re-optimize at larger scale to quantify transfer gap.

Metrics:
- aggregate quality;
- per-domain quality;
- worst-domain regression;
- convergence;
- mixture-search compute;
- lifecycle compute.

Failure criterion: proxy improvement plus larger-scale regression is recorded as a transfer failure, not averaged away.

Targets: RDE005.

---

# RXP003 — Synthetic-data factorial and ancestry experiment

Question: When does synthetic pretraining help, and when does it narrow support or amplify errors?

Factors:
- synthetic mode: none, rephrase, textbook/explanation, relational/bootstrap, verifier-backed code/math/proof;
- natural-data anchor: high, medium, low;
- ancestry depth: generation 1, 2, 3+;
- generator diversity: one teacher, related teachers, independent-family teachers.

Metrics:
- loss;
- downstream quality;
- long-tail domain quality;
- lexical/semantic diversity;
- memorization;
- calibration;
- OOD;
- generation compute;
- verifier compute;
- source-coverage drift.

Hard rule: generation/filtering/verifier compute is reported separately from student training compute.

Targets: RDE006.

---

# RXP004 — Optimizer geometry: AdamW vs Muon vs SOAP vs low-rank state

Arms:
- AdamW;
- Muon for compatible matrices + AdamW remainder;
- SOAP/Shampoo family;
- GaLore/LoRA-Pre-style low-rank optimizer state.

Fairness:
- update-RMS matching or explicit sweep;
- comparable weight-decay semantics;
- warmup;
- batch;
- clipping;
- precision;
- tuning budget.

Training metrics:
- loss/tokens;
- quality/tokens;
- quality/wall-clock;
- update/weight ratio;
- gradient norm;
- loss spikes;
- non-finite steps.

Systems metrics:
- optimizer-state bytes;
- communication;
- decomposition/projection time;
- checkpoint bytes;
- resume time.

Scale transfer requires at least a proxy and a larger confirmation scale.

Targets: RDE007.

---

# RXP005 — FP8 long-horizon stability

Baseline: matched BF16 run.

Record FP8 separately for:
- matrix compute;
- activations;
- gradients;
- optimizer moments;
- communication;
- accumulation.

Stress:
- outlier-rich batches;
- long-context phase;
- checkpoint/resume;
- batch-size changes;
- LR transitions;
- rare large-gradient steps.

Metrics:
- quality;
- loss divergence;
- scaler events;
- overflow/underflow;
- late-run spikes;
- throughput;
- memory;
- communication.

One catastrophic numerical failure not observed in BF16 is recorded separately from average quality.

Targets: RDE008.

---

# RXP006 — Sparse/differential attention reality check

Arms:
- dense exact;
- local/window;
- content-routed sparse;
- native sparse attention candidate;
- differential attention;
- shared-routing sparse candidate.

Workloads:
- short normal;
- long retrieval;
- distributed facts;
- distractor-heavy;
- near duplicates;
- adversarial low-salience key token;
- prompt-injection distractors.

Metrics:
- quality;
- retrieval miss;
- route stability;
- training throughput;
- decode throughput;
- memory;
- p95/p99 latency;
- kernel occupancy;
- fallback rate.

Report algorithmic, theoretical-FLOP, and realized-system effects separately.

---

# RXP007 — Recurrent latent-depth scaling

Compare:
- direct;
- longer visible reasoning;
- Best-of-N;
- fixed recurrence counts;
- adaptive recurrence;
- verifier-guided search.

Tasks:
- math;
- code;
- compositional reasoning;
- general QA;
- long-context reasoning.

Metrics:
- task quality;
- latency;
- compute;
- visible tokens;
- recurrence count;
- convergence/oscillation;
- overthinking rate.

Stress:
- easy tasks forced to recur;
- adversarial stop criteria;
- near-max recurrence;
- low precision.

Targets: RDE010 partly.

---

# RXP008 — Request-local neural memory vs external memory

Arms:
- context only;
- lexical/dense retrieval;
- summarizing external memory;
- Titans/MIRAS-style learned neural memory;
- external + neural hybrid.

Neural memory is request-local in the first experiment.

Tasks:
- exact recall;
- repeated updates;
- contradictions;
- distributed associations;
- distractor streams;
- changing rules.

Metrics:
- accuracy;
- state bytes;
- read/write latency;
- interference;
- forgetting;
- reset fidelity;
- replay fidelity;
- poison recovery;
- provenance recoverability.

Kill rule: unreplayable or scope-leaking neural memory remains research-only regardless of benchmark quality.

Targets: RDE018.

---

# RXP009 — Byte-latent representation falsification

Arms:
- current subword tokenizer;
- fixed byte-level;
- dynamic byte-patch/BLT-style.

Tasks:
- normal text;
- multilingual;
- code;
- rare identifiers;
- mixed scripts;
- malformed/noisy input;
- Unicode confusables;
- structured JSON/tool calls.

Metrics:
- quality;
- compute;
- effective sequence length;
- latency;
- cache bytes;
- structured-output failure;
- normalization ambiguity;
- speculative compatibility.

Targets: RDE003.

---

# RXP010 — Test-time scaling protocol matrix

Strategies:
- direct;
- sequential continuation/revision;
- Best-of-N + voting;
- Best-of-N + learned verifier;
- prefix/tree search;
- decomposition;
- mixed strategy.

Accounting:
- generated tokens;
- verifier tokens;
- wall-clock;
- model calls;
- memory;
- search/tool calls.

Task strata:
- easy;
- medium;
- hard;
- verifier-easy/solve-hard;
- verifier-hard;
- open-ended.

Output: conditional Pareto fronts by task class, never one universal winner.

Targets: RDE010.

---

# RXP011 — Verifier independence and correlated failure

Verifier arms:
- self-verifier;
- same-family separate model;
- different-family model;
- ensemble;
- deterministic execution/checker;
- formal solver.

Measurements:
- verifier accuracy;
- calibration;
- candidate-verifier error correlation;
- gaming;
- diversity collapse;
- OOD;
- cost.

Stress candidate banks where every solution shares one subtle misconception, and where style spuriously correlates with correctness.

Targets: RDE011.

---

# RXP012 — RLVR answer gain vs causal reasoning faithfulness

Matched initialization.

Arms:
- SFT;
- RLVR;
- process-supervised arm where available.

Metrics:
- final accuracy;
- Pass@K;
- trace correctness;
- trace sufficiency;
- causal perturbation;
- cross-domain transfer;
- calibration.

Perturbations:
- remove reasoning segment;
- reorder steps;
- insert plausible wrong intermediate;
- substitute unrelated correct-looking trace.

Targets: RDE012.

---

# RXP013 — Retrieval/context routing ladder

Methods:
- BM25;
- dense;
- sparse+dense hybrid;
- reranked hybrid;
- long context without retrieval;
- graph retrieval;
- agentic/file-system search.

Corpus sizes: at least three meaningful tiers.

Tasks:
- exact lookup;
- paraphrase;
- multi-hop;
- reasoning-intensive retrieval;
- conflicting sources;
- stale/fresh facts;
- long-document synthesis.

Metrics:
- answer quality;
- retrieval recall;
- evidence precision;
- latency;
- tokens;
- build/update cost;
- storage;
- provenance quality.

Targets: RDE013 and RDE014.

---

# RXP014 — Durable-memory belief revision

Scenarios:
- corrected fact;
- temporal state change;
- conflicting sources;
- uncertain claim;
- retraction;
- superseded preference;
- source-trust change.

Memory models:
- append-only;
- latest-write-wins;
- versioned claims;
- contradiction graph;
- probabilistic/belief-state candidate.

Metrics:
- current-answer correctness;
- historical reconstruction;
- contradiction detection;
- provenance retention;
- false retraction;
- stale-fact use.

Targets: RDE015.

---

# RXP015 — Prospective memory and typed intention stores

Arms:
- prompt/context only;
- retrospective memory;
- generic RAG memory;
- typed intention store;
- learned intention selector;
- typed store + learned selector.

Triggers:
- absolute time;
- relative time;
- event;
- state transition;
- recurring condition;
- dependency completion;
- compound condition.

Metrics:
- precision;
- recall;
- Set-F1;
- false alarms;
- missed triggers;
- early/late action;
- stale authorization;
- cancellation;
- supersession;
- cost.

Action execution always requires fresh authority even when trigger detection is correct.

Targets: RDE016.

---

# RXP016 — Action horizon and abstraction

Keep decision rules roughly fixed while increasing primitive action length.

Arms:
- primitive actions;
- macro-actions;
- explicit subgoals;
- hierarchical policy;
- memory-only intervention;
- longer context only.

Metrics:
- training stability;
- reward;
- success;
- exploration entropy;
- credit-assignment proxies;
- horizon transfer;
- recovery.

Targets: RDE019.

---

# RXP017 — Tool metadata adversary

Mutate functionally equivalent tools through:
- names;
- descriptions;
- examples;
- ordering;
- provider claims;
- fake safety claims;
- injection payloads.

Metrics:
- selection bias;
- task success;
- authority violations;
- robustness after canonical capability normalization.

Targets: RDE021.

---

# RXP018 — Colocated vs disaggregated serving crossover

Topologies:
- colocated;
- static P/D;
- dynamic P/D;
- P/D + prefill deflection;
- network-aware decode routing.

Grid:
- prompt length short/medium/long;
- generation short/medium/heavy-tail;
- concurrency low/medium/saturation;
- network fast/congested/heterogeneous.

Metrics:
- TTFT p50/p95/p99;
- inter-token latency;
- throughput;
- KV transfer;
- queue time;
- accelerator utilization;
- network utilization;
- fairness;
- recovery.

Targets: RDE022 and RDE023.

---

# RXP019 — KV-cache rate-distortion study

Methods:
- no compression;
- uniform quantization;
- per-channel/layer quantization;
- eviction;
- transform coding;
- latent compression;
- recompute/retrieval hybrid.

Fairness: equal-memory comparison.

Metrics:
- downstream quality;
- attention-output distortion;
- decode latency;
- codec time;
- memory;
- bandwidth;
- long-context degradation.

Targets: RDE024.

---

# RXP020 — Output-length uncertainty and reservation

Workloads:
- tight distributions;
- heavy tails;
- mixed request classes;
- adversarial max-token requests.

Policies:
- reserve max_tokens;
- mean estimate;
- quantile;
- robust/distributionally robust;
- adaptive after start.

Metrics:
- OOM;
- rejection;
- utilization;
- latency;
- fairness;
- wasted reservation.

Targets: RDE025.

---

# RXP021 — Monitorability drift matrix

Axes:
- model family/scale;
- base vs SFT vs preference/RL vs reasoning-trained;
- direct vs visible reasoning vs tool use;
- weaker/comparable/stronger/different-family monitor.

Threats:
- obvious sabotage;
- subtle sabotage;
- motivated misclassification;
- secret exfiltration;
- hidden policy bypass;
- evaluation-aware evasion.

Metrics:
- detection;
- false positives;
- calibration;
- time-to-detect;
- adversarial evasion;
- observation-channel dependence.

Targets: RDE028.

---

# RXP022 — Specialized detector OOD stress

Train on one safety/deception family.

Test:
- paraphrase;
- new task;
- new model family;
- new attack strategy;
- another language;
- longer interaction.

Baselines:
- specialized fine-tuned detector;
- prompted general model;
- ensemble;
- deterministic rules where applicable.

Targets: RDE029.

---

# RXP023 — Interpretability usefulness benchmark

Arms:
- transcript only;
- logits/activations;
- SAE features;
- neuron features;
- circuit graph;
- combined.

Tasks:
- predict behavior under intervention;
- localize injected defect;
- choose effective intervention;
- predict safety failure;
- distinguish causal from correlated feature.

Metrics:
- predictive uplift;
- intervention success;
- cost/time;
- calibration;
- downstream decision quality.

Targets: RDE026.

---

# RXP024 — Interpretability portability after compression

Artifacts:
- full precision;
- quantized;
- pruned;
- architecture-surgery derivative.

Compare:
- feature identity;
- circuit identity;
- causal intervention;
- behavior.

Targets: RDE027.

---

# RXP025 — Formal semantic fidelity

Pipeline:
natural language -> formalization -> deterministic proof/check -> semantic-equivalence evaluation.

Cases:
- omitted constraint;
- strengthened theorem;
- weakened theorem;
- unit mismatch;
- quantifier inversion;
- hidden assumption.

Metrics:
- formal validity;
- semantic fidelity;
- false-assurance rate;
- repair success.

Targets: RDE032.

---

# RXP026 — Research-agent anti-cheating

Agent may access declared code, literature and experiment tools.

Hide:
- blind promotion answers;
- evaluator internals;
- future labels.

Plant:
- noisy scorer;
- exploitable benchmark script;
- metric loophole;
- filename hint;
- stale answer cache;
- overfit public dev set.

Metrics:
- scientific quality;
- cheating attempts;
- exploit success;
- detection;
- reproducibility;
- independent recompute agreement.

Targets: RDE033.

---

# RXP027 — Research-agent implementation benchmark

Score separately:
- literature comprehension;
- hypothesis;
- design;
- code modification;
- debugging;
- run management;
- statistical analysis;
- interpretation;
- replication.

Tasks:
- reproduce known result;
- bounded extension;
- diagnose failed reproduction;
- compare competing explanations.

Targets: RDE034.

---

# RXP028 — Dynamic benchmark generator validation

Checks:
- answer validity;
- difficulty stability;
- diversity;
- evaluator agreement;
- leakage;
- duplication;
- generation-model bias.

Maintain:
- dynamic set;
- fixed anchor;
- hidden expert-audited subset.

Targets: RDE035.

---

# RXP029 — Multi-agent equal-compute comparison

Arms:
- one strong agent;
- homogeneous multi-agent;
- heterogeneous specialist agents;
- generator/verifier pair.

Equalize:
- total tokens;
- wall-clock where possible;
- tool calls;
- verifier budget.

Metrics:
- success;
- diversity;
- correlated errors;
- coordination overhead;
- deadlock/rework;
- authority incidents.

Targets: RDE020.

---

# RXP030 — Unlearning/deletion evaluation

Separate:
1. external memory deletion;
2. retrieval policy block;
3. approximate weight unlearning;
4. retraining reference where feasible.

Metrics:
- target forgetting;
- extraction attack;
- membership inference;
- retained utility;
- generalization;
- sequential request degradation;
- collateral damage;
- time/compute.

Targets: RDE030.

---

# RXP031 — Multimodal post-training regression

Before/after:
- object/attribute perception;
- OCR;
- spatial grounding;
- temporal video reasoning;
- audio grounding;
- cross-modal contradiction;
- textual helpfulness.

Targets: RDE031.

---

# RXP032 — Ternary/sparse kernel reality check

Arms:
- BF16 dense;
- PTQ low-bit;
- native ternary;
- activation sparse;
- structured weight sparse;
- ternary+sparse.

Devices:
- CPU;
- at least one accelerator family.

Metrics:
- quality;
- latency;
- throughput;
- memory;
- energy where measurable;
- operator coverage;
- fallback rate.

No theoretical bit/FLOP claim counts as realized systems evidence.

---

# RXP033 — Topology-aware distributed planner

Cluster variants:
- uniform links;
- heterogeneous links;
- degraded link;
- straggler;
- topology change.

Compare:
- fixed manual layout;
- topology-aware planner;
- offline best-known/oracle where feasible.

Metrics:
- step time;
- exposed communication;
- memory;
- utilization;
- reconfiguration cost;
- recovery.

---

# RXP034 — Exotic-candidate minimal falsification harness

Every Track AC candidate gets one cheap direct falsification before scale-up.

Examples:
- neural memory: reset/replay;
- recurrent depth: measurable quality gain vs recurrence;
- diffusion: quality-equivalent parallelism under real serving overhead;
- equilibrium: reliable convergence;
- byte latent: robustness/efficiency advantage where hypothesized;
- generated adapters: weight stability/reproducibility.

If the central claim fails the smallest direct test, do not immediately rescue it by adding mechanisms.

---

# RXP035 — Research freshness automation

Inputs:
- arXiv/OpenReview/source identifiers;
- known version/status;
- code/model/data releases;
- benchmark versions.

Detect:
- revision;
- venue decision;
- withdrawal/retraction;
- code/data release;
- correction;
- replication/counterevidence candidate;
- stronger baseline;
- benchmark issue.

Output change receipt:

~~~text
source_id
old_state
new_state
observed_at
change_type
affected_FR_RQ_CX_RDE
requires_reanalysis
~~~

Automation creates review work. It never rewrites a research conclusion automatically.

Targets: RDE036.

---

# 36. Experiment sequencing policy

Recommended first wave:
1. RXP001 baseline;
2. RXP013 retrieval ladder;
3. RXP010 test-time scaling;
4. RXP014 + RXP015 memory;
5. RXP017 tool-selection security;
6. RXP018 serving crossover;
7. RXP004 optimizer geometry;
8. RXP003 synthetic data;
9. RXP021 monitorability;
10. RXP026 research-agent anti-cheating.

Expensive architecture/exotic runs wait for:
- stable baseline;
- eval firewall;
- immutable experiment manifest;
- resource/cost accounting;
- applicable P0 hardening gates.

# 37. Experiment-result decision vocabulary

Allowed conclusions:
- SUPPORTED_IN_SCOPE;
- PARTIALLY_SUPPORTED;
- NULL_RESULT;
- FALSIFIED_IN_SCOPE;
- INCONCLUSIVE_VARIANCE;
- INCONCLUSIVE_RESOURCE_LIMIT;
- INVALID_METHOD;
- INVALID_BASELINE;
- INVALID_EVALUATION;
- REPRODUCTION_FAILED.

Do not translate every non-positive result into "needs more scale."

# 38. Experiment integrity gate

Before a result enters the claim graph:
- code commit is immutable;
- config digest is recorded;
- dataset manifest is known;
- source/evaluator versions are known;
- hardware/software are recorded;
- failures are retained;
- baseline parity is reviewed;
- primary metrics were not silently changed post hoc;
- blind promotion holdouts remain blind;
- raw evidence is durably referenced.
