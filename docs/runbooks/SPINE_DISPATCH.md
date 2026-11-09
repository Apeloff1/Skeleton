# P2 spine dispatch hook

Machine owners:

- `skeleton/persistence/spine_cursor.py`
- `skeleton/persistence/spine_dispatch.py`

AI-tree mirrors are byte-identical.

`SpineDispatchHook` does not replace `DurableOperationRuntime.dispatch_outbox`. It publishes pending outbox rows, projects acknowledged identities into the inbox and tenant fence, then reads the cursor. A second run of the same row is a duplicate. The fence epoch stays put. Poison count is part of the cursor card.

No completion checkbox. No signatures. stored_prose=0. This does not merge PR #2333.

```bash
python -m pytest -q skeleton/testing/test_spine_dispatch.py skeleton/testing/test_spine_depth.py
```
