from skeleton.api.server import create_app


def test_hardened_swarm_routes_are_mounted() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/swarm/integrity/audit" in paths
    assert "/api/v1/swarm/integrity/assert" in paths
    assert "/api/v1/swarm/fenced/workers/{worker_id}/tasks/{task_id}/success" in paths
    assert "/api/v1/swarm/fenced/workers/{worker_id}/tasks/{task_id}/failure" in paths
    assert "/api/v1/swarm/fenced/workers/{worker_id}/tasks/{task_id}/renew" in paths
