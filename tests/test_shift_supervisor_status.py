from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.status import status_payload


def test_status_payload_is_monitoring_friendly():
    payload = status_payload(InMemoryPlanStore())
    assert payload["clocked_in"] == 0
    assert payload["queued_items"] == 0
    assert "checked_at" in payload
