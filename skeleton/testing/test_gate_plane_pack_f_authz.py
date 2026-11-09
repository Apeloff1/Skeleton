"""Pack F — per-route s2s authZ policy and the layered S2S auth gate."""

from __future__ import annotations

import asyncio
import json

import pytest

from skeleton.gate_plane.admit import AdmissionMatrix
from skeleton.gate_plane.s2s.authz import (
    AuthzReason,
    Effect,
    PolicyError,
    PolicyTable,
    Principal,
    RoutePattern,
    RoutePolicy,
    default_gate_plane_policies,
    evaluate_policy,
    split_path,
)
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.gate import (
    PRINCIPAL_SCOPE_KEY,
    S2S_GATE_LAYER,
    S2SAuthGate,
    S2SAuthMiddleware,
    S2SOutcome,
    TokenExtractionError,
    extract_token,
    install_s2s_gate,
    stack_with_s2s,
)
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import ReplayCache, TokenErrorCode, TokenSigner, TokenVerifier
from skeleton.gate_plane.stack import GATE_LAYERS
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor, Rung

SECRET = b"s" * 32


def svc(name="forge", *scopes, overlap=False):
    return Principal(service=name, scopes=frozenset(scopes), kid="k1", in_overlap=overlap)


# --- patterns --------------------------------------------------------------


@pytest.mark.parametrize(
    "path,parts",
    [("/", []), ("", []), ("/a//b/", ["a", "b"]), ("/a/./b?x=1", ["a", "b"]), ("/a#frag", ["a"])],
)
def test_split_path(path, parts):
    assert split_path(path) == parts


@pytest.mark.parametrize(
    "pattern,path,params",
    [
        ("/", "/", {}),
        ("/api/v1/forge", "/api/v1/forge", {}),
        ("/api/v1/forge", "/api/v1/forge/", {}),
        ("/api/v1/forge/{job_id}", "/api/v1/forge/42", {"job_id": "42"}),
        ("/api/{ver}/forge/{job_id}/run", "/api/v2/forge/7/run", {"ver": "v2", "job_id": "7"}),
        ("/api/*/status", "/api/x/status", {}),
        ("/api/**", "/api", {}),
        ("/api/**", "/api/a/b/c", {}),
        ("/api/v1/forge/{id}/**", "/api/v1/forge/9/a/b", {"id": "9"}),
    ],
)
def test_pattern_matches(pattern, path, params):
    assert RoutePattern.parse(pattern).match(path) == params


@pytest.mark.parametrize(
    "pattern,path",
    [
        ("/api/v1/forge", "/api/v1/forge/x"),
        ("/api/v1/forge/{id}", "/api/v1/forge"),
        ("/api/*/status", "/api/status"),
        ("/api/v1/forge/{id}/**", "/api/v1/forge"),
        ("/", "/x"),
        ("/api/**", "/apix"),
    ],
)
def test_pattern_non_matches(pattern, path):
    assert RoutePattern.parse(pattern).match(path) is None


@pytest.mark.parametrize(
    "bad",
    ["", "api", "/a//b", "/a/**/b", "/a/{Bad}", "/a/{x}/{x}", "/a/b*c", "/a/{x", "/a/b c", None],
)
def test_pattern_parse_rejects(bad):
    with pytest.raises(PolicyError):
        RoutePattern.parse(bad)  # type: ignore[arg-type]


def test_pattern_specificity_order():
    lit = RoutePattern.parse("/api/v1/forge/run")
    param = RoutePattern.parse("/api/v1/forge/{id}")
    glob = RoutePattern.parse("/api/v1/forge/**")
    assert lit.specificity() > param.specificity() > glob.specificity()


def test_pattern_shape_erases_param_names():
    assert RoutePattern.parse("/a/{x}").shape() == RoutePattern.parse("/a/{y}").shape() == RoutePattern.parse("/a/*").shape()


