# P2 cutover card and published window

Machine owners:

- `skeleton/persistence/spine_cutover.py`
- `skeleton/persistence/spine_window.py`

The window lists published outbox identities for one tenant. A foreign tenant gets count 0. The cutover card reads lag, drift, and the apply gate. applied stays 0. Neither call dispatches.

```bash
python -m pytest -q skeleton/testing/test_spine_cutover.py
```
