from __future__ import annotations

import pytest

from skeleton.agents.swarm_fairness import FairShareLedger
from skeleton.agents.swarm_maintenance import compact_runtime, compact_state
from skeleton.agents.swarm_rate_limit import TokenBucketLimiter
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.agents.swarm_snapshot import SnapshotError, normalize_snapshot, validate_snapshot


def test_weighted_fair_share_prefers_lower_virtual_load() -> None:
    ledger = FairShareLedger()
    ledger.configure("gold", weight=4)
    ledger.configure("bronze", weight=1)
    ledger.admit("bronze")
    ledger.admit("gold")
    assert ledger.preferred(["bronze", "gold"]) == "gold"


def test_fair_share_completion_releases_inflight() -> None:
    ledger = FairShareLedger()
    ledger.admit("tenant")
    ledger.complete("tenant")
    assert ledger.snapshot()["tenant"]["inflight"] == 0
    assert ledger.snapshot()["tenant"]["completed"] == 1


def test_token_bucket_refills_deterministically() -> None:
    now = [0.0]
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=1, clock=lambda: now[0])
    assert limiter.allow("tenant")
    assert limiter.allow("tenant")
    assert not limiter.allow("tenant")
    now[0] = 1.0
    assert limiter.allow("tenant")


def test_snapshot_validation_rejects_duplicate_task_ids() -> None:
    state = {"version": 1, "config": {}, "workers": [], "counters": {}, "tasks": [{"id": "x"}, {"id": "x"}]}
    with pytest.raises(SnapshotError):
        validate_snapshot(state)


def test_snapshot_normalization_is_deterministic() -> None:
    state = {"version": 1, "config": {}, "workers": [{"id": "b"}, {"id": "a"}], "counters": {"z": 1, "a": 2}, "tasks": [{"id": "b"}, {"id": "a"}]}
    normalized = normalize_snapshot(state)
    assert [task["id"] for task in normalized["tasks"]] == ["a", "b"]
    assert [worker["id"] for worker in normalized["workers"]] == ["a", "b"]


def test_compaction_keeps_only_latest_terminal_budget() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=3)
    for task_id in ("a", "b", "c"):
        runtime.submit(SwarmTask(task_id, {}))
    for task in runtime.lease("w", limit=3):
        runtime.succeed("w", task.id)
    state = compact_state(runtime, max_terminal_tasks=1)
    assert len(state["tasks"]) == 1
    assert state["maintenance"]["pruned_terminal_tasks"] == 2


def test_compacted_runtime_remains_restorable() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}))
    task = runtime.lease("w")[0]
    runtime.succeed("w", task.id)
    restored = compact_runtime(runtime, max_terminal_tasks=0)
    assert restored.task("a") is None