# --- policy build/validation ------------------------------------------------


def test_policy_build_defaults():
    p = RoutePolicy.build("p", "/x")
    assert p.effect is Effect.ALLOW
    assert not p.explicit_methods
    assert p.to_dict()["methods"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"methods": ["TRACE"]},
        {"methods": []},
        {"scopes_all": ["BAD SCOPE"]},
        {"allow_services": ["Bad"]},
        {"allow_services": ["a"], "deny_services": ["a"]},
        {"priority": 10},
        {"priority": -1},
        {"allow_anonymous": True, "scopes_all": ["x:y"]},
        {"allow_anonymous": True, "allow_services": ["a"]},
    ],
)
def test_policy_build_rejects(kwargs):
    with pytest.raises(PolicyError):
        RoutePolicy.build("p", "/x", **kwargs)


def test_policy_build_rejects_empty_name():
    with pytest.raises(PolicyError):
        RoutePolicy.build("", "/x")


def test_policy_from_dict_roundtrip():
    p = RoutePolicy.build(
        "w", "/api/v1/forge/{id}", methods=["post"], scopes_all=["forge:write"], allow_services=["gateway"],
        deny_services=["rogue"], allow_overlap_keys=False, priority=2,
    )
    q = RoutePolicy.from_dict(p.to_dict())
    assert q == p


def test_policy_from_dict_rejects_unknown_and_missing():
    with pytest.raises(PolicyError):
        RoutePolicy.from_dict({"name": "x", "pattern": "/x", "surprise": 1})
    with pytest.raises(PolicyError):
        RoutePolicy.from_dict({"name": "x"})


# --- evaluation ------------------------------------------------------------


def test_explicit_deny_wins():
    p = RoutePolicy.build("d", "/x", effect="deny")
    d = evaluate_policy(p, svc())
    assert not d.allowed and d.reason is AuthzReason.EXPLICIT_DENY and d.http_status == 403


def test_anonymous_allowed_and_forbidden():
    assert evaluate_policy(RoutePolicy.build("a", "/x", allow_anonymous=True), Principal.anonymous_principal()).allowed
    d = evaluate_policy(RoutePolicy.build("b", "/x"), Principal.anonymous_principal())
    assert d.reason is AuthzReason.ANONYMOUS_FORBIDDEN and d.http_status == 401


def test_service_allow_and_deny_lists():
    p = RoutePolicy.build("p", "/x", allow_services=["gateway"], deny_services=["rogue"])
    assert evaluate_policy(p, svc("gateway")).allowed
    assert evaluate_policy(p, svc("forge")).reason is AuthzReason.SERVICE_NOT_ALLOWED
    assert evaluate_policy(p, svc("rogue")).reason is AuthzReason.SERVICE_DENIED


def test_scopes_all_reports_missing():
    p = RoutePolicy.build("p", "/x", scopes_all=["a:read", "a:write", "b:read"])
    d = evaluate_policy(p, svc("forge", "a:read"))
    assert d.reason is AuthzReason.MISSING_SCOPE
    assert d.missing_scopes == ("a:write", "b:read")
    assert evaluate_policy(p, svc("forge", "a:*", "b:read")).allowed


def test_scopes_any():
    p = RoutePolicy.build("p", "/x", scopes_any=["a:read", "a:write"])
    assert evaluate_policy(p, svc("forge", "a:write")).allowed
    d = evaluate_policy(p, svc("forge", "b:read"))
    assert d.reason is AuthzReason.MISSING_SCOPE and d.missing_scopes == ("a:read", "a:write")


def test_overlap_key_forbidden_on_sensitive_route():
    p = RoutePolicy.build("p", "/x", allow_overlap_keys=False)
    assert evaluate_policy(p, svc()).allowed
    assert evaluate_policy(p, svc(overlap=True)).reason is AuthzReason.OVERLAP_KEY_FORBIDDEN


