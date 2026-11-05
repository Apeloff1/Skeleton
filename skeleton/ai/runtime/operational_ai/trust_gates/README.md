# Operational AI production trust gates

Twenty closed-schema runtime boundaries with deterministic cross-field checks,
opt-in native-service admission adapter, strict JSON CLI, and 240 source-controlled
positive/adversarial fixtures. No model text grants tool, filesystem, approval or
release authority. No hosted model fallback. Existing real GGUF/native model and
SQLite chat custody remain the canonical inference and persistence implementations.

```bash
python -m skeleton.ai.runtime.operational_ai.trust_gates.cli selftest
python -m unittest discover -s skeleton/testing -p 'test_ai_trust_gate_*.py' -q
```

Acceptance of input claims **does not prove** that the claimed model weight bytes,
license, tokenizer, source digest, reviewer, CI status, device or inference is real.
All actual native E2E and final-head release checks remain mandatory. The CLI
reads trusted operator-controlled input only; untrusted package ingestion must
use the existing descriptor-anchored installer instead.
