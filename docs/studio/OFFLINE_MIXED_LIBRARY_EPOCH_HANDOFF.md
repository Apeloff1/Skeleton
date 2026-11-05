# Durable multi-generation mixed game handoff

`python -m skeleton app mixed-library-epoch-handoff` accepts two to six
matching `--unsigned-generation` and `--signed-generation` JSON arrays
and `--trusted-local-operator`. Choose exactly one of `--output NEW.json`
or `--inspect-receipt EXISTING.json --expected-receipt-sha256 HEX`.

The writer replays every source-bound signed and unsigned game twice, verifies
all previous player actions and signer-policy history, then atomically publishes
an owner-private, no-clobber JSON receipt. The reader requires an independent
receipt digest and replays every generation against the live installed games,
archives, signatures, policies and private saves. Tampered or replaced receipts,
changed replay history, untrusted custody paths and missing operator consent
fail closed. Publication requires POSIX nofollow descriptor primitives.

This is a source-level, point-in-time custody check. No claim is made about
persistent rollback counters, native Godot execution, consumer-device tests,
malware clearance, legal rights, package signatures or release readiness.
