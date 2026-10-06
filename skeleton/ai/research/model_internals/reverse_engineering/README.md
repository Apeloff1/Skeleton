# Governed AI reverse-engineering lab

This package provides an evidence-first reverse-engineering surface for AI systems
that the operator is authorized to test. It is research-only and grants no model
execution, training, deployment, source-retirement, or promotion authority.

The first contract is intentionally black-box-first:

- explicit target authorization before a probe can execute;
- probe payloads are persisted only as SHA-256 identities in evidence records;
- outputs are normalized into digests, shapes, error types, and bounded feature flags;
- repeated probes create deterministic behavioral fingerprints;
- architecture statements remain hypotheses unless evidence thresholds are met;
- differential runs compare observable behavior without claiming hidden implementation identity;
- artifact inspection is separately gated by rights provenance and rejects credential/personal-data-bearing inputs;
- report identities are canonical and deterministic so later verification can bind to exact evidence.

This is a foundation for future context-window characterization, routing fingerprinting,
tool-boundary analysis, state/memory experiments, decoding-behavior studies, quantization
effects, local owned-model inspection, and adversarial replication experiments. New
claims must continue to separate observation from inference and must define a falsifier.
