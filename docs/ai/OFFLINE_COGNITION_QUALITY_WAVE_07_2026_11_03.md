# Wave 7/8 — external-evidence-aware offline model quality

Eight canonical domains: benchmark admission, finite metrics, output shape,
refusal quality, source quality, answer grounding, hallucination hold,
review readiness. No parallel model-evaluator owner or provider SDK.

The shared quality_gate supplies source-model-policy-environment bound
benchmark identities; exact SHA outcome tests; finite latency p50/p95/p99;
strict duplicate-key-rejecting output envelope admission; exact original
bytes in citation proofs; deterministic refusal label statistics; and
human/independent-review holds. A cryptographic quote proof establishes
provenance, not factual or logical entailment.

No automatic model promotion is possible, including on a perfect held-out
source corpus. Evaluation inputs must come from separately trusted
collectors, original operator-approved source rights, independently
provisioned real GGUF weights, and exact-head bound scorer/dataset/config.
The source controlled cases here do not qualify the target Windows laptop.

Focused local tests:
    python -m unittest skeleton.testing.test_offline_cognition_quality_gate -v
    python -m unittest discover -s skeleton/testing -p 'test_offline_cognition_*.py' -q

L00-L02: canonical owner and declared exact model/evaluator schema.
L03-L05: bounded independent evaluation input only, no self-promotion.
L06-L07: prompt/content remains untrusted; refuse unverifiable source spans.
L08-L09: finite metrics including empirical p95/p99, never one fake latency.
L10: original adverse quality tests and reviewer evidence.
L11-L12: no model install or release transition without independent CI,
device, license and replay proof; rollback remains separately owned.
L13: comparator-backed quality/cost/latency/security superiority unproven.