def test_table_default_deny():
    t = PolicyTable([RoutePolicy.build("p", "/x")])
    d = t.evaluate("GET", "/y", svc())
    assert not d.allowed and d.reason is AuthzReason.NO_MATCHING_POLICY


def test_table_method_not_allowed():
    t = PolicyTable([RoutePolicy.build("p", "/x", methods=["GET"])])
    d = t.evaluate("POST", "/x", svc())
    assert d.reason is AuthzReason.METHOD_NOT_ALLOWED and d.http_status == 405


def test_table_most_specific_wins():
    t = PolicyTable(
        [
            RoutePolicy.build("glob", "/api/v1/forge/**", scopes_all=["forge:read"]),
            RoutePolicy.build("param", "/api/v1/forge/{id}", scopes_all=["forge:job"]),
            RoutePolicy.build("lit", "/api/v1/forge/admin", effect="deny"),
        ]
    )
    assert t.match("GET", "/api/v1/forge/admin")[0].name == "lit"
    assert t.match("GET", "/api/v1/forge/42")[0].name == "param"
    assert t.match("GET", "/api/v1/forge/42/logs")[0].name == "glob"
    assert t.evaluate("GET", "/api/v1/forge/42", svc("x", "forge:job")).params == {"id": "42"}


def test_table_explicit_methods_beat_implicit_same_shape():
    t = PolicyTable(
        [
            RoutePolicy.build("any", "/x/{id}", scopes_all=["x:read"]),
            RoutePolicy.build("post", "/x/{id}", methods=["POST"], scopes_all=["x:write"]),
        ]
    )
    assert t.match("POST", "/x/1")[0].name == "post"
    assert t.match("GET", "/x/1")[0].name == "any"


def test_table_rejects_conflicts():
    with pytest.raises(PolicyError):
        PolicyTable([RoutePolicy.build("a", "/x/{id}", methods=["GET"]), RoutePolicy.build("b", "/x/*", methods=["GET", "POST"])])
    with pytest.raises(PolicyError):
        PolicyTable([RoutePolicy.build("a", "/x"), RoutePolicy.build("a", "/y")])


def test_table_allows_disjoint_methods_same_shape():
    t = PolicyTable([RoutePolicy.build("r", "/x", methods=["GET"]), RoutePolicy.build("w", "/x", methods=["POST"])])
    assert len(t) == 2


def test_table_roundtrip_and_digest_stable():
    t = default_gate_plane_policies()
    t2 = PolicyTable.from_dicts(t.to_dicts())
    assert t.digest() == t2.digest()
    assert len(t.digest()) == 64
    t2.add(RoutePolicy.build("extra", "/z"))
    assert t.digest() != t2.digest()


def test_table_explain_lists_all_candidates():
    t = default_gate_plane_policies()
    names = [row["policy"] for row in t.explain("POST", "/api/v1/forge/x")]
    assert set(names) == {"forge-read", "forge-write"}
    ok = {row["policy"]: row["method_ok"] for row in t.explain("POST", "/api/v1/forge/x")}
    assert ok == {"forge-read": False, "forge-write": True}


