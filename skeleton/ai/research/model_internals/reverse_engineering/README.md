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
- report identities are canonical and deterministic so later verification can bind to exact evidence.

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
- **activation geometry** — per-layer norms, sparsity, and pairwise cosine structure while reports retain only vector digests;
- **architecture-family scoring** — transparent evidence-weighted candidate ranking rather than opaque identity claims;
- **expert routing** — observed top-k, expert load concentration, and routing-weight summaries for authorized MoE models;
- **residual interventions** — output-change and metric-delta summaries for controlled causal interventions on authorized local models;
- **authorized artifact manifests** — tensor shapes/dtypes/counts with provenance receipts but no raw tensor persistence;
- **tensor topology** — indexed-layer and recurrent-shape inference from authorized tensor metadata;
- **quantization** — numerical error and cosine-similarity characterization for authorized reference/quantized samples;
- **replication** — independent-actor reproduction ledgers before a supported observation is treated as replicated;
- **experiment design** — deterministic factorial matrices with stable protocol identities;
- **evidence chains** — tamper-evident append-only linkage for reports and measurements.

These surfaces characterize what can be observed or what is available in artifacts
the operator is authorized to inspect. They do not assert proprietary architecture
identity, recover hidden weights from inaccessible systems, bypass access controls,
or create a right to inspect artifacts without ownership or permission.

Future work can layer tool topology, residual-stream/activation interventions on
authorized local models, cache eviction experiments, multimodal adapter geometry,
and adversarial replication over these contracts while preserving the same
evidence/inference boundary.
