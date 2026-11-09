# P2 spine batch and witness

Machine owners:

- `skeleton/persistence/spine_batch.py`
- `skeleton/persistence/spine_witness.py`

The batch runs the dispatch hook once per operation id, capped at 256. A poison counts as failed and does not stop the rest. The witness bundles lag, catalog, and status. It does not dispatch.

```bash
python -m pytest -q skeleton/testing/test_spine_batch.py
```