@pytest.mark.parametrize(
    "method,path,principal,allowed,reason",
    [
        ("GET", "/health", Principal.anonymous_principal(), True, AuthzReason.ALLOWED),
        ("GET", "/api/v1/health/deep", Principal.anonymous_principal(), True, AuthzReason.ALLOWED),
        ("POST", "/health", Principal.anonymous_principal(), False, AuthzReason.METHOD_NOT_ALLOWED),
        ("GET", "/api/v1/forge/kinds", svc("gateway", "forge:read"), True, AuthzReason.ALLOWED),
        ("GET", "/api/v1/forge/kinds", svc("gateway", "forge:write"), True, AuthzReason.ALLOWED),
        ("POST", "/api/v1/forge/blueprint", svc("gateway", "forge:read"), False, AuthzReason.MISSING_SCOPE),
        ("POST", "/api/v1/forge/blueprint", svc("gateway", "forge:write"), True, AuthzReason.ALLOWED),
        ("DELETE", "/api/v1/swarm/n1", svc("gateway", "swarm:write"), True, AuthzReason.ALLOWED),
        ("GET", "/api/v1/admin/flags", svc("gateway", "admin:control"), False, AuthzReason.SERVICE_NOT_ALLOWED),
        ("GET", "/api/v1/admin/flags", svc("control-plane", "admin:control"), True, AuthzReason.ALLOWED),
        ("GET", "/api/v1/admin/flags", svc("control-plane", "admin:control", overlap=True), False, AuthzReason.OVERLAP_KEY_FORBIDDEN),
        ("GET", "/api/v1/unknown", svc("gateway", "forge:*"), False, AuthzReason.NO_MATCHING_POLICY),
        ("GET", "/api/v1/forge/kinds", Principal.anonymous_principal(), False, AuthzReason.ANONYMOUS_FORBIDDEN),
    ],
)
def test_default_table_matrix(method, path, principal, allowed, reason):
    d = default_gate_plane_policies().evaluate(method, path, principal)
    assert d.allowed is allowed
    assert d.reason is reason


def test_default_table_priorities():
    t = default_gate_plane_policies()
    assert t.match("POST", "/api/v1/telemetry/x")[0].priority == 3
    assert t.match("GET", "/api/v1/admin/x")[0].priority == 0


# --- token extraction ------------------------------------------------------


def test_extract_token_variants():
    assert extract_token({}) is None
    assert extract_token({"Authorization": "Service abc"}) == "abc"
    assert extract_token({"authorization": "service   abc  "}) == "abc"
    assert extract_token({"X-Service-Token": "abc"}) == "abc"
    assert extract_token({"authorization": "Service abc", "x-service-token": "abc"}) == "abc"
    assert extract_token({"authorization": "Bearer user-jwt"}) is None


@pytest.mark.parametrize(
    "headers",
    [
        {"authorization": "Service"},
        {"authorization": "Service a b"},
        {"x-service-token": "  "},
        {"authorization": "Service a", "x-service-token": "b"},
    ],
)
def test_extract_token_rejects(headers):
    with pytest.raises(TokenExtractionError):
        extract_token(headers)


# --- gate ------------------------------------------------------------------


class Env:
    def __init__(self, *, gate_capacity=100, admission=True, replay=False):
        self.clock = ManualClock()
        self.ring = KeyRing(clock=self.clock)
        self.ring.add_key("k1", SECRET, activate=True)
        self.verifier = TokenVerifier(
            "gateway", self.ring, clock=self.clock, replay_cache=ReplayCache() if replay else None
        )
        self.governor = ChaosGovernor(min_samples=1000)
        self.matrix = AdmissionMatrix(gate=AdaptiveGate(gate_capacity, 0), governor=self.governor)
        self.decisions = []
        self.gate = S2SAuthGate(
            self.verifier, default_gate_plane_policies(), matrix=self.matrix, admission=admission,
            hooks=[lambda m, p, d: self.decisions.append((m, p, d.outcome))],
        )

    def token(self, service="gateway", *scopes, **kw):
        return TokenSigner(service, self.ring, clock=self.clock).mint("gateway", scopes, **kw)

    def headers(self, *scopes, service="gateway", **kw):
        return {"Authorization": f"Service {self.token(service, *scopes, **kw)}"}


def test_gate_open_probe_bypasses_auth():
    env = Env()
    d = env.gate.evaluate("GET", "/health", {})
    assert d.outcome is S2SOutcome.OPEN_BYPASS and d.allowed and d.http_status == 200


