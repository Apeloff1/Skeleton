"""Pack F hardening — HardenedS2SGate decisions and ASGI middleware end to end."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json

import pytest

from skeleton.gate_plane.admit import AdmissionMatrix
from skeleton.gate_plane.hardening import (
    HARDENED_GATE_LAYER,
    ClaimsPolicy,
    HardenedOutcome,
    HardenedS2SMiddleware,
    MutualAuthPolicy,
    PeerExtractor,
    RateRule,
    RequestSigner,
    RequestVerifier,
    ServiceRateLimiter,
    SignatureMode,
    SpiffeMap,
    bound_extra,
    build_hardened_gate,
    current_context,
    install_hardened_gate,
    propagate,
)
from skeleton.gate_plane.hardening.request_id import HOP_HEADER, REQUEST_ID_HEADER, VIA_HEADER
from skeleton.gate_plane.s2s.authz import default_gate_plane_policies
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.gate import PRINCIPAL_SCOPE_KEY, S2SAuthGate
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import ReplayCache, TokenSigner, TokenVerifier
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor

DER = b"\x30\x82forge-client-cert"
THUMB = hashlib.sha256(DER).hexdigest()
PEM = "-----BEGIN CERTIFICATE-----\n" + base64.b64encode(DER).decode() + "\n-----END CERTIFICATE-----\n"
SWARM = "/api/v1/swarm/jobs"


class Env:
    def __init__(self, *, capacity=100, claims=None, **gate_kw):
        self.clock = ManualClock()
        self.ring = KeyRing(clock=self.clock)
        self.ring.add_key("forge:1", b"F" * 32, activate=True)
        self.verifier = TokenVerifier("gateway", self.ring, clock=self.clock, replay_cache=ReplayCache())
        self.adaptive = AdaptiveGate(capacity, 0)
        self.matrix = AdmissionMatrix(gate=self.adaptive, governor=ChaosGovernor(min_samples=1000))
        self.decisions = []
        self.gate = build_hardened_gate(
            self.verifier, default_gate_plane_policies(), claims=claims, matrix=self.matrix, service="gateway",
            hooks=[lambda m, p, d: self.decisions.append(d)], **gate_kw,
        )

    def token(self, *scopes, service="forge", **kw):
        return TokenSigner(service, self.ring, clock=self.clock).mint("gateway", scopes, **kw)

    def headers(self, *scopes, **kw):
        return {"Authorization": f"Service {self.token(*scopes, **kw)}"}


def test_builder_requires_admission_free_base():
    env = Env()
    with pytest.raises(ValueError):
        type(env.gate)(S2SAuthGate(env.verifier, default_gate_plane_policies(), admission=True))


def test_signature_mode_requires_verifier():
    env = Env()
    with pytest.raises(ValueError):
        type(env.gate)(env.gate.base, signature_mode="required")


def test_allow_carries_context_and_principal():
    env = Env()
    d = env.gate.evaluate("GET", SWARM, {**env.headers("swarm:read"), REQUEST_ID_HEADER: "req-gatetest00001"})
    assert d.allowed and d.outcome is HardenedOutcome.ALLOW and d.http_status == 200
    assert d.principal.service == "forge" and d.policy == "swarm-read"
    assert d.context.request_id == "req-gatetest00001" and d.admission == "admit"
    assert ("x-request-id", "req-gatetest00001") in d.response_headers()
    assert env.decisions[-1] is d


def test_open_probe_bypass_still_gets_context():
    env = Env()
    d = env.gate.evaluate("GET", "/health", {})
    assert d.outcome is HardenedOutcome.OPEN_BYPASS and d.context.request_id


def test_loop_detected():
    env = Env()
    d = env.gate.evaluate("GET", SWARM, {HOP_HEADER: "40"})
    assert d.outcome is HardenedOutcome.LOOP_DETECTED and d.http_status == 508
    d2 = env.gate.evaluate("GET", SWARM, {VIA_HEADER: "forge,gateway"})
    assert d2.outcome is HardenedOutcome.LOOP_DETECTED


def test_base_failures_passthrough():
    env = Env()
    assert env.gate.evaluate("GET", SWARM, {}).outcome is HardenedOutcome.UNAUTHENTICATED
    d = env.gate.evaluate("POST", SWARM, env.headers("swarm:read"))
    assert d.outcome is HardenedOutcome.FORBIDDEN and d.body()["missing_scopes"]


def test_hardening_failure_reason_surfaces():
    env = Env(claims=ClaimsPolicy.build(scope_ceilings={"forge": ["swarm:read"]}))
    d = env.gate.evaluate("GET", SWARM, env.headers("swarm:read", "admin:control"))
    assert d.outcome is HardenedOutcome.UNAUTHENTICATED and d.reason == "scope_ceiling"
    assert "admin:control" not in json.dumps(d.body())


def test_mutual_required_without_peer():
    env = Env(mutual=MutualAuthPolicy.build("required"), extractor=PeerExtractor())
    d = env.gate.evaluate("GET", SWARM, env.headers("swarm:read"))
    assert d.outcome is HardenedOutcome.MUTUAL_AUTH_FAILED and d.reason == "mtls_no_peer" and d.http_status == 401


def test_mutual_tls_with_bound_token_allows():
    env = Env(
        claims=ClaimsPolicy.build(require_binding=True),
        mutual=MutualAuthPolicy.build("required", pinned_thumbprints={"forge": [THUMB]}),
        extractor=PeerExtractor(),
    )
    scope = {"extensions": {"tls": {"client_cert_chain": [PEM]}}}
    hdrs = env.headers("swarm:read", extra=bound_extra(thumbprint=THUMB))
    d = env.gate.evaluate("GET", SWARM, hdrs, scope=scope)
    assert d.allowed and d.peer.peer.thumbprint == THUMB


def test_stolen_bound_token_from_other_peer_rejected():
    env = Env(claims=ClaimsPolicy.build(require_binding=True), extractor=PeerExtractor())
    other_pem = "-----BEGIN CERTIFICATE-----\n" + base64.b64encode(b"attacker").decode() + "\n-----END CERTIFICATE-----\n"
    hdrs = env.headers("swarm:read", extra=bound_extra(thumbprint=THUMB))
    d = env.gate.evaluate("GET", SWARM, hdrs, scope={"extensions": {"tls": {"client_cert_chain": [other_pem]}}})
    assert d.outcome is HardenedOutcome.UNAUTHENTICATED and d.reason == "binding_mismatch"


def test_xfcc_spiffe_identity_mismatch():
    env = Env(
        mutual=MutualAuthPolicy.build("required"),
        extractor=PeerExtractor(trusted_proxies=["10.0.0.0/8"], spiffe=SpiffeMap("prod")),
    )
    hdrs = {**env.headers("swarm:read"), "x-forwarded-client-cert": f"Hash={THUMB};URI=spiffe://prod/svc/telemetry"}
    d = env.gate.evaluate("GET", SWARM, hdrs, scope={"client": ("10.0.0.5", 1234)})
    assert d.outcome is HardenedOutcome.MUTUAL_AUTH_FAILED and d.reason == "mtls_peer_mismatch"
    hdrs = {**env.headers("swarm:read"), "x-forwarded-client-cert": f"Hash={THUMB};URI=spiffe://prod/svc/forge"}
    assert env.gate.evaluate("GET", SWARM, hdrs, scope={"client": ("10.0.0.5", 1234)}).allowed


def test_signed_requests_required():
    env = _with_verifier(Env(claims=ClaimsPolicy.build(pin_kids_to_issuer=True)), "required")
    signer = RequestSigner(env.ring, clock=env.clock)
    rid = "req-signedgate001"
    sig = signer.sign(method="POST", path=SWARM, audience="gateway", body=b'{"a":1}', request_id=rid)
    hdrs = {**env.headers("swarm:write"), REQUEST_ID_HEADER: rid, "x-s2s-signature": sig}
    d = env.gate.evaluate("POST", SWARM, hdrs, body=b'{"a":1}')
    assert d.allowed and d.signature_kid == "forge:1"
    d2 = env.gate.evaluate("POST", SWARM, {**env.headers("swarm:write"), REQUEST_ID_HEADER: rid}, body=b"{}")
    assert d2.outcome is HardenedOutcome.SIGNATURE_FAILED and d2.reason == "signature_missing"
    sig3 = signer.sign(method="POST", path=SWARM, audience="gateway", body=b"x", request_id=rid)
    d3 = env.gate.evaluate("POST", SWARM, {**env.headers("swarm:write"), REQUEST_ID_HEADER: rid,
                                            "x-s2s-signature": sig3}, body=b"tampered")
    assert d3.outcome is HardenedOutcome.SIGNATURE_FAILED and d3.reason == "signature_invalid"


def _with_verifier(env, mode):
    from skeleton.gate_plane.hardening.gate import HardenedS2SGate

    env.gate = HardenedS2SGate(
        env.gate.base, service="gateway", request_verifier=RequestVerifier("gateway", env.ring, clock=env.clock),
        signature_mode=mode,
    )
    return env


def test_signature_optional_allows_missing():
    env = _with_verifier(Env(), SignatureMode.OPTIONAL)
    assert env.gate.evaluate("GET", SWARM, env.headers("swarm:read")).allowed
    assert env.gate.needs_body


def test_signature_kid_must_belong_to_issuer():
    env = Env(claims=ClaimsPolicy.build(kid_owners={"forge:1": "forge", "tele:1": "telemetry"}))
    env = _with_verifier(env, "required")
    token_headers = env.headers("swarm:read")  # minted with forge:1
    env.ring.rotate("tele:1", b"T" * 32)  # forge:1 keeps verifying during overlap
    sig = RequestSigner(env.ring, clock=env.clock).sign(method="GET", path=SWARM, audience="gateway",
                                                         request_id="req-kidpinning001")
    hdrs = {**token_headers, REQUEST_ID_HEADER: "req-kidpinning001", "x-s2s-signature": sig}
    d = env.gate.evaluate("GET", SWARM, hdrs)
    assert d.outcome is HardenedOutcome.SIGNATURE_FAILED and d.reason == "signature_kid_not_pinned"


def test_rate_limit_by_identity_and_no_admission_charge():
    env = Env(capacity=100, limiter=None)
    env.gate.limiter = ServiceRateLimiter(default=RateRule(rate_per_s=1, burst=2), clock=env.clock)
    before = env.adaptive.stats()["tokens_available"]
    results = [env.gate.evaluate("POST", SWARM, env.headers("swarm:write")) for _ in range(3)]
    assert [r.outcome for r in results] == [HardenedOutcome.ALLOW, HardenedOutcome.ALLOW, HardenedOutcome.RATE_LIMITED]
    limited = results[-1]
    assert limited.http_status == 429 and limited.body()["retry_after_s"] == 1.0
    assert ("retry-after", "1") in limited.response_headers()
    # Only the two admitted writes charged the AdaptiveGate.
    assert before - env.adaptive.stats()["tokens_available"] == 2
    other = env.gate.evaluate("POST", SWARM, env.headers("swarm:write", service="telemetry"))
    assert other.allowed


def test_admission_shed_after_all_checks():
    env = Env(capacity=1)
    assert env.gate.evaluate("POST", SWARM, env.headers("swarm:write")).allowed
    d = env.gate.evaluate("POST", SWARM, env.headers("swarm:write"))
    assert d.outcome is HardenedOutcome.SHED and d.http_status == 429


def test_hooks_never_change_verdict():
    env = Env()
    env.gate.add_hook(lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    assert env.gate.evaluate("GET", SWARM, env.headers("swarm:read")).allowed


def test_layer_descriptor():
    assert HARDENED_GATE_LAYER.name == "s2s_hardened"


# -- ASGI ------------------------------------------------------------------------


def _run(mw, scope, body=b"", chunks=None):
    sent = []
    msgs = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)] if chunks else [
        {"type": "http.request", "body": body, "more_body": False}
    ]

    async def receive():
        return msgs.pop(0) if msgs else {"type": "http.disconnect"}

    async def send(m):
        sent.append(m)

    asyncio.run(mw(scope, receive, send))
    return sent


def _scope(method, path, headers, **extra):
    return {
        "type": "http", "method": method, "path": path, "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()], **extra,
    }


def _hdrs(msg):
    return {k.decode(): v.decode() for k, v in msg["headers"]}


class Downstream:
    def __init__(self):
        self.calls = []

    async def __call__(self, scope, receive, send):
        msg = await receive()
        ctx = current_context()
        outbound = propagate(service="gateway")
        self.calls.append({"body": msg.get("body"), "ctx": ctx, "principal": scope.get(PRINCIPAL_SCOPE_KEY),
                           "outbound": outbound})
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"ok"})


def test_middleware_allows_binds_context_and_echoes_ids():
    env = Env()
    app = Downstream()
    mw = HardenedS2SMiddleware(app, gate=env.gate)
    sent = _run(mw, _scope("GET", SWARM, {**env.headers("swarm:read"), "x-request-id": "req-asgitest00001"}))
    assert sent[0]["status"] == 200
    h = _hdrs(sent[0])
    assert h["x-request-id"] == "req-asgitest00001" and "traceparent" in h
    call = app.calls[0]
    assert call["ctx"].request_id == "req-asgitest00001" and call["principal"].service == "forge"
    assert call["outbound"]["x-request-id"] == "req-asgitest00001" and call["outbound"]["x-s2s-hop"] == "1"
    assert current_context() is None


def test_middleware_rejects_with_json_and_request_id():
    env = Env()
    sent = _run(HardenedS2SMiddleware(Downstream(), gate=env.gate), _scope("GET", SWARM, {}))
    assert sent[0]["status"] == 401
    body = json.loads(sent[1]["body"])
    assert body["error"] == "unauthenticated" and body["request_id"] == _hdrs(sent[0])["x-request-id"]


def test_middleware_conflicting_credentials():
    env = Env()
    t1, t2 = env.token("swarm:read"), env.token("swarm:read")
    scope = _scope("GET", SWARM, {})
    scope["headers"] = [(b"x-service-token", t1.encode()), (b"x-service-token", t2.encode())]
    sent = _run(HardenedS2SMiddleware(Downstream(), gate=env.gate), scope)
    assert sent[0]["status"] == 401 and json.loads(sent[1]["body"])["reason"] == "bad_credentials"


def test_middleware_signed_body_buffered_and_replayed():
    env = _with_verifier(Env(), "required")
    app = Downstream()
    rid = "req-asgisigned001"
    body = b'{"job":"x"}'
    sig = RequestSigner(env.ring, clock=env.clock).sign(method="POST", path=SWARM, audience="gateway", body=body,
                                                        request_id=rid)
    hdrs = {**env.headers("swarm:write"), "x-request-id": rid, "x-s2s-signature": sig}
    sent = _run(HardenedS2SMiddleware(app, gate=env.gate), _scope("POST", SWARM, hdrs), chunks=[body[:4], body[4:]])
    assert sent[0]["status"] == 200 and app.calls[0]["body"] == body


def test_middleware_body_limit():
    env = _with_verifier(Env(), "required")
    sent = _run(HardenedS2SMiddleware(Downstream(), gate=env.gate, max_body_bytes=4),
                _scope("POST", SWARM, env.headers("swarm:write")), body=b"0123456789")
    assert sent[0]["status"] == 413


def test_middleware_passes_non_http():
    env = Env()
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(HardenedS2SMiddleware(app, gate=env.gate)({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


def test_install_hook_and_fastapi_roundtrip():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    env = Env()
    app = fastapi.FastAPI()

    @app.get(SWARM)
    def jobs():
        ctx = current_context()
        return {"rid": ctx.request_id if ctx else None}

    install_hardened_gate(app, env.gate)
    client = TestClient(app)
    r = client.get(SWARM, headers={**env.headers("swarm:read"), "x-request-id": "req-fastapitest01"})
    assert r.status_code == 200 and r.json() == {"rid": "req-fastapitest01"}
    assert r.headers["x-request-id"] == "req-fastapitest01"
    assert client.get(SWARM).status_code == 401
