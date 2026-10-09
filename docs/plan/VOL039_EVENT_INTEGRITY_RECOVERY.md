# VOL-039 Event Architecture — Durable Integrity and Verified Replay

This implementation extends the existing canonical event persistence owner
`skeleton/frontier/runtime/operation_stream_store.py`. It does not create a
new event service, change the authority of an outbox/inbox, or grant replay
authority to model output.

## Concrete runtime capabilities

- `SQLiteOperationEventStore.audit_operation(operation_id)` makes one
  bounded SQLite transaction snapshot and walks the retained event stream
  in batches, checking canonical event encoding, internal sequence continuity,
  terminal consistency, older-than-compaction residual records, and consumer
  acknowledgement bounds. The scan is capped at 1,000,000 events and each
  database fetch is capped at 4,096 events.
- The result contains a `content_sha256` integrity receipt. This binds
  namespace, operation identity, compaction watermark, terminal state and
  each canonical retained event's identity, sequence, timestamp, type and
  payload. It deliberately does **not** certify consumer lease/ACK identity.
  The SHA-256 digest is not a signature or independent attestation.
- `replay_verified(cursor, expected_sha256=...)` performs validation and
  event selection inside the **same** SQLite transaction. A concurrent writer
  cannot compact the verified tail in between these two operations.
- Operators may store the digest in a separate **trusted** witness and supply
  it to either method to detect a missing tail or a changed but valid JSON
  payload. An independently pinned digest cannot be obtained by simply
  reading the same potentially corrupted database being verified.
- `StreamStoreCorruptionError` is raised for malformed persisted records,
  sequence gaps, impossible terminal state, invalid consumer ACK, impossible
  compaction residues, exceeded audit budget and witness mismatch. The
  default `replay()` remains available as a lightweight transport operation.

## Boundaries and use

```python
from skeleton.frontier.runtime.operation_stream import ReplayCursor
from skeleton.frontier.runtime.operation_stream_store import SQLiteOperationEventStore

with SQLiteOperationEventStore("/path/to/events.sqlite") as store:
    report = store.audit_operation(operation_id)
    # Persist report.content_sha256 in independent trusted recovery evidence.
    events = store.replay_verified(
        ReplayCursor(operation_id, after_sequence=report.compacted_through),
        expected_sha256=report.content_sha256,
    )
```

This verifies one durable operation's **retained** history. It cannot
reconstruct compacted events, repair corrupted databases, authenticate an
external witness or prove the exact historic append log without a prior
independent witness. It does not run privileged consumer side effects. An
external outbox/inbox idempotency and actual delivery receipt are still
needed for exactly-once effect semantics.

Do not invoke the whole-stream audit for every frequent polling request; it
is an intentionally bounded operator/recovery mode. Before production use,
measure scan cost under the specified workload and choose an appropriate
operational audit budget.

Focused tests:

```bash
python -m pytest skeleton/testing/test_event_integrity_audit.py -v
python -m pytest skeleton/testing/test_event_architecture.py -v
python -m pytest skeleton/testing/test_operation_stream_store.py -v
```

No VOL-039 signoff or MDM-008 qualification is inferred from file existence
or these named tests; exact-head CI, independent review and canonical
accountability remain mandatory.
