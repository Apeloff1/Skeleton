"""Agent edge — mountable FastAPI gateway through auth -> backpressure -> pipeline."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.gate_plane.agent_edge import (  # noqa: E402
    GATE_ORDER,
    AgentAuthority,
    AgentBus,
    AgentEdge,
    AgentEndpoint,
    AgentGateway,
    AgentRegistry,
    AgentRouter,
    ScopeCeiling,
    build_agent_gateway_router,
    create_agent_gateway_app,
    default_edge_routes,
)
from skeleton.gate_plane.backpressure import BackpressureGate, PressureState, PressureView, StaticSource  # noqa: E402
from skeleton.gate_plane.backpressure.snapshot import iso_now  # noqa: E402
from skeleton.gate_plane.pipeline.breaker import BreakerConfig, BreakerRegistry  # noqa: E402
from skeleton.gate_plane.s2s.clock import ManualClock  # noqa: E402
from skeleton.gate_plane.s2s.keyring import KeyRing  # noqa: E402

FULL = ["msg:send:*", "msg:recv", "route:resolve", "agent:delegate", "dlq:read", "dlq:admin"]


class World:
    def __init__(self, pressure=PressureState.OPEN, retry_after_s=0.0):
        import time

        self.clock = ManualClock(start=time.time())
        ring = KeyRing(clock=self.clock)
        ring.add_key("k1", b"k" * 32, activate=True)
        self.authority = AgentAuthority(
            ring,
            clock=self.clock,
            ceiling=ScopeCeiling({"planner": FULL, "worker": ["msg:recv", "msg:send:work.*"], "helper": FULL}),
        )
        reg = AgentRegistry([AgentEndpoint.build("worker", "backend", ["work.item"]), AgentEndpoint.build("planner", "internal", ["plan.write"])])
        self.edge = AgentEdge(AgentBus(clock=self.clock), AgentRouter(reg, clock=self.clock), self.authority)
        self.state = {"pressure": pressure, "retry_after_s": retry_after_s}
        source = StaticSource(lambda tenant: self.view())
        self.gateway = AgentGateway(
            self.edge,
            backpressure=BackpressureGate(source, max_throttle_wait_s=0.0),
            breakers=BreakerRegistry(clock=self.clock),
            routes=default_edge_routes(breaker=BreakerConfig(consecutive_failures=2, min_calls=2, window_size=4)),
        )
        app = FastAPI()
        app.include_router(build_agent_gateway_router(self.gateway))
        self.client = TestClient(app)

    def view(self):
        return PressureView(
            schema_version=1, load=0.1 if self.state["pressure"] is PressureState.OPEN else 0.97,
            queue_depth=0, max_queue_depth=0, tenant_queue_depth=None,
            retry_after_s=self.state["retry_after_s"], state=self.state["pressure"],
            observed_at=iso_now(self.clock.now()), source="test",
        )

    def auth(self, agent, scopes=None):
        return {"authorization": f"Service {self.authority.issue(agent, scopes or self.authority.ceiling.of(agent))}"}


@pytest.fixture
def w():
    return World()


BASE = "/api/v1/agents"


def test_gate_order_declared():
    assert GATE_ORDER == ("auth", "backpressure", "pipeline")


def test_health_is_anonymous(w):
    r = w.client.get(f"{BASE}/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["x-gate-stage"] == "pipeline"


def test_missing_and_bad_tokens_rejected_at_auth(w):
    r = w.client.post(f"{BASE}/messages", json={"topic": "work.item", "recipient": "worker"})
    assert r.status_code == 401 and r.headers["x-gate-stage"] == "auth"
    assert "www-authenticate" in r.headers
    r = w.client.post(f"{BASE}/messages", json={"topic": "work.item", "recipient": "worker"}, headers={"authorization": "Service abc.def.ghi"})
    assert r.status_code == 401


def test_full_message_lifecycle_over_http(w):
    planner, worker = w.auth("planner"), w.auth("worker")
    r = w.client.post(f"{BASE}/messages", headers=planner, json={"topic": "work.item", "recipient": "worker", "payload": {"n": 1}, "conversation_id": "conv-0001"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "accepted" and body["sequence"] == 1 and body["recipient"] == "worker"
    dup = w.client.post(f"{BASE}/messages", headers=planner, json={"topic": "work.item", "recipient": "worker", "message_id": body["message_id"], "conversation_id": "conv-0001"})
    assert dup.status_code == 200 and dup.json()["status"] == "duplicate"

    r = w.client.post(f"{BASE}/mailbox/worker/pull", headers=worker, json={"max_messages": 5})
    deliveries = r.json()["deliveries"]
    assert r.status_code == 200 and len(deliveries) == 1
    d = deliveries[0]
    assert d["envelope"]["sender"] == "planner" and d["attempt"] == 1
    lease = d["lease_id"]
    assert w.client.post(f"{BASE}/leases/{lease}/extend", headers=worker, json={"lease_s": 60}).status_code == 200
    r = w.client.post(f"{BASE}/leases/{lease}/ack", headers=worker)
    assert r.status_code == 200 and r.json()["acked"] == body["message_id"]
    assert w.client.post(f"{BASE}/leases/{lease}/ack", headers=worker).status_code == 404


def test_scope_and_ownership_enforced_over_http(w):
    worker = w.auth("worker")
    r = w.client.post(f"{BASE}/messages", headers=worker, json={"topic": "plan.write", "recipient": "planner"})
    assert r.status_code == 403 and r.json()["reason"] == "missing_scope"
    r = w.client.post(f"{BASE}/mailbox/planner/pull", headers=worker, json={})
    assert r.status_code == 403 and r.json()["reason"] == "not_mailbox_owner"
    r = w.client.get(f"{BASE}/dlq", headers=worker)
    assert r.status_code == 403


def test_bad_bodies_are_400(w):
    planner = w.auth("planner")
    r = w.client.post(f"{BASE}/messages", headers={**planner, "content-type": "application/json"}, content=b"{not json")
    assert r.status_code == 400 and r.headers["x-gate-stage"] == "request"
    r = w.client.post(f"{BASE}/messages", headers=planner, json={"topic": "work.item"})
    assert r.status_code == 400
    r = w.client.post(f"{BASE}/mailbox/worker/pull", headers=w.auth("worker"), json={"topics": "x"})
    assert r.status_code == 400


def test_no_route_404_and_capability_resolve(w):
    planner = w.auth("planner")
    r = w.client.post(f"{BASE}/messages", headers=planner, json={"topic": "work.item", "recipient": "ghost"})
    assert r.status_code == 404 and r.json()["error"] == "no_route"
    r = w.client.get(f"{BASE}/routes/resolve", headers=planner, params={"capability": "work.item"})
    assert r.status_code == 200 and r.json()["agent_id"] == "worker"
    r = w.client.get(f"{BASE}/routes/resolve", headers=planner, params={"capability": "deploy.prod"})
    assert r.status_code == 404
    r = w.client.post(f"{BASE}/messages", headers=planner, json={"topic": "work.item", "capability": "work.item", "lane": "backend"})
    assert r.status_code == 202 and r.json()["route"]["outcome"] == "routed"


def test_backpressure_sheds_before_pipeline(w):
    planner = w.auth("planner")
    w.state.update(pressure=PressureState.SHED, retry_after_s=2.0)
    r = w.client.post(f"{BASE}/messages", headers=planner, json={"topic": "work.item", "recipient": "worker"})
    assert r.status_code == 429 and r.headers["x-gate-stage"] == "backpressure"
    assert r.headers["retry-after"] == "2"
    assert w.edge.bus.depth() == 0
    # auth still runs first: an unauthenticated caller gets 401, not 429
    r = w.client.post(f"{BASE}/messages", json={"topic": "work.item", "recipient": "worker"})
    assert r.status_code == 401
    w.state.update(pressure=PressureState.OPEN, retry_after_s=0.0)
    assert w.client.post(f"{BASE}/messages", headers=planner, json={"topic": "work.item", "recipient": "worker"}).status_code == 202


def test_route_unavailable_has_retry_after(w):
    planner = w.auth("planner")
    w.edge.router.record("worker", ok=False)
    for _ in range(5):
        w.edge.router.record("worker", ok=False)
    r = w.client.post(f"{BASE}/messages", headers=planner, json={"topic": "work.item", "recipient": "worker"})
    assert r.status_code == 503 and "retry-after" in r.headers


def test_pipeline_breaker_opens_on_server_errors(w):
    def boom(_p):
        raise RuntimeError("bus exploded")

    planner = {k: v for k, v in w.auth("planner").items()}
    for _ in range(2):
        with pytest.raises(RuntimeError):
            w.gateway.handle("POST", "messages", planner, boom)
    res = w.gateway.handle("POST", "messages", planner, lambda p: (200, {}))
    assert res.status == 503 and res.stage == "pipeline" and res.header("retry-after")


def test_delegation_endpoint_and_dlq_replay(w):
    planner, worker = w.auth("planner"), w.auth("worker")
    r = w.client.post(f"{BASE}/delegations", headers=planner, json={"delegate": "helper", "scopes": ["msg:send:work.*"]})
    assert r.status_code == 201
    helper = {"authorization": f"Service {r.json()['token']}"}
    r = w.client.post(f"{BASE}/messages", headers=helper, json={"topic": "work.item", "recipient": "worker", "max_attempts": 1})
    assert r.status_code == 202
    d = w.client.post(f"{BASE}/mailbox/worker/pull", headers=worker, json={}).json()["deliveries"][0]
    assert d["envelope"]["headers"]["on-behalf-of"] == "planner"
    r = w.client.post(f"{BASE}/leases/{d['lease_id']}/nack", headers=worker, json={"error": "nope", "retry": False})
    assert r.json()["dead_lettered"] is True
    r = w.client.get(f"{BASE}/dlq", headers=planner, params={"reason": "rejected"})
    assert [x["message_id"] for x in r.json()["dead_letters"]] == [d["envelope"]["message_id"]]
    r = w.client.post(f"{BASE}/dlq/{d['envelope']['message_id']}/replay", headers=planner)
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    r = w.client.post(f"{BASE}/delegations", headers=worker, json={"delegate": "helper", "scopes": ["msg:recv"]})
    assert r.status_code == 403
    r = w.client.post(f"{BASE}/delegations", headers=planner, json={"delegate": "helper"})
    assert r.status_code == 400


def test_stats_and_standalone_app_mount(w):
    planner = w.auth("planner")
    r = w.client.get(f"{BASE}/stats", headers=planner)
    assert r.status_code == 200 and r.json()["gateway"]["order"] == list(GATE_ORDER)
    host = FastAPI()
    host.mount("/edge", create_agent_gateway_app(w.gateway))
    c = TestClient(host)
    assert c.get("/edge/health").status_code == 200
    assert c.post("/edge/messages", json={"topic": "work.item", "recipient": "worker"}).status_code == 401
    assert c.post("/edge/messages", headers=planner, json={"topic": "work.item", "recipient": "worker"}).status_code == 202


def test_priority_header_cannot_claim_control(w):
    planner = w.auth("planner")
    w.state.update(pressure=PressureState.SHED, retry_after_s=1.0)
    r = w.client.post(f"{BASE}/messages", headers={**planner, "x-priority": "0"}, json={"topic": "work.item", "recipient": "worker"})
    assert r.status_code == 429


# Exact (stripped) server.py lines allowed to differ from origin/main. Full-line
# matches only: no substrings, so nothing else can ride along. Comments and blank
# lines are always allowed; lifespan/startup/shutdown tokens never are.
SERVER_PY_ALLOWED_LINES = frozenset({
    # #3622 follow-up: registered agent edge behind install_gate (restored after #4139).
    "from skeleton.api.agent_edge_mount import install_registered_agent_edge",
    "install_registered_agent_edge(app)",
    # skeleton.projects.v1 (#4097), restored after #4139.
    "from skeleton.api.projects_routes import router as projects_router",
    'app.include_router(projects_router, prefix="/api/v1")',
    # Cortex route guard wiring (Jenkins #4129 / #4256).
    "from skeleton.api.cortex_mount_guard import reject_cortex_secret_routes",
    "from skeleton.api.cortex_mount_guard import CortexRouteGuardMiddleware, reject_cortex_secret_routes",
    "app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)",
    # OmniFabric surface restored by Jenkins's #4266 (dropped by #4139).
    "def _omnifabric_api_enabled() -> bool:",
    '"""OmniFabric HTTP surface toggle (default on).',
    "``SKELETON_OMNIFABRIC_API`` set to ``0``/``false``/``no``/``off`` keeps the",
    "router unmounted. When mounted it sits behind the HMAC gate like every",
    "other ``/api/v1`` route; it is never added to the open prefixes.",
    '"""',
    'return os.environ.get("SKELETON_OMNIFABRIC_API", "1").strip().lower() not in {',
    '"0", "false", "no", "off",',
    "}",
    "if _omnifabric_api_enabled():",
    "from skeleton.api.omnifabric_routes import router as omnifabric_router",
    'app.include_router(omnifabric_router, prefix="/api/v1")',
    # Realtime hub limits moved to skeleton/realtime/limits.py by Walt's #4253.
    "from skeleton.realtime import RealtimeHub, realtime_limits_from_env, sealed_principal_authorizer",
    "realtime_hub = RealtimeHub(authorizer=sealed_principal_authorizer, **realtime_limits_from_env())",
    # Original lines #4253 replaces (removed side of its server.py diff).
    "from skeleton.realtime import RealtimeHub, sealed_principal_authorizer",
    "realtime_hub = RealtimeHub(authorizer=sealed_principal_authorizer)",
})
_SERVER_PY_FORBIDDEN_TOKENS = ("on_event", "lifespan", "startup", "shutdown")


