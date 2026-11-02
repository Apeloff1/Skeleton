# CPU capacity guard: canonical head and token-window integrity

CPU reservation and claim now verify the complete read-only stream-head
record, including its domain-separated stream digest, exact checkpoint,
tokenizer and generation, schema, and canonical record SHA-256. The observed
window must contain exactly the bounded token-ID sequence, offsets, source
sequence digest, and a matching canonical window digest. A digest-shaped
string alone is insufficient. Booleans, malformed offsets, extra fields,
wrong streams, stale generations, and mismatched token content fail closed.

This protects the cooperative guard against accidentally trusting a malformed
progress adapter or stale/corrupted window observation. It does **not**
attest the actual tokenizer, tensor contents, model weights, GPU/M-chip,
or device execution. Real CPU backend admission must still independently
validate the model snapshot, authorization, KV allocation, memory and disk
headroom, pressure, and irreversible token consumption before committing
progress. Cross-process exclusivity is not provided by the CPU guard.

Focused regression: `python -m pytest -q tests/flgb/test_long_context_cpu_guard.py`.
Release requires all exact-head CI and security checks; no hardware/device
qualification is asserted by this change.
