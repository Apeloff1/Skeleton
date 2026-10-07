from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib

import pytest

from skeleton.ai.runtime.autonomous_engineering.worker import (
    AutonomousWorkerController,
    WorkerBudget,
    WorkerCheckpointStore,
    WorkerControlError,
)


NOW=datetime(2026,10,2,5,0,tzinfo=timezone.utc)
FINGERPRINT=hashlib.sha256(b"repo-v1").hexdigest()
AUTH=hashlib.sha256(b"authority").hexdigest()


def _controller(tmp_path, *, steps=4, actions=3, cost="5"):
    return AutonomousWorkerController(
        WorkerCheckpointStore(tmp_path/"worker.sqlite3"),
        WorkerBudget(
            max_steps=steps,
            max_actions=actions,
            max_cost=Decimal(cost),
        ),
    )


def _start(controller):
    return controller.start(
        run_id="run-1",
        objective="Complete bounded repository work.",
        repository_fingerprint=FINGERPRINT,
        authority_digest=AUTH,
        deadline_at=NOW+timedelta(hours=1),
        now=NOW,
        evidence_refs=("authority:grant",),
    )


def test_checkpoint_reopens_and_recovers_after_interruption(tmp_path) -> None:
    controller=_controller(tmp_path)
    cp=_start(controller)
    cp=controller.checkpoint_step(
        cp.run_id,
        repository_fingerprint=FINGERPRINT,
        cost_delta="1",
        action_delta=1,
        conflict_domains=("repo:skeleton",),
        evidence_refs=("step:1",),
        now=NOW+timedelta(minutes=1),
    )
    cp=controller.interrupt(
        cp.run_id,
        evidence_ref="interrupt:process-exit",
        now=NOW+timedelta(minutes=2),
    )
    assert cp.status=="interrupted"

    reopened=AutonomousWorkerController(
        WorkerCheckpointStore(tmp_path/"worker.sqlite3"),
        WorkerBudget(max_steps=4,max_actions=3,max_cost=Decimal("5")),
    )
    recovered=reopened.store.get("run-1")
    assert recovered is not None
    assert recovered.steps_used==1
    resumed=reopened.resume(
        "run-1",
        repository_fingerprint=FINGERPRINT,
        resume_authority_ref="resume:operator",
        now=NOW+timedelta(minutes=3),
    )
    assert resumed.status=="active"
    assert resumed.actions_used==1


def test_stale_repository_blocks_resume(tmp_path) -> None:
    controller=_controller(tmp_path)
    cp=_start(controller)
    controller.interrupt(
        cp.run_id,
        evidence_ref="interrupt:pause",
        now=NOW+timedelta(minutes=1),
    )
    with pytest.raises(WorkerControlError,match="stale repository"):
        controller.resume(
            cp.run_id,
            repository_fingerprint=hashlib.sha256(b"repo-v2").hexdigest(),
            resume_authority_ref="resume:operator",
            now=NOW+timedelta(minutes=2),
        )


def test_deadline_blocks_further_work(tmp_path) -> None:
    controller=_controller(tmp_path)
    cp=controller.start(
        run_id="deadline-run",
        objective="Bounded work.",
        repository_fingerprint=FINGERPRINT,
        authority_digest=AUTH,
        deadline_at=NOW+timedelta(seconds=1),
        now=NOW,
        evidence_refs=("authority:grant",),
    )
    with pytest.raises(WorkerControlError,match="deadline exhausted"):
        controller.checkpoint_step(
            cp.run_id,
            repository_fingerprint=FINGERPRINT,
            cost_delta="0",
            action_delta=0,
            evidence_refs=("step:late",),
            now=NOW+timedelta(seconds=2),
        )


def test_resource_exhaustion_is_fail_closed(tmp_path) -> None:
    controller=_controller(tmp_path,steps=1,actions=1,cost="1")
    cp=_start(controller)
    cp=controller.checkpoint_step(
        cp.run_id,
        repository_fingerprint=FINGERPRINT,
        cost_delta="1",
        action_delta=1,
        evidence_refs=("step:1",),
        now=NOW+timedelta(minutes=1),
    )
    with pytest.raises(WorkerControlError,match="step budget exhausted"):
        controller.checkpoint_step(
            cp.run_id,
            repository_fingerprint=FINGERPRINT,
            cost_delta="0",
            action_delta=0,
            evidence_refs=("step:2",),
            now=NOW+timedelta(minutes=2),
        )


def test_human_override_is_terminal_halt(tmp_path) -> None:
    controller=_controller(tmp_path)
    cp=_start(controller)
    halted=controller.human_override(
        cp.run_id,
        override_ref="operator:stop",
        now=NOW+timedelta(minutes=1),
    )
    assert halted.status=="halted"
    with pytest.raises(WorkerControlError,match="not active"):
        controller.checkpoint_step(
            cp.run_id,
            repository_fingerprint=FINGERPRINT,
            cost_delta="0",
            action_delta=0,
            evidence_refs=("step:no",),
            now=NOW+timedelta(minutes=2),
        )


def test_optimistic_revision_rejects_stale_checkpoint_writer(tmp_path) -> None:
    controller=_controller(tmp_path)
    cp=_start(controller)
    stale=cp
    current=controller.checkpoint_step(
        cp.run_id,
        repository_fingerprint=FINGERPRINT,
        cost_delta="0",
        action_delta=0,
        evidence_refs=("step:1",),
        now=NOW+timedelta(minutes=1),
    )
    # Direct store write simulates a stale process that still believes revision 0.
    with pytest.raises(WorkerControlError,match="stale checkpoint write"):
        controller.store.put(stale,expected_revision=0)
    assert controller.store.get(cp.run_id)==current


def test_completed_worker_cannot_continue(tmp_path) -> None:
    controller=_controller(tmp_path)
    cp=_start(controller)
    done=controller.complete(
        cp.run_id,
        repository_fingerprint=FINGERPRINT,
        evidence_refs=("verify:complete",),
        now=NOW+timedelta(minutes=1),
    )
    assert done.status=="completed"
    with pytest.raises(WorkerControlError,match="not active"):
        controller.checkpoint_step(
            cp.run_id,
            repository_fingerprint=FINGERPRINT,
            cost_delta="0",
            action_delta=0,
            evidence_refs=("step:after",),
            now=NOW+timedelta(minutes=2),
        )