def disallowed_server_py_lines(diff_text: str) -> list[str]:
    """Changed server.py lines (from a ``git diff -U0``) outside the exact allowlist."""
    bad = []
    for raw in diff_text.splitlines():
        if raw[:1] not in "+-" or raw.startswith(("+++", "---")):
            continue
        text = raw[1:].strip()
        if any(t in text for t in _SERVER_PY_FORBIDDEN_TOKENS):
            bad.append(raw)
        elif text and not text.startswith("#") and text not in SERVER_PY_ALLOWED_LINES:
            bad.append(raw)
    return bad


def test_server_py_not_modified():
    """Pack F never touches the server lifespan.

    The #3622 follow-up (TD: create_app is the only HTTP entry) adds one
    extend-only agent-edge hook inside create_app; every other server.py
    change, and anything touching startup/shutdown/lifespan, still fails.
    """
    import subprocess

    out = subprocess.run(["git", "diff", "-U0", "origin/main", "--", "skeleton/api/server.py"], capture_output=True, text=True)
    assert disallowed_server_py_lines(out.stdout) == []


@pytest.mark.parametrize("line", [
    "+    app.include_router(cortex_router)",
    '+    app.include_router(cortex_router, prefix="/api/v1")',
    "+    from skeleton.api.cortex_routes import router as cortex_router",
    '+    app.mount("/", StaticFiles(directory="."))',
    '+    app.mount("/", StaticFiles(directory="static"), name="root")',
    "+    )",
    "+    install_registered_agent_edge(app); app.include_router(cortex_router)",
    "+    # lifespan tweak",
    "-    install_gate(app, policy=gate_policy)",
])
def test_server_py_check_rejects_unlisted_changes(line):
    diff = "--- a/skeleton/api/server.py\n+++ b/skeleton/api/server.py\n@@ -1,0 +1 @@\n" + line + "\n"
    assert disallowed_server_py_lines(diff) == [line]


def test_server_py_check_accepts_exact_allowlisted_lines():
    diff = "\n".join("+    " + line for line in sorted(SERVER_PY_ALLOWED_LINES)) + "\n+\n+    # comment\n"
    assert disallowed_server_py_lines(diff) == []


def test_server_composes_agent_edge_behind_shared_gate():
    """The assembled server owns HTTP composition and gates the optional edge."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "skeleton/api/server.py").read_text())
    factory = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "create_app")
    calls = [
        statement.value.func.id
        for statement in factory.body
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
    ]
    assert calls.count("install_registered_agent_edge") == 1
    assert calls.index("install_gate") < calls.index("install_registered_agent_edge")
    assert "create_agent_gateway_app" not in calls
