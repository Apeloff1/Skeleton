from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker
from skeleton.api.swarm_tenant_broker_routes import TenantCompletion, TenantFailure, TenantSubmission, fail, submit, succeed, tenant_broker_status


def _broker() -> TenantSwarmBroker:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w", capacity=2)
    return TenantSwarmBroker(
        SwarmBroker(runtime),
        SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100),
    )


def test_tenant_broker_api_submit_and_success() -> None:
    broker = _broker()
    submitted = submit(TenantSubmission(tenant="acme", task_id="task", payload={"x": 1}), broker=broker)
    assert submitted["admitted"] is True
    assert submitted["leased"] is True

    completed = succeed("w", "task", TenantCompletion(completion_token="done"), broker=broker)
    assert completed["state"] == "succeeded"
    assert completed["tenant"] == "acme"
    assert completed["duplicate"] is False


def test_tenant_broker_api_retry_requeues_tenant_accounting() -> None:
    broker = _broker()
    submit(TenantSubmission(tenant="acme", task_id="task", max_attempts=2), broker=broker)
    result = fail("w", "task", TenantFailure(error="retry", completion_token="attempt-1"), broker=broker)
    assert result["state"] == "queued"
    status = tenant_broker_status(broker=broker)
    assert status["ingress"]["phases"]["acme:task"] == "queued"


def test_tenant_broker_api_duplicate_success_is_idempotent() -> None:
    broker = _broker()
    submit(TenantSubmission(tenant="acme", task_id="task"), broker=broker)
    first = succeed("w", "task", TenantCompletion(completion_token="same"), broker=broker)
    second = succeed("w", "task", TenantCompletion(completion_token="same"), broker=broker)
    assert first["duplicate"] is False
    assert second["duplicate"] is True
