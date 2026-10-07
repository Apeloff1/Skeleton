"""Adversarial contract tests for durable run/checkpoint persistence."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.state import (
    InvalidTransition,
    PayloadTooLarge,
    RunNotFound,
    RunStatus,
    SQLiteRunStore,
    SchemaVersionError,
    StateConflict,
    StepStatus,
)


class Clock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_store(tmp_path, clock: Clock | None = None, **kwargs) -> SQLiteRunStore:
    return SQLiteRunStore(
        tmp_path / "runs.sqlite3",
        clock=clock or Clock(),
        **kwargs,
    )


def test_claim_is_revisioned_and_stale_compare_and_swap_fails(tmp_path):
    clock = Clock()
    store = make_store(tmp_path, clock)
    created = store.create_run("run-1", {"task": "compile"})

    claimed = store.claim_run(
        "run-1",
        "worker-a",
        lease_seconds=30,
        expected_revision=created.revision,
    )

    assert claimed.status is RunStatus.RUNNING
    assert claimed.worker_id == "worker-a"
    assert claimed.revision == 1

    with pytest.raises(StateConflict, match="stale run revision"):
        store.heartbeat(
            "run-1",
            "worker-a",
            expected_revision=created.revision,
        )


def test_live_lease_blocks_competing_worker_then_expires(tmp_path):
    clock = Clock()
    store = make_store(tmp_path, clock)
    store.create_run("run-1")
    first = store.claim_run("run-1", "worker-a", lease_seconds=10)

    with pytest.raises(StateConflict, match="another worker"):
        store.claim_run("run-1", "worker-b", lease_seconds=10)

    clock.advance(10.001)
    second = store.claim_run("run-1", "worker-b", lease_seconds=20)

    assert second.worker_id == "worker-b"
    assert second.revision == first.revision + 1
    with pytest.raises(StateConflict, match="does not own"):
        store.heartbeat("run-1", "worker-a")


def test_recoverable_listing_includes_pending_and_expired_not_live(tmp_path):
    clock = Clock()
    store = make_store(tmp_path, clock)
    store.create_run("pending")
    store.create_run("expired")
    store.create_run("live")
    store.claim_run("expired", "worker-a", lease_seconds=5)
    store.claim_run("live", "worker-b", lease_seconds=50)

    clock.advance(6)
    recoverable = {run.run_id for run in store.list_recoverable()}

    assert recoverable == {"pending", "expired"}


def test_restart_replays_only_work_after_last_checkpoint(tmp_path):
    clock = Clock()
    path = tmp_path / "runs.sqlite3"
    first_process = SQLiteRunStore(path, clock=clock)
    first_process.create_run("run-1", {"request": 7})
    first_process.claim_run("run-1", "worker-a", lease_seconds=5)

    first_process.start_step(
        "run-1",
        "step-1",
        "tool",
        worker_id="worker-a",
        payload={"n": 1},
        effect_key="effect-1",
    )
    first_process.finish_step(
        "run-1",
        "step-1",
        StepStatus.SUCCEEDED,
        worker_id="worker-a",
        result={"ok": 1},
    )
    first_process.checkpoint(
        "run-1",
        {"cursor": 1},
        worker_id="worker-a",
        after_step_id="step-1",
        state_version=3,
    )

    first_process.start_step(
        "run-1",
        "step-2",
        "tool",
        worker_id="worker-a",
        payload={"n": 2},
        effect_key="effect-2",
    )
    first_process.finish_step(
        "run-1",
        "step-2",
        StepStatus.SUCCEEDED,
        worker_id="worker-a",
        result={"ok": 2},
    )

    # Simulate process death: no graceful release, only lease expiry.
    clock.advance(6)
    second_process = SQLiteRunStore(path, clock=clock)
    second_process.claim_run("run-1", "worker-b", lease_seconds=30)
    resume = second_process.resume_state("run-1")

    assert resume.checkpoint is not None
    assert resume.checkpoint.state == {"cursor": 1}
    assert resume.checkpoint.state_version == 3
    assert [step.step_id for step in resume.replay_steps] == ["step-2"]
    assert resume.replay_steps[0].status is StepStatus.SUCCEEDED

    # Re-issuing an already-known step is idempotent and does not duplicate it.
    replay = second_process.start_step(
        "run-1",
        "step-2",
        "tool",
        worker_id="worker-b",
        payload={"n": 2},
        effect_key="effect-2",
    )
    assert replay.status is StepStatus.SUCCEEDED
    assert [step.step_id for step in second_process.list_steps("run-1")] == [
        "step-1",
        "step-2",
    ]


def test_effect_key_cannot_be_rebound_to_different_step(tmp_path):
    store = make_store(tmp_path)
    store.create_run("run-1")
    store.claim_run("run-1", "worker-a")
    store.start_step(
        "run-1",
        "step-1",
        "publish",
        worker_id="worker-a",
        effect_key="release-v1",
    )

    with pytest.raises(StateConflict, match="effect_key"):
        store.start_step(
            "run-1",
            "step-2",
            "publish",
            worker_id="worker-a",
            effect_key="release-v1",
        )


def test_step_identity_cannot_change_semantics_on_replay(tmp_path):
    store = make_store(tmp_path)
    store.create_run("run-1")
    store.claim_run("run-1", "worker-a")
    store.start_step(
        "run-1",
        "step-1",
        "tool",
        worker_id="worker-a",
        payload={"arg": "safe"},
        effect_key="effect-1",
    )

    with pytest.raises(StateConflict, match="different semantics"):
        store.start_step(
            "run-1",
            "step-1",
            "tool",
            worker_id="worker-a",
            payload={"arg": "changed"},
            effect_key="effect-1",
        )


def test_concurrent_duplicate_start_is_single_persisted_step(tmp_path):
    clock = Clock()
    store = make_store(tmp_path, clock)
    store.create_run("run-1")
    store.claim_run("run-1", "worker-a", lease_seconds=60)

    def start():
        return store.start_step(
            "run-1",
            "step-1",
            "tool",
            worker_id="worker-a",
            payload={"x": 1},
            effect_key="effect-1",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: start(), range(16)))

    assert {result.sequence for result in results} == {1}
    assert {result.step_id for result in results} == {"step-1"}
    assert len(store.list_steps("run-1")) == 1


def test_checkpoint_requires_completed_boundary_and_cannot_move_backwards(tmp_path):
    store = make_store(tmp_path)
    store.create_run("run-1")
    store.claim_run("run-1", "worker-a")
    store.start_step("run-1", "step-1", "tool", worker_id="worker-a")

    with pytest.raises(InvalidTransition, match="succeeded or skipped"):
        store.checkpoint(
            "run-1",
            {"cursor": 1},
            worker_id="worker-a",
            after_step_id="step-1",
        )

    store.finish_step(
        "run-1",
        "step-1",
        StepStatus.SUCCEEDED,
        worker_id="worker-a",
    )
    store.checkpoint(
        "run-1",
        {"cursor": 1},
        worker_id="worker-a",
        after_step_id="step-1",
    )
    store.start_step("run-1", "step-2", "tool", worker_id="worker-a")
    store.finish_step(
        "run-1",
        "step-2",
        StepStatus.SKIPPED,
        worker_id="worker-a",
    )
    store.checkpoint(
        "run-1",
        {"cursor": 2},
        worker_id="worker-a",
        after_step_id="step-2",
    )

    with pytest.raises(InvalidTransition, match="move backwards"):
        store.checkpoint(
            "run-1",
            {"cursor": 1},
            worker_id="worker-a",
            after_step_id="step-1",
        )


def test_success_requires_no_unfinished_steps_and_terminal_run_is_immutable(tmp_path):
    store = make_store(tmp_path)
    store.create_run("run-1")
    store.claim_run("run-1", "worker-a")
    store.start_step("run-1", "step-1", "tool", worker_id="worker-a")

    with pytest.raises(InvalidTransition, match="unfinished"):
        store.transition_run(
            "run-1",
            RunStatus.SUCCEEDED,
            worker_id="worker-a",
        )

    store.finish_step(
        "run-1",
        "step-1",
        StepStatus.SUCCEEDED,
        worker_id="worker-a",
        result={"done": True},
    )
    done = store.transition_run(
        "run-1",
        RunStatus.SUCCEEDED,
        worker_id="worker-a",
        output={"answer": 42},
    )

    assert done.status is RunStatus.SUCCEEDED
    assert done.output == {"answer": 42}
    assert done.worker_id is None
    assert store.get_run("run-1").status is RunStatus.SUCCEEDED

    with pytest.raises(InvalidTransition, match="terminal"):
        store.claim_run("run-1", "worker-b")
    with pytest.raises(InvalidTransition, match="invalid run transition"):
        store.transition_run("run-1", RunStatus.CANCELLED)


def test_wrong_or_expired_worker_cannot_mutate_steps_or_checkpoints(tmp_path):
    clock = Clock()
    store = make_store(tmp_path, clock)
    store.create_run("run-1")
    store.claim_run("run-1", "worker-a", lease_seconds=5)

    with pytest.raises(StateConflict, match="does not own"):
        store.start_step("run-1", "step-1", "tool", worker_id="worker-b")

    clock.advance(6)
    with pytest.raises(StateConflict, match="expired"):
        store.start_step("run-1", "step-1", "tool", worker_id="worker-a")
    with pytest.raises(StateConflict, match="expired"):
        store.checkpoint("run-1", {"cursor": 0}, worker_id="worker-a")


def test_schema_version_mismatch_fails_closed(tmp_path):
    path = tmp_path / "runs.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 999")
    conn.close()

    with pytest.raises(SchemaVersionError, match="unsupported"):
        SQLiteRunStore(path)


def test_claimed_schema_version_without_tables_fails_closed(tmp_path):
    path = tmp_path / "runs.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 1")
    conn.close()

    with pytest.raises(SchemaVersionError, match="incomplete"):
        SQLiteRunStore(path)


def test_payload_limits_and_nonfinite_json_fail_before_persistence(tmp_path):
    store = make_store(tmp_path, max_payload_bytes=32)

    with pytest.raises(PayloadTooLarge):
        store.create_run("too-big", {"blob": "x" * 100})
    with pytest.raises(ValueError, match="finite JSON"):
        store.create_run("nan", {"value": float("nan")})
    with pytest.raises(RunNotFound):
        store.get_run("too-big")


def test_pending_run_cannot_bypass_claim_transition(tmp_path):
    store = make_store(tmp_path)
    store.create_run("run-1")

    with pytest.raises(InvalidTransition, match="pending -> running"):
        store.transition_run("run-1", RunStatus.RUNNING)

    cancelled = store.transition_run("run-1", RunStatus.CANCELLED)
    assert cancelled.status is RunStatus.CANCELLED


@pytest.mark.parametrize("lease", [0, -1, float("nan"), float("inf"), True])
def test_invalid_lease_durations_fail_closed(tmp_path, lease):
    store = make_store(tmp_path)
    store.create_run("run-1")

    with pytest.raises(ValueError, match="lease_seconds"):
        store.claim_run("run-1", "worker-a", lease_seconds=lease)
