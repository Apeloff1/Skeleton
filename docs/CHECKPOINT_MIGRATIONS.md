# Checkpoint migration discipline

Durable run recovery must survive application upgrades without teaching the SQLite storage layer every subsystem's state schema. `CheckpointMigrator` provides that boundary: storage records `state_version`; the owning subsystem registers deterministic migrations from version `N` to `N + 1`.

## Contract

A migrator has one declared `current_version`. Every historical version that can still appear in retained checkpoints needs a contiguous forward path to that version. Missing edges fail before any migration executes. Downgrades and checkpoints newer than the running code are rejected.

```python
from skeleton.state import CheckpointMigrator

migrator = CheckpointMigrator(current_version=3)

@migrator.migration(1)
def v1_to_v2(state):
    state["phase"] = state.pop("stage", "pending")
    return state

@migrator.migration(2)
def v2_to_v3(state):
    state["tasks"] = [
        {"name": name, "status": "pending"}
        for name in state.pop("task_names", [])
    ]
    return state

restored = migrator.migrate(checkpoint.state, checkpoint.state_version)
```

The input is detached before migration and every intermediate output is round-tripped through strict JSON validation. Non-finite values, unserializable objects, and oversized states are rejected at the version boundary that produced them. A migration function's raw exception is retained as the Python exception cause for debugging, but the public migration error names only the failing version edge rather than copying arbitrary exception text into higher-level state.

## Rules for migrations

Migration functions should be deterministic and side-effect free. They must not perform network calls, mutate external databases, invoke tools, or depend on wall-clock time. Their only job is to transform one persisted checkpoint representation into the next representation.

Do not skip versions to make a migration graph shorter. If version 2 introduced an invariant that version 3 relies on, a direct 1-to-3 jump can silently bypass it. The registry therefore accepts only one-version edges and verifies the whole requested path before starting work.

Keep migrations after the application moves forward. A durable store can retain old failed or interrupted runs for investigation or later recovery, so deleting an old migration is a compatibility break even if newly-created checkpoints no longer use that version.

## Operational limits

`max_steps` bounds how many migrations a single recovery can execute, protecting startup from unexpectedly long historical chains. `max_payload_bytes` applies before the first migration and after every edge, preventing migration code from expanding a small checkpoint into unbounded state.

When a subsystem intentionally stops supporting a historical checkpoint version, make that an explicit compatibility decision: archive or terminalize affected runs, document the minimum recoverable version, and only then remove the obsolete migration path.
