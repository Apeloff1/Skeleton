# P2 lag and tenant catalogs

Machine owners:

- `skeleton/persistence/spine_lag.py`
- `skeleton/persistence/spine_catalog.py`
- `skeleton/persistence/mongo_catalog.py`

Lag counts pending against published and does not dispatch. Catalogs list fence resources for one tenant. A foreign tenant gets an empty list, not another epoch.

```bash
python -m pytest -q skeleton/testing/test_spine_catalog.py
```
