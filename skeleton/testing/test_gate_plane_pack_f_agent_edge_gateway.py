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


def test_server_py_not_modified():
    import subprocess

    out = subprocess.run(["git", "diff", "--name-only", "origin/main", "--", "skeleton/api/server.py"], capture_output=True, text=True)
    assert out.stdout.strip() == ""
