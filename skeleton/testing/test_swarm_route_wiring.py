from skeleton.api.server import create_app


def test_swarm_control_planes_are_mounted() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/swarm/status" in paths
    assert "/api/v1/swarm/operator/overview" in paths
    assert "/api/v1/swarm/policy/admission-preview" in paths
    assert "/api/v1/swarm/lifecycle/pressure" in paths
    assert "/api/v1/swarm/operator/gc" in paths
    assert "/api/v1/swarm/operator/checkpoint" in paths
    assert "/api/v1/swarm/operator/failover/elect" in paths
