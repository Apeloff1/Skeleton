# P2 spine status, quarantine, and Mongo fence

Machine owners:

- `skeleton/persistence/mongo_fence.py`
- `skeleton/persistence/spine_quarantine.py`
- `skeleton/persistence/spine_status.py`

Mongo fence uses the injected protocol. Missing fence opens only at expected epoch 0. A stale epoch conflicts. A foreign tenant reads as unknown.

Quarantine lists poison marks for one tenant and does not repair them. Status reads the cursor and fence epoch. Neither card sets a completion checkbox.

```bash
python -m pytest -q skeleton/testing/test_mongo_fence.py skeleton/testing/test_spine_status.py
```
