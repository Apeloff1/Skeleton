# Bounded-contract test portfolio

The source fixture corpus covers 20 boundaries, with 12 named cases per
boundary. It checks two independent valid inputs plus 10 expected denials:
missing key, unknown key, wrong primary type, null, oversized text, wrong
last-field type, malformed surrogate, and three cross-field security faults.

The application suite separately covers actual source-stream hashing,
UTF-8 spans, stream finalization, quota reservation, alternating chat,
journal content-hash recomputation, loopback request preflight, deadline
inspection and explicit checkpoint approval.

Control tests prove process-local model compare-and-set, idempotent replay,
retry bounds, HMAC consent, unacknowledged frame blocking, local routing,
staged rollouts, evaluation counts, recovery ordering and tool intents.

Cross-system adversarial tests exercise multithreaded quota and backpressure
saturation, duplicate keys, nonfinite numbers, mismatched model digests,
release-gate pending states, key/token scope conflicts and recovery skipped
stages.

These tests provide deterministic contract evidence, **not** real model
quality, device, physical filesystem security or end-to-end deployment proof.
Use the canonical test command in the package README after implementation
and review of the final exact source head.
