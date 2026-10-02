# P2 drift sweep

Machine owner: `skeleton/persistence/spine_sweep.py`

Scans a bounded resource list for one tenant. A missing Mongo fence counts as a mismatch. Neither fence is advanced.

```bash
python -m pytest -q skeleton/testing/test_spine_sweep.py
```
