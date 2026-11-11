import pytest

from skeleton.api.v1_edge.auth import ApiKeyStore, EdgeAuthenticator, SessionVerifier
from skeleton.api.v1_edge.edge import EdgeConfig, build_v1_edge
from skeleton.api.v1_edge.health import HealthRegistry
from skeleton.api.v1_edge.idempotency import IdempotencyCache
from skeleton.api.v1_edge.quotas import QuotaPolicy, TenantQuotas
from skeleton.api.v1_edge.registry import RouteRegistry, RouteSpec
from skeleton.api.v1_edge.security import CorsPolicy
from skeleton.api.v1_edge.webhook_ingress import WebhookIngressVerifier
from starlette.testclient import TestClient

SECRET = b"s" * 32
calls = []


async def downstream(scope, receive, send):
    body = b""
    while True:
        m = await receive()
        body += m.get("body", b"")
        if not m.get("more_body"):
            break
    calls.append(scope["path"])
    st = scope.get("state", {})
    p = st.get("principal")
    import json
    out = json.dumps({"path": scope["path"], "tenant": getattr(p, "tenant", None),
                      "n": len(calls), "echo": body.decode() or None,
                      "params": st.get("path_params")}).encode()
    status = 500 if scope["path"].endswith("/boom") else 201 if scope["method"] == "POST" else 200
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": out})


@pytest.fixture
def env():
    calls.clear()
    reg = RouteRegistry()
    reg.register(RouteSpec("GET", "/public/ping", auth="public"))
    reg.register(RouteSpec("GET", "/projects/{pid}", scopes={"projects:read"}))
    reg.register(RouteSpec("POST", "/projects", auth="api_key", scopes={"projects:write"},
                           idempotent_writes=True, quota_class="writes",
                           schema={"type": "object", "required": ["name"], "additionalProperties": False,
                                   "properties": {"name": {"type": "string", "minLength": 1}}}))
    reg.register(RouteSpec("POST", "/boom", idempotent_writes=True))
    reg.register(RouteSpec("GET", "/me", auth="session"))
    reg.register(RouteSpec("POST", "/webhooks/{source}", auth="public"))
    keys = ApiKeyStore()
    token = keys.add("k1", "secretvalue", subject="svc", tenant="t1", scopes={"projects:read", "projects:write"})
    ro = keys.add("k2", "readonly", subject="ro", tenant="t2", scopes={"projects:read"})
    sessions = SessionVerifier(SECRET)
    health = HealthRegistry()
    health.add("db", lambda: True)
    traces = []
    cfg = EdgeConfig(registry=reg, auth=EdgeAuthenticator(keys, sessions),
                     quotas=TenantQuotas({"default": QuotaPolicy(1000, 1000),
                                          "writes": QuotaPolicy(0.001, 6)}),
                     cors=CorsPolicy(frozenset({"https://app.example"})), health=health,
                     idempotency=IdempotencyCache(), webhooks=WebhookIngressVerifier({"gh": SECRET}),
                     max_body=1024, on_trace=traces.append)
    client = TestClient(build_v1_edge(downstream, cfg))
    return dict(client=client, token=token, ro=ro, sessions=sessions, health=health, traces=traces, cfg=cfg)
