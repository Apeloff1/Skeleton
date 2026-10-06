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

The lab now contains bounded analyzers for:

- **context-window behavior** — success/fidelity brackets, first failure, monotonicity violations, and confidence;
- **routing behavior** — route concentration, per-input-class route sets, and deterministic-class ratio;
- **state and memory** — reset-controlled recall, repeated-input divergence, and cross-reset carryover signals;
- **decoding behavior** — repeated-output diversity/collision ratios, response-length distributions, and stop-reason counts;
- **replication** — independent-actor reproduction ledgers before a supported observation is treated as replicated;
- **experiment design** — deterministic factorial matrices with stable protocol identities.

These surfaces characterize what can be observed. They do not assert proprietary
architecture identity, recover hidden weights, bypass access controls, or create a
right to inspect artifacts the operator does not own or have permission to analyze.

Future work can layer owned/open-weight model internals, quantization characterization,
tool topology, activation-space experiments on authorized local models, and adversarial
replication over these contracts while preserving the same evidence/inference boundary.
