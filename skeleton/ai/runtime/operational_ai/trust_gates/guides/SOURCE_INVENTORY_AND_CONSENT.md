# Auditable source matrix and single-use consent

The source inventory uses a deterministic lexically sorted path/digest
serialization of 20 closed schemas, 20 semantic check modules and 240 real
admission/denial examples. It rejects absent paths, symlinks, extra fixture
identities, malformed JSON, oversized bytes and incomplete expected counts.

The optional fixture qualification invokes the actual trusted runtime
predicates; it never returns a model-generation receipt or silently upgrades
CI/build/release status. The script can be invoked from a checkout after all
files are complete.

Memory consent is now issued with an OS-cryptographic nonce, 256-bit HMAC,
strict time/scope constraints, constant-time authenticator comparison,
and a bounded single-use in-process replay fence. It blocks duplicate
admission after an acknowledged use. It does **not** replace persistent key
custody, durable cross-process nonce storage or the authoritative consented
memory database.

```bash
python scripts/check_operational_ai_trust_boundaries.py --run-fixtures
python -m unittest discover -s skeleton/testing -p 'test_ai_trust_*.py' -q
python -m compileall -q skeleton/ai/runtime/operational_ai/trust_gates
```

Real-model E2E, local device proofs, license review, security CI and independent
human approval remain separate mandatory holds.
