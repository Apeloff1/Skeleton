from __future__ import annotations

import pytest

from scripts.benchmark_frontier_events import run_benchmark


@pytest.mark.asyncio
async def test_event_benchmark_reports_behavior_without_latency_thresholds():
    report = await run_benchmark(events=12, replay_batch=5)

    assert report["workload"] == "frontier-event-journal-v1"
    assert report["source_semantics"] == {
        "repository": "Apeloff1/gameforge-rs",
        "path": "crates/gf-core/src/lib.rs",
        "blob": "481fcfca5a23272b70353eb09b7c3406bbc9bdd9",
    }
    assert report["configuration"] == {"events": 12, "replay_batch": 5}

    evidence = report["evidence"]
    assert evidence["journaled_events"] == 12
    assert evidence["pending_before_reopen"] == 12
    assert evidence["replayed_events"] == 12
    assert evidence["replay_batches"] == 3
    assert evidence["pending_after_replay"] == 0
    assert evidence["ordered_replay"] is True
    assert evidence["backpressure_observed"] is True
    assert evidence["backpressure_replayed"] == 1
    assert evidence["backpressure_recovered_sequence"] == [1]
    assert evidence["backpressure_pending_after"] == 0

    timing = report["timing"]
    assert timing["journal_seconds"] >= 0
    assert timing["replay_seconds"] >= 0
    assert timing["journal_ops_per_second"] is not None
    assert timing["replay_ops_per_second"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("events", "replay_batch", "message"),
    [
        (0, 1, "events must be positive"),
        (1, 0, "replay_batch must be positive"),
    ],
)
async def test_event_benchmark_rejects_invalid_workloads(events, replay_batch, message):
    with pytest.raises(ValueError, match=message):
        await run_benchmark(events=events, replay_batch=replay_batch)
