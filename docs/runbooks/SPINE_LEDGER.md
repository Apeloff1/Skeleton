# P2 spine digest ledger

Machine owner: `skeleton/persistence/spine_ledger.py`

Appends the digest hash. A second record of the same empty operation keeps the same digest and raises the count. It does not dispatch and it does not advance a fence.

```bash
python -m pytest -q skeleton/testing/test_spine_ledger.py
```
