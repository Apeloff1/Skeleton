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

These surfaces characterize what can be observed or what is available in artifacts
the operator is authorized to inspect. They do not assert proprietary architecture
identity, recover hidden weights from inaccessible systems, bypass access controls,
or create a right to inspect artifacts without ownership or permission.

Future work can deepen automated circuit discovery, rank-sensitive attribution, causal
mediation, multimodal alignment interventions, long-horizon drift alarms, and adversarial
replication while preserving the same evidence/inference boundary.
