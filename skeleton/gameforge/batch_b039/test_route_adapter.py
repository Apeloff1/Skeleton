"""B039 ↔ B031/B038 seam tests."""
import pytest

from skeleton.frontier.runtime.model_router_contract import CallBudget, RouteStatus, RoutingReceipt
from skeleton.gameforge import batch_b038
from skeleton.gameforge.batch_b039 import (
    BudgetExceeded, Diagnosis, ProvenanceRecord, RouteChoice, digest, repair_route_task,
)


def _receipt(status=RouteStatus.PLANNED, provider="p1", cost=0.5):
    return RoutingReceipt(request_id="r", task_type="gameforge.self_repair", backend="t",
                          status=status, selected_provider_id=provider, fallback_chain=(),
                          rejected={}, budget=CallBudget(), decided_at=0.0, estimated_cost=cost)


def test_provenance_and_digest_come_from_b038():
    assert ProvenanceRecord is batch_b038.ProvenanceRecord
    assert digest is batch_b038.digest


def test_from_receipt_maps_provider_and_cost():
    rc = RouteChoice.from_receipt(_receipt(), model="m")
    assert (rc.model, rc.provider, rc.unit_cost) == ("m", "p1", 0.5)
    assert rc.as_dict()["receipt"]["selected_provider_id"] == "p1"


def test_from_receipt_refuses_unusable_route():
    with pytest.raises(BudgetExceeded):
        RouteChoice.from_receipt(_receipt(status=RouteStatus.NO_ROUTE, provider=None))


def test_plain_route_choice_still_works():
    assert RouteChoice("m", "p").as_dict() == {"model": "m", "provider": "p", "unit_cost": 0.0}


def test_repair_route_task():
    t = repair_route_task((Diagnosis("logic", ("a",), "h"),), request_id="x")
    assert t.task_type == "gameforge.self_repair" and t.metadata["diagnoses"] == ["logic"]
