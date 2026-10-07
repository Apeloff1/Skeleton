# P2 index plan and worker bind

Machine owners:

- `skeleton/persistence/spine_index.py`
- `skeleton/persistence/spine_bind.py`

The index plan lists three unique indexes and calls create_index only when the collection has that method. The memory stand-in skips. The bind starts SpineWorker and does not call DurableOperationRuntime.start_dispatcher.

```bash
python -m pytest -q skeleton/testing/test_spine_index.py
```
