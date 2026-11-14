"""Edge decision order and the ASGI middleware, with real s2s tokens (TEST-ONLY keys)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from skeleton.gate_plane.s2s.audit import InMemoryAuditSink
from skeleton.gate_plane.s2s.authz import Principal
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.gate import S2SAuthGate, install_s2s_gate
from skeleton.gate_plane.s2s.mint_cli import build_test_keyring
from skeleton.gate_plane.s2s.tokens import TokenSigner, TokenVerifier
from skeleton.gate_plane.systems.catalog import SystemCatalog, SystemLimits, SystemProfile, default_catalog
from skeleton.gate_plane.systems.edge import (
    EdgeOutcome,
    EdgeRequest,
    RecoveredSystemsEdge,
    install_recovered_systems_edge,
)
from skeleton.gate_plane.systems.policies import merge_into
from skeleton.gate_plane.systems.readiness import ProbeResult, ReadinessRegistry
from skeleton.gate_plane.s2s.authz import default_gate_plane_policies


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture
def ring(clock):
    return build_test_keyring(["test-k1"], clock=clock)


@pytest.fixture
def mint(ring, clock):
    def _mint(service, *scopes, aud="gate"):
        return TokenSigner(service, ring, clock=clock).mint(aud, scopes)
    return _mint


def ready_all(clock, catalog=None, *, down=()):
    reg = ReadinessRegistry(clock=clock)
    for name in (catalog or default_catalog()).names():
        reg.register(name, (lambda n=name: ProbeResult.failed("down") if n in down else ProbeResult.passed()))
    return reg


def H(**kv):
    return [(k.replace("_", "-").encode(), str(v).encode()) for k, v in kv.items()]


def P(service, *scopes, overlap=False):
    return Principal(service=service, scopes=frozenset(scopes), kid="test-k1", in_overlap=overlap)


@pytest.fixture
def edge(clock):
    return RecoveredSystemsEdge(readiness=ready_all(clock), clock=clock)


def ev(edge, method, path, principal=None, headers=()):
    return edge.evaluate(EdgeRequest(method, path, list(headers), principal))


def test_pass_through_outside_systems(edge):
    d = ev(edge, "GET", "/api/v1/forge/x")
    assert d.outcome is EdgeOutcome.PASS_THROUGH and d.allowed


def test_decision_order(edge):
    assert ev(edge, "GET", "/api/jeeves/a").outcome is EdgeOutcome.UNAUTHENTICATED
    assert ev(edge, "GET", "/api/jeeves/health").outcome is EdgeOutcome.ALLOW
    assert ev(edge, "POST", "/api/jeeves/health").outcome is EdgeOutcome.UNAUTHENTICATED
    d = ev(edge, "POST", "/api/jeeves/a", P("svc", "jeeves:read"))
    assert d.outcome is EdgeOutcome.FORBIDDEN and d.missing_scopes == ("jeeves:write",)
    assert ev(edge, "POST", "/api/jeeves/a", P("svc", "jeeves:write")).outcome is EdgeOutcome.ALLOW
    assert ev(edge, "POST", "/api/jeeves-master/x", P("svc", "jeeves:write")).reason == "missing_scope"
    assert ev(edge, "POST", "/api/jeeves-master/x", P("svc", "jeeves:admin", overlap=True)).reason == "overlap_key_forbidden"
    assert ev(edge, "POST", "/api/jeeves-master/x", P("svc", "jeeves:admin")).allowed


def test_framing_and_size(edge):
    p = P("svc", "gameforge:write")
    assert ev(edge, "POST", "/api/gameforge/map", p, H(content_length=1, **{"Content-Length": 2})).reason == "conflicting_content_length"
    assert ev(edge, "POST", "/api/gameforge/map", p, H(content_length="x")).reason == "invalid_content_length"
    assert (
        ev(edge, "POST", "/api/gameforge/map", p, H(content_length=3, transfer_encoding="chunked")).reason
        == "content_length_with_transfer_encoding"
    )
    big = 8 * 1024 * 1024 + 1
    assert ev(edge, "POST", "/api/gameforge/map", p, H(content_length=big)).outcome is EdgeOutcome.PAYLOAD_TOO_LARGE


def test_allow_and_deny_lists(clock):
    prof = SystemProfile.build("svcsys", "S", ["/api/s/**"], allow_services=["good"], deny_services=["evil"])
    cat = SystemCatalog([prof])
    e = RecoveredSystemsEdge(cat, readiness=ready_all(clock, cat), clock=clock)
    assert ev(e, "GET", "/api/s/x", P("good", "svcsys:read")).allowed
    assert ev(e, "GET", "/api/s/x", P("other", "svcsys:read")).reason == "service_not_allowed"
    prof2 = SystemProfile.build("svcsys", "S", ["/api/s/**"], deny_services=["evil"])
    e2 = RecoveredSystemsEdge(SystemCatalog([prof2]), readiness=ready_all(clock, SystemCatalog([prof2])), clock=clock)
    assert ev(e2, "GET", "/api/s/x", P("evil", "svcsys:read")).reason == "service_denied"


def test_not_ready_fails_closed(clock):
    e = RecoveredSystemsEdge(readiness=ready_all(clock, down=("local_ai",)), clock=clock)
    d = ev(e, "POST", "/api/v1/local-ai/chat", P("svc", "local_ai:infer"))
    assert d.outcome is EdgeOutcome.NOT_READY and d.http_status == 503 and d.reason == "not_ready:down"
    e2 = RecoveredSystemsEdge(clock=clock)  # no probes registered at all
    assert ev(e2, "GET", "/api/v1/hive/verify", P("svc", "hive:read")).reason == "not_ready:no_probe_registered"


def test_requires_ready_false_skips_probe(clock):
    prof = SystemProfile.build("opt", "O", ["/api/o/**"], requires_ready=False)
    e = RecoveredSystemsEdge(SystemCatalog([prof]), clock=clock)
    assert ev(e, "GET", "/api/o/x", P("svc", "opt:read")).allowed


def test_bulkhead_and_release(clock):
    prof = SystemProfile.build("tiny", "T", ["/api/t/**"], limits=SystemLimits(max_concurrency=1))
    cat = SystemCatalog([prof])
    e = RecoveredSystemsEdge(cat, readiness=ready_all(clock, cat), clock=clock)
    first = ev(e, "GET", "/api/t/x", P("svc", "tiny:read"))
    second = ev(e, "GET", "/api/t/x", P("svc", "tiny:read"))
    assert first.allowed and second.outcome is EdgeOutcome.BUSY and ("retry-after", "1") in second.headers
    e.release(first)
    assert ev(e, "GET", "/api/t/x", P("svc", "tiny:read")).allowed


def test_deadline_propagation(edge):
    p = P("svc", "hive:read")
    assert ev(edge, "GET", "/api/v1/hive/verify", p).deadline_ms == 5000
    assert ev(edge, "GET", "/api/v1/hive/verify", p, H(x_skeleton_deadline_ms=1200)).deadline_ms == 1200
    assert ev(edge, "GET", "/api/v1/hive/verify", p, H(x_skeleton_deadline_ms=99999)).deadline_ms == 5000
    assert ev(edge, "GET", "/api/v1/hive/verify", p, H(x_skeleton_deadline_ms="junk")).deadline_ms == 5000


def test_body_never_leaks_principal(edge):
    d = ev(edge, "POST", "/api/jeeves/a", P("secret-svc", "jeeves:read"))
    body = d.body()
    assert "service" not in body and "secret-svc" not in str(body)


def test_audit_hook_errors_never_change_verdict(clock):
    sink = InMemoryAuditSink()
    e = RecoveredSystemsEdge(readiness=ready_all(clock), clock=clock, audit=[lambda ev_: 1 / 0, sink.emit])
    assert ev(e, "GET", "/api/jeeves/a").outcome is EdgeOutcome.UNAUTHENTICATED
    ev(e, "GET", "/api/v1/forge/x")  # pass-through is not audited
    events = sink.events(kind="systems_edge")
    assert len(events) == 1 and events[0].action == "deny" and events[0].http_status == 401


def test_own_verifier(clock, ring, mint):
    e = RecoveredSystemsEdge(readiness=ready_all(clock), clock=clock, verifier=TokenVerifier("gate", ring, clock=clock))
    tok = mint("jeeves-worker", "jeeves:read")
    assert ev(e, "GET", "/api/jeeves/a", headers=H(authorization=f"Service {tok}")).service == "jeeves-worker"
    assert ev(e, "GET", "/api/jeeves/a", headers=H(authorization="Service a.b.c")).outcome is EdgeOutcome.UNAUTHENTICATED
    dup = [(b"x-service-token", tok.encode()), (b"x-service-token", b"other")]
    assert ev(e, "GET", "/api/jeeves/a", headers=dup).reason == "conflicting_credentials"
    wrong_aud = mint("jeeves-worker", "jeeves:read", aud="elsewhere")
    assert ev(e, "GET", "/api/jeeves/a", headers=H(x_service_token=wrong_aud)).reason == "bad_audience"


def _app(edge, ring, clock):
    app = FastAPI()

    @app.api_route("/api/jeeves/{rest:path}", methods=["GET", "POST"])
    async def jeeves(rest: str, request: Request):
        body = await request.body()
        resp = {
            "caller": request.headers.get("x-skeleton-caller"),
            "system": request.headers.get("x-skeleton-system"),
            "principal_hdr": request.headers.get("x-principal"),
            "deadline": request.headers.get("x-skeleton-deadline-ms"),
            "n": len(body),
        }
        from fastapi.responses import JSONResponse

        return JSONResponse(resp, headers={"x-skeleton-caller": "leak", "x-scopes": "leak", "etag": "e1"})

    @app.get("/api/v1/forge/{x}")
    def forge(x: str):
        return {"forge": x}

    install_recovered_systems_edge(app, edge)
    verifier = TokenVerifier("gate", ring, clock=clock)
    install_s2s_gate(app, S2SAuthGate(verifier, merge_into(default_gate_plane_policies()), admission=False))
    return app


def test_asgi_stack_with_s2s(clock, ring, mint, edge):
    client = TestClient(_app(edge, ring, clock))
    tok = mint("jeeves-worker", "jeeves:read", "jeeves:write")
    r = client.post("/api/jeeves/run", content=b"abc", headers={"authorization": f"Service {tok}", "x-principal": "root"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j == {"caller": "jeeves-worker", "system": "jeeves", "principal_hdr": None, "deadline": "60000", "n": 3}
    assert "x-skeleton-caller" not in r.headers and "x-scopes" not in r.headers and r.headers["etag"] == "e1"
    assert edge.bulkheads.get("jeeves").in_flight == 0
    assert client.get("/api/jeeves/run").status_code == 401
    assert client.get("/api/v1/forge/1", headers={"authorization": f"Service {mint('f', 'forge:read')}"}).json() == {"forge": "1"}


def test_asgi_streamed_body_over_limit(clock, ring, mint):
    prof = SystemProfile.build("jeeves", "J", ["/api/jeeves/**"], limits=SystemLimits(max_body_bytes=8))
    cat = SystemCatalog([prof])
    e = RecoveredSystemsEdge(cat, readiness=ready_all(clock, cat), clock=clock, verifier=TokenVerifier("gate", ring, clock=clock))
    app = FastAPI()

    @app.post("/api/jeeves/{x}")
    async def j(x: str, request: Request):
        return {"n": len(await request.body())}

    install_recovered_systems_edge(app, e)
    client = TestClient(app)
    tok = mint("w", "jeeves:write")

    def gen():
        yield b"12345"
        yield b"67890"

    r = client.post("/api/jeeves/a", content=gen(), headers={"authorization": f"Service {tok}"})
    assert r.status_code == 413 and r.json()["reason"] == "body_over_limit"
    assert e.bulkheads.get("jeeves").in_flight == 0
    ok = client.post("/api/jeeves/a", content=b"1234", headers={"authorization": f"Service {tok}"})
    assert ok.json() == {"n": 4}


def test_describe(edge):
    d = edge.describe()
    assert d["catalog_digest"] == default_catalog().digest()
    assert set(d["bulkheads"]) == {"gameforge", "hive", "jeeves", "local_ai"}
