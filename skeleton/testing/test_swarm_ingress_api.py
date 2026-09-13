import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.api.swarm_ingress_routes import (
    IngressRequest,
    TaskAccountingRequest,
    TenantConfiguration,
    admit,
    complete,
    configure_tenant,
    ingress_status,
    mark_leased,
)


def test_ingress_api_full_accounting_flow() -> None:
    governor = SwarmIngressGovernor(rate_capacity=10, rate_refill_per_second=1)
    configured = configure_tenant(
        "tenant",
        TenantConfiguration(weight=2, max_queued=2, max_leased=2, max_payload_bytes=1000),
        governor=governor,
    )
    assert configured["configured"] is True

    admitted = admit(IngressRequest(tenant="tenant", task_id="task", payload={"x": 1}), governor=governor)
    assert admitted["accepted"] is True
    assert mark_leased(TaskAccountingRequest(tenant="tenant", task_id="task"), governor=governor)["phase"] == "leased"
    assert complete(TaskAccountingRequest(tenant="tenant", task_id="task"), governor=governor)["completed"] is True
    assert ingress_status(governor=governor)["accounted_tasks"] == 0


def test_ingress_api_quota_rejection_is_conflict() -> None:
    governor = SwarmIngressGovernor()
    configure_tenant(
        "tiny",
        TenantConfiguration(max_queued=1, max_leased=1, max_payload_bytes=2),
        governor=governor,
    )
    with pytest.raises(HTTPException) as exc:
        admit(IngressRequest(tenant="tiny", task_id="task", payload={"x": "large"}), governor=governor)
    assert exc.value.status_code == 409


def test_ingress_api_rate_rejection_is_429() -> None:
    governor = SwarmIngressGovernor(rate_capacity=1, rate_refill_per_second=0.000001)
    assert admit(IngressRequest(tenant="tenant", task_id="first"), governor=governor)["accepted"] is True
    with pytest.raises(HTTPException) as exc:
        admit(IngressRequest(tenant="tenant", task_id="second"), governor=governor)
    assert exc.value.status_code == 429
