# P2 quarantine export

Machine owner: `skeleton/persistence/spine_export.py`

Writes the tenant quarantine card as JSON. It does not repair poison and it does not advance a fence.

```bash
python -m pytest -q skeleton/testing/test_spine_export.py
```
