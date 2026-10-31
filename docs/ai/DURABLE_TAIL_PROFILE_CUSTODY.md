# Durable local inference tail profile custody

The measured tail profile recorder can now be backed by an authenticated,
append-only SQLite checkpoint and an **independent** monotonic generation CAS.
A profile digest alone is not a proof of source or anti-rollback integrity.

## Production boundary

The application provisions an exclusive, securely opened SQLite connection,
a separately stored 32–128-byte HMAC key, a source-bound `ProfileIdentity`,
and an independent `TailProfileAnchor` implementation. Do not store the
anchor in the same SQLite file, create a new key during restart, or use an
in-memory test double as a production anchor. The caller owns disk quota,
key custody, connection lifetime, and filesystem protections.

`DurableTailProfileStore.bootstrap()` is explicit one-time initialization.
`load()` authenticates generation, HMAC, payload digest, profile shape and
identity against the independent anchor. `persist()` permits only new
observations; it forbids deleting, rewriting, or silently evicting earlier
records. SQLite commit precedes the independent CAS. Any failed CAS
quarantines the instance; restart also detects the mismatch.

`OfflineDurableTailRecorder` wires canonical app resource capture to this
store and returns only a payload-free status after durable publication.
An incomplete or uncommitted observation never becomes an admission
certificate. The adapter does not execute models or certify GPU, M-chip,
thermal, energy, tokenizer, model quality or hardware device readiness.

This is a source-owned custody seam, not a production key-vault,
filesystem sandbox, backup/restore policy, or a device benchmark. The
operator must implement separate protected storage and durable anchor.

## Validation

`python -m pytest -q skeleton/testing/test_tail_profile_custody.py`
covers restart, append-only invariants, anchor failure, tampering,
wrong key, missing anchor, schema mismatch, and byte limits. Tests
use synthetic CPU observations and simulated anchors only.
