# P2 inbox and consistency fence

Machine owners:

- `skeleton/persistence/inbox_ledger.py`
- `skeleton/persistence/consistency_fence.py`

AI-tree mirrors live under `skeleton/ai/runtime/persistence/` and must stay semantically identical.

## What this slice does

The runtime spine already commits operation state and an outbox row in one transaction. This slice is the consumer side of that contract.

- An inbox accepts only a published outbox identity.
- Receipt and per-operation watermark commit together.
- Same event identity plus same payload digest is an idempotent replay.
- Digest, tenant, version, or type drift on a reused event identity is a conflict.
- Versions are contiguous. The first accept is version 1.
- A consistency fence opens at epoch 1 per tenant and resource.
- Later writes must present the current epoch.
- A foreign tenant cannot observe another tenant's fence.

## What this slice does not do

No completion checkbox. No implementation signature. No verification signature. No masterplan maturity promotion. No T1 activation. `stored_prose` stays 0.

## Local check

```bash
python -m pytest -q skeleton/testing/test_inbox_ledger.py skeleton/testing/test_consistency_fence.py
```