def test_gate_missing_token_401_with_challenge():
    env = Env()
    d = env.gate.evaluate("GET", "/api/v1/forge/kinds", {})
    assert d.outcome is S2SOutcome.UNAUTHENTICATED
    assert d.http_status == 401
    assert d.reason == "missing_token"
    assert dict(d.headers)["www-authenticate"].startswith("Service ")


def test_gate_invalid_token_401_code():
    env = Env()
    d = env.gate.evaluate("GET", "/api/v1/forge/kinds", {"x-service-token": "garbage"})
    assert d.outcome is S2SOutcome.UNAUTHENTICATED
    assert d.token_error is TokenErrorCode.MALFORMED
    assert 'error="invalid_token"' in dict(d.headers)["www-authenticate"]


def test_gate_conflicting_headers_401():
    env = Env()
    d = env.gate.evaluate("GET", "/api/v1/forge/kinds", {"authorization": "Service a", "x-service-token": "b"})
    assert d.reason == "bad_credentials"


def test_gate_allows_read():
    env = Env()
    d = env.gate.evaluate("GET", "/api/v1/forge/kinds", env.headers("forge:read"))
    assert d.outcome is S2SOutcome.ALLOW
    assert d.principal.service == "gateway"
    assert d.policy == "forge-read"
    assert d.admission == "admit"


def test_gate_forbidden_on_missing_scope():
    env = Env()
    d = env.gate.evaluate("POST", "/api/v1/forge/blueprint", env.headers("forge:read"))
    assert d.outcome is S2SOutcome.FORBIDDEN and d.http_status == 403
    assert d.body()["missing_scopes"] == ["forge:write"]


def test_gate_method_not_allowed():
    env = Env()
    table = PolicyTable([RoutePolicy.build("r", "/api/v1/x", methods=["GET"])])
    gate = S2SAuthGate(env.verifier, table, matrix=env.matrix)
    d = gate.evaluate("PUT", "/api/v1/x", env.headers())
    assert d.outcome is S2SOutcome.METHOD_NOT_ALLOWED and d.http_status == 405


def test_gate_sheds_mutations_when_bucket_empty():
    env = Env(gate_capacity=1)
    ok = env.gate.evaluate("POST", "/api/v1/forge/b", env.headers("forge:write"))
    shed = env.gate.evaluate("POST", "/api/v1/forge/b", env.headers("forge:write"))
    assert ok.outcome is S2SOutcome.ALLOW
    assert shed.outcome is S2SOutcome.SHED and shed.http_status == 429
    assert dict(shed.headers)["retry-after"] == "1"


def test_gate_priority_zero_overdraws():
    env = Env(gate_capacity=0)
    d = env.gate.evaluate("POST", "/api/v1/admin/flags", env.headers("admin:control", service="control-plane"))
    assert d.outcome is S2SOutcome.ALLOW


def test_gate_emergency_read_only():
    env = Env()
    with env.governor._lock:
        env.governor._rung = Rung.EMERGENCY_READ_ONLY
    d = env.gate.evaluate("POST", "/api/v1/forge/b", env.headers("forge:write"))
    assert d.outcome is S2SOutcome.EMERGENCY_READ_ONLY and d.http_status == 503
    r = env.gate.evaluate("GET", "/api/v1/forge/b", env.headers("forge:read"))
    assert r.outcome is S2SOutcome.ALLOW


def test_gate_admission_disabled_does_not_charge_bucket():
    env = Env(gate_capacity=1, admission=False)
    for _ in range(5):
        d = env.gate.evaluate("POST", "/api/v1/forge/b", env.headers("forge:write"))
        assert d.outcome is S2SOutcome.ALLOW and d.admission is None


def test_gate_replay_rejected():
    env = Env(replay=True)
    h = env.headers("forge:read")
    assert env.gate.evaluate("GET", "/api/v1/forge/a", h).allowed
    d = env.gate.evaluate("GET", "/api/v1/forge/a", h)
    assert d.token_error is TokenErrorCode.REPLAYED


