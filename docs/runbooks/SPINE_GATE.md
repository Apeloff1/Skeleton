# P2 hold gate and epoch watch

Machine owners:

- `skeleton/persistence/spine_gate.py`
- `skeleton/persistence/spine_watch.py`

A held outbox id is refused. The watch records epochs around a reaccept and raises if the fence moved.

```bash
python -m pytest -q skeleton/testing/test_spine_gate.py
```
