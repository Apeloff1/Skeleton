from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.api.server import ServerState, create_app


def test_server_rebind_preserves_tenant_broker_metadata() -> None:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))

    replacement = HardenedSwarmRuntime()
    replacement.submit(SwarmTask("task", {}))
    state.bind_swarm_runtime(replacement)

    assert state.swarm_tenant_broker.broker is state.swarm_broker
    assert state.swarm_tenant_broker.tenant_for("task") == "acme"
    assert state.swarm_tenant_broker.status()["reconcile"]["missing_active"] == ()


def test_server_health_fails_on_tenant_runtime_mismatch() -> None:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    health = state.is_healthy()
    assert health["overall"] is False
    assert health["checks"]["swarm_tenant_broker"]["reconcile"]["missing_active"] == ("task",)


def test_app_mounts_tenant_broker_routes() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/swarm/tenant-broker/status" in paths
    assert "/api/v1/swarm/tenant-broker/submit" in paths
    assert "/api/v1/swarm/tenant-broker/workers/{worker_id}/tasks/{task_id}/success" in paths
    assert "/api/v1/swarm/tenant-broker/workers/{worker_id}/tasks/{task_id}/failure" in paths
