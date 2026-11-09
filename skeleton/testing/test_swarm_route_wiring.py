from skeleton.api.server import create_app


def test_swarm_control_planes_are_mounted() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert "/api/v1/swarm/status" in paths
    assert "/api/v1/swarm/operator/overview" in paths
    assert "/api/v1/swarm/policy/admission-preview" in paths
    assert "/api/v1/swarm/lifecycle/pressure" in paths
    assert "/api/v1/swarm/operator/gc" in paths
    assert "/api/v1/swarm/operator/checkpoint" in paths
    assert "/api/v1/swarm/operator/failover/elect" in paths


def test_gameforge_and_commands_have_one_mounted_owner():
    import warnings

    from skeleton.api.server import create_app

    with warnings.catch_warnings():
        warnings.filterwarnings("error", message="Duplicate Operation ID")
        schema = create_app().openapi()
    paths = schema["paths"]
    assert "post" in paths["/api/v1/gameforge/run"]
    assert "post" in paths["/api/v1/gameforge/intake"]
    assert "get" in paths["/api/v1/commands/contracts"]
    assert "post" in paths["/api/v1/commands/execute/{command}"]
