from core.shift_supervisor.models import PlanItem
from core.shift_supervisor.plan_api import PlanReadAPI
from core.shift_supervisor.plan_store import InMemoryPlanStore


def test_plan_read_api_returns_priority_ordered_team_work():
    store = InMemoryPlanStore()
    store.add_items([
        PlanItem(id="a", title="low", description="x", priority=10, target_team="night"),
        PlanItem(id="b", title="high", description="y", priority=90, target_team="night"),
        PlanItem(id="c", title="idle", description="z", priority=100, target_team="idle"),
    ])
    result = PlanReadAPI(store).pending_for_team("night")
    assert [item["id"] for item in result] == ["b", "a"]
