from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.policy import (
    may_admit_worker,
    may_delegate,
    overtime_exceeds_soft_limit,
)
from core.shift_supervisor.squads import safe_squad_capacity


def _item(*, team: str = "night", status: str = "queued") -> PlanItem:
    return PlanItem(
        id="x",
        title="x",
        description="x",
        priority=1,
        target_team=team,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
    )


def _worker(
    *,
    team: str = "night",
    status: str = "idle",
    overtime: int = 0,
    task_id: str | None = None,
) -> WorkerState:
    return WorkerState(
        worker_id="n",
        team=team,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        overtime_minutes=overtime,
        current_task_id=task_id,
    )


def test_policy_blocks_cross_team_and_overtime():
    item = _item()
    idle_worker = _worker(team="idle")
    assert may_delegate(worker=idle_worker, item=item, overtime_soft_limit_minutes=120).reason == "cross-team"

    overtime_worker = _worker(status="idle", overtime=120)
    assert (
        may_delegate(worker=overtime_worker, item=item, overtime_soft_limit_minutes=120).reason
        == "overtime-soft-limit"
    )


def test_preemptive_admission_refuses_blocked_offline_working_and_occupied_workers():
    assert may_admit_worker(worker=_worker(status="blocked"), overtime_soft_limit_minutes=120).reason == "worker-blocked"
    assert may_admit_worker(worker=_worker(status="offline"), overtime_soft_limit_minutes=120).reason == "worker-offline"
    assert may_admit_worker(worker=_worker(status="working"), overtime_soft_limit_minutes=120).reason == "worker-working"
    assert (
        may_admit_worker(
            worker=_worker(status="idle", task_id="still-busy"),
            overtime_soft_limit_minutes=120,
        ).reason
        == "worker-occupied"
    )
    allowed = may_admit_worker(worker=_worker(status="idle"), overtime_soft_limit_minutes=120)
    assert allowed.allowed is True
    assert allowed.reason == "allowed"


def test_zero_overtime_limit_admits_zero_minutes_and_rejects_any_overtime():
    assert overtime_exceeds_soft_limit(0, 0) is False
    assert overtime_exceeds_soft_limit(1, 0) is True
    assert overtime_exceeds_soft_limit(119, 120) is False
    assert overtime_exceeds_soft_limit(120, 120) is True
    assert may_admit_worker(worker=_worker(overtime=0), overtime_soft_limit_minutes=0).allowed is True
    assert may_admit_worker(worker=_worker(overtime=1), overtime_soft_limit_minutes=0).reason == "overtime-soft-limit"


def test_may_delegate_refuses_terminal_items_after_worker_admission():
    worker = _worker()
    done = may_delegate(worker=worker, item=_item(status="done"), overtime_soft_limit_minutes=120)
    rejected = may_delegate(worker=worker, item=_item(status="rejected"), overtime_soft_limit_minutes=120)
    assert done.reason == "terminal-item"
    assert rejected.reason == "terminal-item"


def test_squad_capacity_uses_canonical_admission_gate():
    idle = [_worker() for _ in range(4)]
    for index, worker in enumerate(idle):
        worker.worker_id = f"night-{index}"
    blocked = _worker(status="blocked")
    blocked.worker_id = "night-blocked"
    overtime = _worker(overtime=120)
    overtime.worker_id = "night-ot"
    working = _worker(status="working")
    working.worker_id = "night-working"
    assert safe_squad_capacity(idle + [blocked, overtime, working], "night") == 1
