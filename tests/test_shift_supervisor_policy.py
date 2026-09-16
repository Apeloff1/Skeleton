from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.policy import may_delegate


def test_policy_blocks_cross_team_and_overtime():
    item = PlanItem(id="x", title="x", description="x", priority=1, target_team="night")
    idle_worker = WorkerState(worker_id="i", team="idle", status="idle")
    assert may_delegate(worker=idle_worker, item=item, overtime_soft_limit_minutes=120).reason == "cross-team"

    night_worker = WorkerState(worker_id="n", team="night", status="working", overtime_minutes=120)
    assert may_delegate(worker=night_worker, item=item, overtime_soft_limit_minutes=120).reason == "overtime-soft-limit"
