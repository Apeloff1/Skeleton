from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.api.server import ServerState, create_app


def test_server_state_reports_ingress_status() -> None:
    state = ServerState()
    state.swarm_ingress = SwarmIngressGovernor()
    state.swarm_ingress.admit("tenant", "task", {})
    health = state.is_healthy()
    assert health["overall"] is True
    assert health["checks"]["swarm_ingress"]["accounted_tasks"] == 1


def test_app_mounts_ingress_routes() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/swarm/ingress/status" in paths
    assert "/api/v1/swarm/ingress/tenants/{tenant}" in paths
    assert "/api/v1/swarm/ingress/admit" in paths
    assert "/api/v1/swarm/ingress/lease" in paths
    assert "/api/v1/swarm/ingress/complete" in paths
