"""Loopback-only reverse proxy for the local inference runtime.

The local AI runtime (the pinned llama.cpp server provisioned by
``scripts/provision_local_ai.py``) listens on loopback only. This proxy is
the single gate-plane path to it:

* the upstream host must be a loopback literal or ``localhost``; anything
  else is refused at construction (no DNS lookups, no remote fallback);
* only an allowlist of operations is forwarded, each mapped to a fixed
  upstream path, so callers cannot reach arbitrary runtime endpoints;
* request bodies must be JSON objects, ``stream`` is forced off and
  ``max_tokens`` / ``n_predict`` are clamped;
* every call runs through the Pack F pipeline (deadline, retry budget,
  circuit breaker) for the ``system-local-ai`` upstream;
* responses are size-bounded and redirects are failures.
"""

# No ``from __future__ import annotations``: FastAPI resolves the locally imported
# ``Request`` annotation on the nested route handlers at definition time.

import http.client
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from skeleton.gate_plane.pipeline.breaker import BreakerConfig
from skeleton.gate_plane.pipeline.core import CallContext, PipelineRequest, PipelineResponse
from skeleton.gate_plane.pipeline.errors import PipelineError
from skeleton.gate_plane.pipeline.retry import RetrySpec
from skeleton.gate_plane.pipeline.routes import PipelineRouter, RouteConfig, RouteTable
from skeleton.gate_plane.s2s.clock import Clock, system_clock
from skeleton.gate_plane.systems.readiness import is_loopback_host

UPSTREAM = "system-local-ai"
DEFAULT_MAX_TOKENS = 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class LocalAIProxyError(ValueError):
    pass


@dataclass(frozen=True)
class Operation:
    name: str
    method: str
    upstream_path: str
    has_body: bool


OPERATIONS: Dict[str, Operation] = {
    "health": Operation("health", "GET", "/health", False),
    "models": Operation("models", "GET", "/v1/models", False),
    "chat": Operation("chat", "POST", "/v1/chat/completions", True),
    "complete": Operation("complete", "POST", "/v1/completions", True),
}


@dataclass(frozen=True)
class ProxyResult:
    status: int
    body: Any
    operation: str
    attempts: int
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "operation": self.operation, "attempts": self.attempts, "error": self.error}


