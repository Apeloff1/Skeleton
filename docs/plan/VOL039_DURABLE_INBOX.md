# VOL-039 — Durable AI inbox and causal replay persistence

The canonical `skeleton/ai/inbox_causality.py` model remains the source of
truth for `InboundMessage`, `ProcessingReceipt`, `QuarantineReceipt` and
their deterministic receipt identity. New public factories
`processing_receipt()` and `quarantine_receipt()` are shared by the
reference model and the SQLite implementation; no second message identity or
hash algorithm is introduced.

`SQLiteInboxLedger` in `skeleton/ai/inbox_sqlite.py` provides:

- durable processed-message deduplication and byte-for-byte equivalent
  reference `ProcessingReceipt` identities after process restart;
- fenced producer epochs and contiguous monotonic sequence admission;
- optional mandatory committed causal predecessors, checked within the
  transaction; cross-producer causes are allowed only after their receipts
  are present;
- atomic SQLite commit of processing identity plus producer high-water mark;
- immutable quarantine evidence, independently bounded to a configurable
  maximum; bounded effect/cause lists and strict UTF-8 identity parsing;
- fixed persisted replay-window, receipt-budget and cause-policy settings;
  reopening with relaxed rules is refused until explicitly migrated;
- cross-connection concurrency governed by SQLite `BEGIN IMMEDIATE`,
  WAL, synchronous FULL, and transaction rollback after failed insert.

## Actual authority boundary

An inbox **processing receipt** records a caller-supplied
`write_receipt_id` from the real effect owner. Creating that receipt alone
does not execute an effect or prove that external effects were committed.
When effect state lives in a separate datastore, use the preexisting
outbox/inbox and compensation protocol; no cross-database exactly-once claim
is made by the SQLite adapter.

The adapter deliberately has no repair, credential, tool or model-execution
authority. The operator must preprovision the DB directory, provide backups,
and independently validate the committed effect witness. An in-process test
of two SQLite connections does not establish multi-host consensus.

## Examples

```python
from skeleton.ai.inbox_causality import InboundMessage
from skeleton.ai.inbox_sqlite import SQLiteInboxLedger

with SQLiteInboxLedger("/var/lib/skeleton/ai-inbox.sqlite") as inbox:
    msg = InboundMessage.create(
        "crawler-worker", producer_epoch=1, sequence=0,
        payload_digest="sha256:validated-payload",
    )
    prior = inbox.admit(msg)
    if prior is None:
        # Only AFTER the canonical effect owner has committed and issued
        # its durable write receipt may this ledger record its identity.
        receipt = inbox.commit(msg, write_receipt_id="trusted-effect-receipt")
```

Run `python -m pytest skeleton/testing/test_inbox_sqlite.py -v` together
with the canonical event stream suites and any existing inbox/outbox conformance
tests. Preserve the original VOL-039 independent verification boundary;
no change made here automatically signs or closes the volume.