def test_gate_hooks_observe_and_cannot_break():
    env = Env()

    def boom(*_):
        raise RuntimeError("observer down")

    env.gate.add_hook(boom)
    d = env.gate.evaluate("GET", "/api/v1/forge/a", env.headers("forge:read"))
    assert d.allowed
    assert env.decisions[-1] == ("GET", "/api/v1/forge/a", S2SOutcome.ALLOW)


def test_decision_as_dict_is_secret_free():
    env = Env()
    h = env.headers("forge:read")
    d = env.gate.evaluate("GET", "/api/v1/forge/a", h)
    blob = json.dumps(d.as_dict())
    assert h["Authorization"].split()[1] not in blob
    assert d.as_dict()["service"] == "gateway"


# --- stack ------------------------------------------------------------------


def test_stack_with_s2s_after_auth():
    names = [layer.name for layer in stack_with_s2s()]
    assert names.index("s2s_auth") == names.index("auth") + 1
    assert len(names) == len(GATE_LAYERS) + 1
    assert [layer.name for layer in GATE_LAYERS].count("s2s_auth") == 0  # Pack B catalog untouched


def test_stack_with_s2s_appends_when_no_auth():
    layers = tuple(layer for layer in GATE_LAYERS if layer.name != "auth")
    assert stack_with_s2s(layers)[-1] is S2S_GATE_LAYER


# --- ASGI middleware ----------------------------------------------------------


async def _downstream(scope, receive, send):
    principal = scope.get(PRINCIPAL_SCOPE_KEY)
    body = json.dumps({"service": None if principal is None else principal.service}).encode()
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


def _call(mw, method, path, headers=()):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "method": method, "path": path, "headers": list(headers)}
    asyncio.run(mw(scope, receive, send))
    return sent[0]["status"], json.loads(sent[1]["body"]), dict(sent[0]["headers"])


def test_asgi_allows_and_propagates_principal():
    env = Env()
    mw = S2SAuthMiddleware(_downstream, gate=env.gate)
    tok = env.token("gateway", "forge:read")
    status, body, _ = _call(mw, "GET", "/api/v1/forge/a", [(b"authorization", f"Service {tok}".encode())])
    assert status == 200 and body == {"service": "gateway"}


def test_asgi_denies_with_json_and_challenge():
    env = Env()
    mw = S2SAuthMiddleware(_downstream, gate=env.gate)
    status, body, headers = _call(mw, "GET", "/api/v1/forge/a")
    assert status == 401
    assert body == {"error": "unauthenticated", "reason": "missing_token"}
    assert b"www-authenticate" in headers


def test_asgi_repeated_credential_header_rejected():
    env = Env()
    mw = S2SAuthMiddleware(_downstream, gate=env.gate)
    tok = env.token("gateway", "forge:read")
    status, body, _ = _call(
        mw, "GET", "/api/v1/forge/a",
        [(b"x-service-token", tok.encode()), (b"x-service-token", b"other")],
    )
    assert status == 401 and body["reason"] == "bad_credentials"


def test_asgi_passes_non_http():
    env = Env()
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(S2SAuthMiddleware(app, gate=env.gate)({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


def test_install_hook_with_starlette_app():
    pytest.importorskip("httpx")
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    env = Env()

    async def kinds(request: Request):
        principal = request.scope.get(PRINCIPAL_SCOPE_KEY)
        return JSONResponse({"caller": principal.service})

    app = Starlette(routes=[Route("/api/v1/forge/kinds", kinds)])
    install_s2s_gate(app, env.gate)
    client = TestClient(app)
    assert client.get("/api/v1/forge/kinds").status_code == 401
    ok = client.get("/api/v1/forge/kinds", headers=env.headers("forge:read"))
    assert ok.status_code == 200 and ok.json() == {"caller": "gateway"}
    denied = client.post("/api/v1/forge/kinds", headers=env.headers("forge:read"))
    assert denied.status_code == 403
