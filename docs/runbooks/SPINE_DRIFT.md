# P2 fence drift and apply gate

Machine owners:

- `skeleton/persistence/spine_drift.py`
- `skeleton/persistence/spine_apply.py`

Drift compares one resource on the SQLite fence and the Mongo fence. A missing side is epoch 0. Neither fence is advanced.

The apply gate records a refusal. applied stays 0.

```bash
python -m pytest -q skeleton/testing/test_spine_drift.py
```
