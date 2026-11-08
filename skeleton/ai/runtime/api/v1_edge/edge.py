"""Compose the /api/v1 edge as one pure-ASGI wrapper.

Order: tracing/request-id -> security headers -> CORS -> health -> route match
(404/405 envelope) -> auth policy -> tenant quota -> body read + validation ->
webhook signature -> idempotency replay -> downstream app. Paths outside
/api/v1 pass straight through untouched.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .auth import EdgeAuthenticator
from .envelope import EdgeError, header, send_error, send_json, set_header
from .health import HealthRegistry
from .idempotency import IdempotencyCache
from .quotas import TenantQuotas
from .registry import V1_PREFIX, RouteRegistry
from .security import DEFAULT_SECURITY_HEADERS, CorsPolicy
from .tracing import parse_or_start, request_id
from .validation import validate
from .webhook_ingress import WebhookIngressVerifier

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class EdgeConfig:
    registry: RouteRegistry
    auth: EdgeAuthenticator
    quotas: Optional[Any] = None  # TenantQuotas, or quota_store.DistributedQuotas (route-aware)
    cors: CorsPolicy = field(default_factory=CorsPolicy)
    health: Optional[HealthRegistry] = None
    idempotency: Optional[IdempotencyCache] = None
    webhooks: Optional[WebhookIngressVerifier] = None
    webhook_prefix: str = "/webhooks/"
    max_body: int = 1 << 20
    security_headers: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SECURITY_HEADERS))
    on_trace: Optional[Callable[[Dict[str, Any]], None]] = None


class _Replay:
    def __init__(self, body: bytes):
        self.body, self.sent = body, False

    async def __call__(self):
        if self.sent:
            return {"type": "http.disconnect"}
        self.sent = True
        return {"type": "http.request", "body": self.body, "more_body": False}


def build_v1_edge(app, cfg: EdgeConfig):
    health_live = V1_PREFIX + "/health/live"
    health_ready = V1_PREFIX + "/health/ready"

    if type(cfg.max_body) is not int or not 1 <= cfg.max_body <= 4 * 1024 * 1024:
        raise ValueError("edge body capacity must be bounded")

    async def edge(scope, receive, send):
        if scope["type"] != "http" or not (scope["path"] == V1_PREFIX
                or scope["path"].startswith(V1_PREFIX + "/")):
            return await app(scope, receive, send)
        path, method = scope["path"], scope["method"].upper()
        rid = request_id(header(scope, "x-request-id"))
        trace = parse_or_start(header(scope, "traceparent"))
        origin = header(scope, "origin")
        extra: Dict[str, str] = dict(cfg.security_headers)
        extra["x-request-id"] = rid
        extra["traceparent"] = trace.traceparent()
        if origin and cfg.cors.allowed(origin):
            extra.update(cfg.cors.response_headers(origin))
        status_box = {"status": 0}

        async def wsend(msg):
            if msg["type"] == "http.response.start":
                hdrs = msg.get("headers", [])
                for k, v in extra.items():
                    hdrs = set_header(hdrs, k, v)
                msg = {**msg, "headers": hdrs}
                status_box["status"] = msg["status"]
            await send(msg)

        def emit(principal=None):
            if cfg.on_trace:
                cfg.on_trace({"request_id": rid, "trace_id": trace.trace_id, "method": method,
                              "path": path, "status": status_box["status"],
                              "tenant": getattr(principal, "tenant", None)})

        principal = None
        try:
            if method == "OPTIONS" and origin and header(scope, "access-control-request-method"):
                pf = cfg.cors.preflight_headers(origin, header(scope, "access-control-request-method"),
                                                header(scope, "access-control-request-headers"))
                if pf is None:
                    raise EdgeError(403, "EDGE.CORS.DENIED", "cors preflight denied")
                extra.update(pf)
                await wsend({"type": "http.response.start", "status": 204, "headers": []})
                await wsend({"type": "http.response.body", "body": b""})
                return
            if cfg.health and path == health_live and method in ("GET", "HEAD"):
                await send_json(wsend, 200, cfg.health.live())
                return
            if cfg.health and path == health_ready and method in ("GET", "HEAD"):
                code, body = await cfg.health.ready()
                await send_json(wsend, code, body)
                return
            spec, params, known = cfg.registry.match(method, path)
            if spec is None:
                if known:
                    raise EdgeError(405, "EDGE.METHOD_NOT_ALLOWED", "method not allowed",
                                    headers={"allow": ", ".join(cfg.registry.allowed_methods(path))})
                raise EdgeError(404, "EDGE.NOT_FOUND", "no such route")
            principal = cfg.auth.enforce(spec, scope)
            if cfg.quotas is not None:
                check_request = getattr(cfg.quotas, "check_request", None)
                if check_request is not None:  # distributed quotas: route-aware buckets
                    extra.update(check_request(principal.tenant, spec, method))
                else:
                    extra.update(cfg.quotas.check(principal.tenant, spec.quota_class))
            body = b""
            if method in UNSAFE:
                body = await _read_body(receive, cfg.max_body)
            if spec.schema is not None and method in UNSAFE:
                ctype = (header(scope, "content-type") or "").split(";")[0].strip().lower()
                if ctype != "application/json":
                    raise EdgeError(415, "EDGE.UNSUPPORTED_MEDIA", "expected application/json")
                try:
                    doc = json.loads(body or b"null")
                except ValueError:
                    raise EdgeError(400, "EDGE.MALFORMED_JSON", "malformed json") from None
                errs = validate(doc, spec.schema)
                if errs:
                    raise EdgeError(422, "EDGE.VALIDATION", "request validation failed", {"errors": errs})
            if cfg.webhooks is not None and spec.path.startswith(cfg.webhook_prefix):
                cfg.webhooks.verify(params.get("source", ""), header(scope, "x-skeleton-signature"), body)
            new_scope = dict(scope)
            new_scope["state"] = {**scope.get("state", {}), "principal": principal, "route": spec,
                                  "path_params": params, "request_id": rid, "trace": trace}
            ikey = header(scope, "idempotency-key")
            if cfg.idempotency is not None and spec.idempotent_writes and method in UNSAFE:
                if not ikey or len(ikey) > 255:
                    raise EdgeError(400, "EDGE.IDEMPOTENCY.KEY_REQUIRED", "idempotency-key header required")
                # Use a non-ambiguous principal identity and action key:
                # two users on the same tenant must never replay each other's response.
                import hashlib
                identity = json.dumps([principal.tenant, principal.subject,
                                       principal.method, method, path, ikey],
                                      separators=(",", ":"), ensure_ascii=True)
                cache_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                await _idempotent(app, cfg.idempotency, new_scope, body, wsend,
                                  cache_key,
                                  IdempotencyCache.fingerprint(method, path, body))
                return
            await app(new_scope, _Replay(body) if method in UNSAFE else receive, wsend)
        except EdgeError as err:
            await send_error(wsend, err, rid)
        finally:
            emit(principal)

    return edge


async def _read_body(receive, limit: int) -> bytes:
    chunks: List[bytes] = []
    size = 0
    frames = 0
    while True:
        frames += 1
        if frames > 4096:
            raise EdgeError(413, "EDGE.BODY_TOO_MANY_FRAMES", "request exceeded body frame budget")
        msg = await receive()
        if msg["type"] == "http.disconnect":
            raise EdgeError(400, "EDGE.CLIENT_DISCONNECT", "client disconnected")
        if msg.get("type") != "http.request":
            raise EdgeError(400, "EDGE.BAD_BODY_FRAME", "invalid request frame")
        chunk = msg.get("body", b"")
        if type(chunk) is not bytes:
            raise EdgeError(400, "EDGE.BAD_BODY_FRAME", "invalid body frame type")
        size += len(chunk)
        if size > limit:
            raise EdgeError(413, "EDGE.BODY_TOO_LARGE", "request body too large", {"limit": limit})
        chunks.append(chunk)
        if not msg.get("more_body"):
            return b"".join(chunks)


async def _idempotent(app, cache: IdempotencyCache, scope, body, send, key, fp):
    stored = cache.begin(key, fp)
    if stored is not None:
        hdrs = set_header(stored.headers, "idempotent-replayed", "true")
        await send({"type": "http.response.start", "status": stored.status, "headers": hdrs})
        await send({"type": "http.response.body", "body": stored.body})
        return
    cap = {"status": 500, "headers": [], "body": []}

    async def capture(msg):
        if msg["type"] == "http.response.start":
            cap["status"], cap["headers"] = msg["status"], list(msg.get("headers", []))
        elif msg["type"] == "http.response.body":
            payload = msg.get("body", b"")
            if type(payload) is not bytes:
                cache.abandon(key)
                raise EdgeError(502, "EDGE.IDEMPOTENCY.BAD_RESPONSE", "invalid downstream body")
            if sum(len(p) for p in cap["body"]) + len(payload) > cache.max_body:
                cap["overflow"] = True
                cap["body"].clear()
            elif not cap.get("overflow"):
                cap["body"].append(payload)
        await send(msg)

    try:
        await app(scope, _Replay(body), capture)
    except BaseException:
        cache.abandon(key)
        raise
    if cap.get("overflow") or not 200 <= cap["status"] < 500:
        cache.abandon(key)
    else:
        cache.complete(key, cap["status"], cap["headers"], b"".join(cap["body"]))
