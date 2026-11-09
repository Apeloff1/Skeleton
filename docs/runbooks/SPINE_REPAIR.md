# P2 Mongo projection and repair plan

Machine owners:

- `skeleton/persistence/mongo_projection.py`
- `skeleton/persistence/spine_repair.py`

MongoSpineProjection reads acknowledged SQLite outbox rows, accepts them into MongoInboxLedger, and advances MongoConsistencyFence only on a new accept. A second project is a duplicate. The fence epoch stays put.

SpineRepairPlan turns quarantine marks into intents. applied stays 0. The fence is not advanced.

```bash
python -m pytest -q skeleton/testing/test_mongo_projection.py skeleton/testing/test_spine_repair.py
```