def sanitize_body(op: Operation, body: Any, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> Dict[str, Any]:
    if not isinstance(body, Mapping):
        raise LocalAIProxyError("body must be a JSON object")
    out = dict(body)
    out["stream"] = False
    for key in ("max_tokens", "n_predict"):
        if key in out:
            try:
                v = int(out[key])
            except (TypeError, ValueError) as exc:
                raise LocalAIProxyError(f"{key} must be an integer") from exc
            if v <= 0:
                raise LocalAIProxyError(f"{key} must be > 0")
            out[key] = min(v, max_tokens)
    if "max_tokens" not in out and "n_predict" not in out:
        out["max_tokens"] = max_tokens
    if op.name == "chat":
        msgs = out.get("messages")
        if not isinstance(msgs, list) or not msgs:
            raise LocalAIProxyError("chat requires a non-empty messages list")
        for m in msgs:
            if not isinstance(m, Mapping) or not isinstance(m.get("role"), str) or "content" not in m:
                raise LocalAIProxyError("each message needs role and content")
    if op.name == "complete" and not isinstance(out.get("prompt"), (str, list)):
        raise LocalAIProxyError("complete requires a prompt")
    return out


def default_local_ai_routes(*, timeout_s: float = 120.0, read_timeout_s: float = 5.0) -> RouteTable:
    breaker = BreakerConfig(consecutive_failures=3, min_calls=3, window_size=6, cooldown_s=15.0)
    return RouteTable([
        RouteConfig(
            name="local-ai-read", pattern="/v1/**", upstream=UPSTREAM, methods=frozenset({"GET"}),
            timeout_s=read_timeout_s, retry=RetrySpec(max_attempts=2, base_backoff_s=0.05, max_backoff_s=0.2),
            breaker=breaker,
        ),
        RouteConfig(
            name="local-ai-health", pattern="/health", upstream=UPSTREAM, methods=frozenset({"GET"}),
            timeout_s=read_timeout_s, retry=RetrySpec.no_retry(), breaker=None,
        ),
        RouteConfig(
            name="local-ai-infer", pattern="/v1/**", upstream=UPSTREAM, methods=frozenset({"POST"}),
            # Inference is not idempotent work: one attempt, breaker on.
            timeout_s=timeout_s, retry=RetrySpec.no_retry(), breaker=breaker,
        ),
    ])


class LocalAIProxy:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        *,
        clock: Optional[Clock] = None,
        routes: Optional[RouteTable] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        connection_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        if not is_loopback_host(host):
            raise LocalAIProxyError(f"local AI upstream must be loopback, got {host!r}")
        if not (0 < int(port) < 65536):
            raise LocalAIProxyError("port out of range")
        if max_tokens < 1:
            raise LocalAIProxyError("max_tokens must be >= 1")
        self.host = host
        self.port = int(port)
        self.clock: Clock = clock if clock is not None else system_clock()
        self.router = PipelineRouter(routes if routes is not None else default_local_ai_routes(), clock=self.clock)
        self.max_tokens = int(max_tokens)
        self.max_response_bytes = int(max_response_bytes)
        self._factory = connection_factory or http.client.HTTPConnection

    # -- transport ----------------------------------------------------------
    def _transport(self, req: PipelineRequest, ctx: CallContext) -> PipelineResponse:
        remaining = ctx.deadline.remaining() if ctx.deadline is not None else None
        timeout = 5.0 if remaining is None else max(0.01, float(remaining))
        conn = self._factory(self.host, self.port, timeout=timeout)
        try:
            headers = {"accept": "application/json"}
            if req.body:
                headers["content-type"] = "application/json"
                headers["content-length"] = str(len(req.body))
            conn.request(req.verb, req.path, body=req.body or None, headers=headers)
            resp = conn.getresponse()
            raw = resp.read(self.max_response_bytes + 1)
            status = int(resp.status)
            hdrs = tuple((k.lower(), v) for k, v in resp.getheaders())
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        if len(raw) > self.max_response_bytes:
            return PipelineResponse(502, {"error": "upstream_response_too_large"})
        if 300 <= status < 400:
            return PipelineResponse(502, {"error": "upstream_redirect_refused"})
        try:
            body: Any = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return PipelineResponse(502 if status < 500 else status, {"error": "upstream_not_json"}, hdrs)
        return PipelineResponse(status, body, hdrs)

    # -- public -------------------------------------------------------------
    def call(self, operation: str, body: Any = None, *, service: Optional[str] = None) -> ProxyResult:
        op = OPERATIONS.get(operation)
        if op is None:
            return ProxyResult(404, {"error": "unknown_operation"}, operation, 0, "unknown_operation")
        payload = b""
        if op.has_body:
            try:
                clean = sanitize_body(op, body, max_tokens=self.max_tokens)
            except LocalAIProxyError as exc:
                return ProxyResult(400, {"error": "invalid_request", "reason": str(exc)}, op.name, 0, "invalid_request")
            payload = json.dumps(clean, separators=(",", ":")).encode("utf-8")
        preq = PipelineRequest(method=op.method, path=op.upstream_path, body=payload, service=service)
        try:
            resp, ctx = self.router.call(preq, self._transport)
        except PipelineError as exc:
            code = type(exc).__name__
            status = 503 if code in ("BreakerOpenError", "RetryBudgetExhausted") else 504 if "Deadline" in code or "Timeout" in code else 502
            return ProxyResult(status, {"error": "upstream_unavailable", "reason": code}, op.name, 0, code)
        except (OSError, http.client.HTTPException) as exc:
            return ProxyResult(502, {"error": "upstream_unreachable"}, op.name, 0, type(exc).__name__)
        return ProxyResult(resp.status, resp.body, op.name, max(1, ctx.attempt), None)

    def breaker_states(self) -> Dict[str, str]:
        return self.router.breakers.states()


def build_local_ai_router(proxy: LocalAIProxy, *, prefix: str = "/api/v1/local-ai") -> Any:
    """FastAPI router exposing the allowlisted operations under ``prefix``."""
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter(prefix=prefix, tags=["local-ai-edge"])

    def _caller(request: Request) -> Optional[str]:
        return request.headers.get("x-skeleton-caller")

    def _reply(res: ProxyResult) -> JSONResponse:
        return JSONResponse(res.body if res.body is not None else {}, status_code=res.status)

    @router.get("/health")
    def health(request: Request) -> JSONResponse:
        return _reply(proxy.call("health", service=_caller(request)))

    @router.get("/models")
    def models(request: Request) -> JSONResponse:
        return _reply(proxy.call("models", service=_caller(request)))

    async def _json(request: Request) -> Tuple[Any, Optional[JSONResponse]]:
        raw = await request.body()
        try:
            return json.loads(raw.decode("utf-8") or "null"), None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, JSONResponse({"error": "invalid_json"}, status_code=400)

    @router.post("/chat")
    async def chat(request: Request) -> JSONResponse:
        body, err = await _json(request)
        if err is not None:
            return err
        return _reply(proxy.call("chat", body, service=_caller(request)))

    @router.post("/complete")
    async def complete(request: Request) -> JSONResponse:
        body, err = await _json(request)
        if err is not None:
            return err
        return _reply(proxy.call("complete", body, service=_caller(request)))

    @router.get("/admin/breakers")
    def breakers() -> Dict[str, str]:
        return proxy.breaker_states()

    return router


__all__ = [
    "DEFAULT_MAX_TOKENS",
    "LocalAIProxy",
    "LocalAIProxyError",
    "OPERATIONS",
    "Operation",
    "ProxyResult",
    "UPSTREAM",
    "build_local_ai_router",
    "default_local_ai_routes",
    "sanitize_body",
]
