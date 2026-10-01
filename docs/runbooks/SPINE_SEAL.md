# P2 seal and gap

Machine owners:

- `skeleton/persistence/spine_seal.py`
- `skeleton/persistence/spine_gap.py`

The seal stores a cutover card. applied stays 0. The gap lists published versions above the inbox watermark and does not accept them.

```bash
python -m pytest -q skeleton/testing/test_spine_seal.py
```
