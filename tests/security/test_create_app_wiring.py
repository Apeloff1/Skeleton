"""Wiring tripwire: create_app must keep mounting projects_router and the registered agent edge.

Both were silently dropped by the stale-base merge of #4139.
"""
import pytest

from skeleton.api.cortex_mount_guard import CortexRouteGuardMiddleware, iter_route_paths


def test_create_app_mounts_projects_router():
    from skeleton.api.projects_routes import router as projects_router
    from skeleton.api.server import create_app

    paths = set(iter_route_paths(create_app()))
    expected = {"/api/v1" + r.path for r in projects_router.routes}
    assert expected and expected <= paths, sorted(expected - paths)


def test_create_app_mounts_registered_agent_edge():
    from skeleton.api import agent_edge_mount as mount
    from skeleton.api.server import create_app
    from skeleton.testing.test_gate_plane_pack_f_agent_edge_gateway import World

    mount.clear_registered_agent_gateway()
    mount.register_agent_gateway(World().gateway)
    try:
        app = create_app()
    finally:
        mount.clear_registered_agent_gateway()
    assert any(p.startswith("/api/v1/agents/") for p in iter_route_paths(app))
    assert app.state.agent_gateway is not None
    assert app.state.gate_policy.required_domain("/api/v1/agents/messages") == mount.AGENT_EDGE_DOMAIN


def test_create_app_without_registered_edge_has_no_agent_routes():
    from skeleton.api import agent_edge_mount as mount
    from skeleton.api.server import create_app

    mount.clear_registered_agent_gateway()
    assert not any(p.startswith("/api/v1/agents/") for p in iter_route_paths(create_app()))


@pytest.mark.parametrize("module", ["skeleton.api.server", "skeleton.ai.runtime.api.server"])
def test_both_server_mirrors_keep_the_wiring(module):
    import importlib
    import inspect

    src = inspect.getsource(importlib.import_module(module).create_app)
    for needle in ("include_router(projects_router", "install_registered_agent_edge(app)",
                   "CortexRouteGuardMiddleware", "reject_cortex_secret_routes(app)"):
        assert needle in src, (module, needle)
    assert CortexRouteGuardMiddleware
