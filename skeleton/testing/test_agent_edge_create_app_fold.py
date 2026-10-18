"""#3622 follow-up: the agent-edge gateway folds into create_app behind install_gate.

TD ruling: create_app is the only HTTP entry. The edge routes must be
reachable through the app create_app builds, every request must clear the
main gate stack (RequestSeal / Auth / PolicyGate) before the edge's own
S2S token check, and the old standalone factory must still work and warn.
"""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.api import agent_edge_mount as mount  # noqa: E402
from skeleton.api.hmac_seal import mint_seal  # noqa: E402
from skeleton.api.middleware import GatePolicy, install_gate  # noqa: E402
from skeleton.gate_plane.agent_edge import create_agent_gateway_app  # noqa: E402
from skeleton.testing.test_gate_plane_pack_f_agent_edge_gateway import World  # noqa: E402

BASE = "/api/v1/agents"
SECRET = "agent-edge-fold-test-secret-0123456789abcdef"
MSG = {"topic": "work.item", "recipient": "worker"}


@pytest.fixture
def sealed_env(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    return {"x-gf-seal": mint_seal("planner-host", secret=SECRET)}


@pytest.fixture
def registered():
    w = World()
    mount.register_agent_gateway(w.gateway)
    try:
        yield w
    finally:
        mount.clear_registered_agent_gateway()


def _ready(app):
    app.state.runtime_lifecycle.mark_ready(reason="agent-edge-fold-test")
    return TestClient(app)


def _paths(app):
    return {getattr(r, "path", "") for r in app.routes}


# -- create_app wiring -----------------------------------------------------------------


def test_create_app_without_registration_adds_no_edge_routes():
    from skeleton.api.server import create_app

    mount.clear_registered_agent_gateway()
    app = create_app()
    assert not any(p.startswith(BASE) for p in _paths(app))
    assert getattr(app.state, "agent_gateway", None) is None
    assert isinstance(app.state.gate_policy, GatePolicy)
    assert app.state.gate_policy.required_domain(f"{BASE}/health") is None


def test_registered_gateway_is_reachable_through_create_app(registered, sealed_env):
    from skeleton.api.server import create_app

    app = create_app()
    assert app.state.agent_gateway is registered.gateway
    assert f"{BASE}/messages" in _paths(app)
    assert app.state.gate_policy.required_domain(f"{BASE}/messages") == mount.AGENT_EDGE_DOMAIN
    client = _ready(app)

    r = client.get(f"{BASE}/health", headers=sealed_env)
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["x-gate-stage"] == "pipeline"
    assert r.headers.get("x-request-id")  # RequestSeal threaded the request

    r = client.post(f"{BASE}/messages", headers={**sealed_env, **registered.auth("planner")}, json=MSG)
    assert r.status_code == 202, r.text


def test_install_agent_edge_after_create_app_is_still_gated(sealed_env):
    from skeleton.api.server import create_app

    mount.clear_registered_agent_gateway()
    w = World()
    app = mount.install_agent_edge(create_app(), w.gateway)
    client = _ready(app)
    assert client.get(f"{BASE}/health").status_code == 401
    assert client.get(f"{BASE}/health", headers=sealed_env).status_code == 200


# -- the gate rejects before the edge ---------------------------------------------------


def test_unsealed_requests_rejected_by_gate_even_with_agent_token(registered, sealed_env):
    from skeleton.api.server import create_app

    client = _ready(create_app())
    planner = registered.auth("planner")
    # No seal: RequestSeal rejects before the edge ever sees the agent token.
    r = client.post(f"{BASE}/messages", headers=planner, json=MSG)
    assert r.status_code == 401 and r.json() == {"error": "invalid_seal"}
    assert "x-gate-stage" not in r.headers
    # Health is anonymous inside the edge, but not open at the main gate.
    r = client.get(f"{BASE}/health")
    assert r.status_code == 401 and "x-gate-stage" not in r.headers
    # Forged seal.
    r = client.get(f"{BASE}/stats", headers={**planner, "x-gf-seal": "planner-host.9999999999.deadbeef"})
    assert r.status_code == 401 and r.json() == {"error": "invalid_seal"}
    assert registered.gateway.counts == {}


def test_sealed_but_unauthenticated_agent_rejected_by_edge_auth(registered, sealed_env):
    from skeleton.api.server import create_app

    client = _ready(create_app())
    r = client.post(f"{BASE}/messages", headers=sealed_env, json=MSG)
    assert r.status_code == 401 and r.headers["x-gate-stage"] == "auth"
    r = client.post(f"{BASE}/messages", headers={**sealed_env, "authorization": "Service abc.def.ghi"}, json=MSG)
    assert r.status_code == 401 and r.headers["x-gate-stage"] == "auth"


def test_seal_secret_unset_fails_closed(registered, monkeypatch):
    from skeleton.api.server import create_app

    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    client = _ready(create_app())
    r = client.post(f"{BASE}/messages", headers=registered.auth("planner"), json=MSG)
    assert r.status_code == 503 and r.json() == {"error": "seal_unavailable"}


# -- install_agent_edge refuses unsafe mounts ------------------------------------------


def test_install_agent_edge_refuses_ungated_app():
    with pytest.raises(mount.AgentEdgeMountError, match="install_gate"):
        mount.install_agent_edge(FastAPI(), World().gateway)


def test_install_agent_edge_refuses_open_root_and_double_install():
    app = install_gate(FastAPI(), policy=GatePolicy())
    w = World()
    with pytest.raises(mount.AgentEdgeMountError):
        mount.install_agent_edge(app, w.gateway, prefix="/")
    with pytest.raises(mount.AgentEdgeMountError, match="open"):
        mount.install_agent_edge(app, w.gateway, prefix="/health")
    with pytest.raises(mount.AgentEdgeMountError, match="already chartered"):
        mount.install_agent_edge(app, w.gateway, prefix="/api/v1/swarm")
    mount.install_agent_edge(app, w.gateway)
    with pytest.raises(mount.AgentEdgeMountError, match="already installed"):
        mount.install_agent_edge(app, w.gateway)
    with pytest.raises(TypeError):
        mount.install_agent_edge(app, object())  # type: ignore[arg-type]


def test_register_domain_is_extend_only():
    policy = GatePolicy()
    before = policy.required_domain("/api/v1/swarm/status")
    policy.register_domain("/api/v1/agents", "agents")
    policy.register_domain("/api/v1/agents/", "agents")  # idempotent
    assert policy.required_domain("/api/v1/agents/messages") == "agents"
    assert policy.required_domain("/api/v1/agentsx") is None
    assert policy.required_domain("/api/v1/swarm/status") == before
    with pytest.raises(ValueError):
        policy.register_domain("/api/v1/agents", "swarm")
    with pytest.raises(ValueError):
        policy.register_domain("/", "agents")
    with pytest.raises(ValueError):
        policy.register_domain("relative", "agents")


# -- deprecated factory -----------------------------------------------------------------


def test_deprecated_factory_still_works_and_warns():
    w = World()
    with pytest.warns(DeprecationWarning, match="create_app is the only HTTP entry"):
        sub = create_agent_gateway_app(w.gateway)
    host = FastAPI()
    host.mount("/edge", sub)
    c = TestClient(host)
    assert c.get("/edge/health").status_code == 200
    assert c.post("/edge/messages", json=MSG).status_code == 401
    assert c.post("/edge/messages", headers=w.auth("planner"), json=MSG).status_code == 202


def test_deprecated_factory_routes_auth_through_install_gate(sealed_env):
    w = World()
    with pytest.warns(DeprecationWarning):
        sub = create_agent_gateway_app(w.gateway, gate_installer=mount.gate_standalone_agent_edge)
    assert isinstance(sub.state.gate_policy, GatePolicy)
    host = FastAPI()
    host.mount("/edge", sub)
    c = TestClient(host)
    planner = w.auth("planner")
    assert c.get("/edge/health").status_code == 401
    assert c.post("/edge/messages", headers=planner, json=MSG).status_code == 401
    assert c.get("/edge/health", headers=sealed_env).status_code == 200
    assert c.post("/edge/messages", headers={**sealed_env, **planner}, json=MSG).status_code == 202


def test_gated_standalone_helper_does_not_leak_warning(sealed_env):
    w = World()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        app = mount.create_gated_agent_gateway_app(w.gateway)
    c = TestClient(app)
    assert c.get("/health").status_code == 401
    assert c.get("/health", headers=sealed_env).status_code == 200
