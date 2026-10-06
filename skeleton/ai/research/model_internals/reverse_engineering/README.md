# Governed AI reverse-engineering lab

This package provides an evidence-first reverse-engineering surface for AI systems
that the operator is authorized to test. It is research-only and grants no model
execution, training, deployment, source-retirement, or promotion authority.

## Evidence contract

The core contract is deliberately black-box-first:

- explicit target authorization before a probe can execute;
- probe payloads are persisted only as SHA-256 identities in evidence records;
- outputs are normalized into digests, shapes, error types, and bounded feature flags;
- repeated probes create deterministic behavioral fingerprints;
- architecture statements remain hypotheses unless evidence thresholds are met;
- differential runs compare observable behavior without claiming hidden implementation identity;
- artifact inspection is separately gated by rights provenance and rejects credential/personal-data-bearing inputs;
- report identities are canonical and deterministic so later verification can bind to exact evidence;
- evidence synthesis requires independent domains and surfaces contradictory evidence instead of averaging it away.

## Characterization planes

The lab contains bounded analyzers for:

- **context-window behavior** — success/fidelity brackets, first failure, monotonicity violations, and confidence;
- **routing behavior** — route concentration, per-input-class route sets, and deterministic-class ratio;
- **state and memory** — reset-controlled recall, repeated-input divergence, and cross-reset carryover signals;
- **decoding behavior** — repeated-output diversity/collision ratios, response-length distributions, and stop-reason counts;
- **tokenizer behavior** — token-count, token-id-space, and character/token fingerprints without persisting raw inputs;
- **embedding geometry** — norms, pairwise cosine structure, centroid magnitude, and zero-norm accounting;
- **KV-cache behavior** — measured bytes/token, approximate linearity, and theoretical-geometry error;
- **cache eviction** — first over-capacity point, first retention loss, hit-rate and retention curves;
- **attention geometry** — MHA/GQA/MQA classification, head ratios, and width-consistency checks;
- **attention patterns** — concentration, effective support, first/last-position mass, and sink-candidate ratios;
- **activation geometry** — per-layer norms, sparsity, and pairwise cosine structure while reports retain only vector digests;
- **representation drift** — adjacent-layer cosine drift and norm-ratio trajectories on matched digested inputs;
- **logit-lens trajectories** — top-token changes, stabilization layer, and confidence progression from authorized local snapshots;
- **position sensitivity** — controlled offset-vs-similarity curves without asserting a positional-encoding implementation;
- **prefill/decode scaling** — log-log latency exponents and fit quality from controlled measurements;
- **model correspondence** — matched-input representation cosine/norm correspondence across authorized models;
- **architecture-family scoring** — transparent evidence-weighted candidate ranking rather than opaque identity claims;
- **evidence synthesis** — multi-domain support/conflict aggregation before promotion from hypothesis to supported;
- **expert routing** — observed top-k, expert load concentration, and routing-weight summaries for authorized MoE models;
- **residual interventions** — output-change and metric-delta summaries for controlled causal interventions;
- **causal tracing** — corruption/restoration effect and recovery-fraction summaries by layer;
- **feature specialization** — feature-to-unit score concentration and dominant layer/unit summaries;
- **multimodal adapters** — projection dimensions, low-rank structure, modalities, and target spaces from authorized metadata;
- **tool topology** — caller→tool and tool→tool transition graphs reconstructed from digested execution traces;
- **authorized artifact manifests** — tensor shapes/dtypes/counts with provenance receipts but no raw tensor persistence;
- **tensor topology** — indexed-layer and recurrent-shape inference from authorized tensor metadata;
- **quantization** — numerical error and cosine-similarity characterization for authorized reference/quantized samples;
- **replication** — independent-actor reproduction ledgers before a supported observation is treated as replicated;
- **experiment design** — deterministic factorial matrices with stable protocol identities;
- **evidence chains** — tamper-evident append-only linkage for reports and measurements.
- **subspace/circuit overlap** — symmetric basis overlap for authorized representation subspaces;
- **multimodal alignment** — paired semantic representation alignment by modality and layer;
- **routing stability** — long-horizon total-variation drift and dominant-route switches;
- **probe calibration** — sensitivity, specificity, precision, and balanced accuracy from explicit positive/negative controls;
- **attribution stability** — repeated top-k overlap, universal features, and majority features;
- **intervention localization** — effect concentration, peak layer, centroid, and sign consistency;
- **counterfactual consistency** — expected-change sensitivity and expected-invariance specificity;
- **effect size** — pooled-standard-deviation normalized treatment/control effects;
- **causal circuit graph** — reproduced source→target intervention edges with effect and sign consistency;
- **claim-quality gate** — fail-closed promotion requiring calibration, stability, material effect, independent domains, replication, and low contradiction;
- **bootstrap uncertainty** — deterministic mean confidence intervals with reproducible seeds;
- **permutation nulls** — two-sided empirical null testing for controlled group effects;
- **sequential evidence** — bounded likelihood-ratio accumulation with explicit support/reject thresholds;
- **calibration drift** — sensitivity/specificity/precision stability across ordered evaluation windows;
- **causal mediation** — total, direct, mediated, and mediated-fraction effect decomposition;
- **rank sensitivity** — top-k attribution stability as the retained rank changes;
- **adversarial probe robustness** — paired baseline/adversarial degradation and output-change rates;
- **long-context interference** — distractor-load fidelity curves and threshold crossings;
- **memory decay** — controlled recall-loss horizons and half-recall delay estimates;
- **tool-policy boundaries** — allow/deny accuracy plus unauthorized execution detection;
- **feature interactions** — pairwise non-additive synergy and sign consistency;
- **circuit motifs** — chains, fan-in/fan-out, reciprocal pairs, sources, and sinks;
- **path patching** — source→mediator→target recovery fractions for authorized causal interventions;
- **negative controls** — expected-null deviation checks and leakage/false-positive alarms;
- **cross-seed stability** — metric range and tolerance consistency across stochastic seeds;
- **contradiction matrices** — explicit pairwise proposition conflict structure;
- **circuit centrality** — deterministic weighted in/out centrality summaries for reconstructed circuits;
- **evidence quorum** — minimum independent-domain support with bounded contradiction;
- **claim registry** — governed hypothesis/supported/conflicted/rejected transitions with fail-closed promotion;
- **campaign manifests** — deterministic dependency-linked inventories of reports, claims, and protocols;
- **report envelopes** — canonical versioned exports with tamper-verifiable payload identity;
- **drift alarms** — multi-domain threshold aggregation with observe/warning/critical severity.
- **power planning** — closed-form two-group sample sizing for standardized effects and target power;
- **balanced randomization** — deterministic stratified assignment with reproducible seeds;
- **mediation graphs** — path-coefficient products and strongest indirect causal paths;
- **intervention equivalence** — matched-effect tolerance checks across alternative interventions;
- **circuit discovery** — thresholded path discovery requiring effect, replication, and sign-consistency evidence;
- **probe scheduling** — budget-, risk-, prerequisite-, and information-aware deterministic scheduling;
- **multimodal intervention consistency** — matched semantic intervention effects across modalities;
- **ablation dose response** — dose/metric slopes, directionality, and monotonicity violations;
- **experiment coverage** — factorial cell and replicate completeness;
- **evidence ledger** — append-only hash-chained research-event verification;
- **conservative evidence confidence** — mandatory-component floors combined with weighted evidence quality;
- **drift response policy** — fail-closed observe/recheck/revalidate/freeze actions;
- **causal directionality** — paired forward/reverse effect asymmetry;
- **intervention specificity** — on-target versus off-target effect concentration;
- **probe redundancy** — binary outcome agreement and deterministic duplicate-pruning suggestions;
- **information gain** — prior/posterior entropy reduction across architecture hypotheses;
- **signature distance** — composite normalized feature distance between authorized model signatures;
- **causal invariance** — cross-environment effect stability and sign preservation;
- **intervention transfer** — matched-intervention sign consistency across authorized models;
- **provenance DAGs** — report→claim→replication ancestry, depth, missing-parent, and cycle checks;
- **assignment balance** — arm imbalance diagnostics within experimental strata;
- **probe Pareto frontiers** — non-dominated cost/information/risk probe selection;
- **multiple-testing correction** — Benjamini–Hochberg false-discovery-rate control.
- **adaptive experiment design** — uncertainty/information/cost/risk-aware next-experiment selection with prerequisite enforcement;
- **hierarchical uncertainty** — within-group, between-group, total-variance, ICC, and grand-mean uncertainty summaries;
- **nonlinear mediation** — dose-stratified total/direct/mediated effects and peak mediated-dose localization;
- **transportability** — source/target effect-gap and sign-preservation checks;
- **precision stopping rules** — stop-supported, stop-futile, stop-conflicted, or continue decisions from precision, effect, replication, and contradiction;
- **replication meta-analysis** — inverse-variance pooled effects, uncertainty, heterogeneity, actor count, and sign agreement;
- **lineage closure** — evidence→analysis→claim→replication completeness checks for supported claims;
- **falsification registry** — explicit claim falsifiers with incomplete/survived/falsified states;
- **calibration curves** — binned calibration gaps, ECE, MCE, and Brier score;
- **version drift** — ordered signature drift across model/research versions;
- **missingness diagnostics** — per-field missingness and complete-record ratios;
- **evidence staleness** — epoch-based freshness enforcement for long-running campaigns;
- **hierarchical calibration** — group-level calibration and worst-group diagnostics;
- **transport stress** — effect-gap growth and sign flips under increasing environment shift;
- **replication decay** — age-decayed replication quality with configurable evidence half-life;
- **bundle verification** — dependency completeness and cycle checks across exported research artifacts;
- **claim closure** — final fail-closed closure gate combining quality, quorum, lineage, falsification, replication, freshness, and contradiction;
- **campaign audit** — ready/hold/blocked end-state audit over critical and noncritical research controls.

These surfaces characterize what can be observed or what is available in artifacts
the operator is authorized to inspect. They do not assert proprietary architecture
identity, recover hidden weights from inaccessible systems, bypass access controls,
or create a right to inspect artifacts without ownership or permission.

Future work can deepen nonlinear structural models, cross-modal causal transport, richer
hierarchical Bayes-style uncertainty approximations, automated experiment generation, and
independent adversarial replication while preserving the same evidence/inference boundary.
