# P2 duplicate replay

Machine owner: `skeleton/persistence/spine_replay.py`

Replays one delivery. A matching identity is a duplicate and the fence epoch is unchanged. A digest change is an InboxConflict and the epoch stays. Poison is not repaired.

```bash
python -m pytest -q skeleton/testing/test_spine_replay.py
```
