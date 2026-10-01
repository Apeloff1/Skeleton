# P2 spine digest

Machine owner: `skeleton/persistence/spine_digest.py`

Hashes the gap card and the drift card with SHA-256. A second read of the same empty operation returns the same digest. It does not dispatch and it does not advance a fence.

```bash
python -m pytest -q skeleton/testing/test_spine_digest.py
```
