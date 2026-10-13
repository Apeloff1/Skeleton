"""Mountable FastAPI/ASGI gateway for the agent edge, routed through the gate plane.

Every request runs the Pack F gate plane in a fixed order::

    1. auth          S2SAuthGate (token + route policy on a canonical path)
                     then AgentAuthority (delegation-aware principal)       -> 401/403/405
    2. backpressure  BackpressureStage inside the pipeline (shed/delay)     -> 429/503 + Retry-After
    3. pipeline      PipelineRouter: deadline -> breaker -> edge handler     -> 503/504 on open/timeout

Nothing here touches ``skeleton/api/server.py`` or any application
lifespan: hosts opt in with ``app.include_router(build_agent_gateway_router(gw))``
or ``app.mount("/edge", create_agent_gateway_app(gw))``. Route policies are
evaluated against *canonical* paths (``/agents/<op>``) produced by each
endpoint, so the authorization result does not depend on where the router
is mounted.
"""

# NOTE: no ``from __future__ import annotations`` here: FastAPI resolves the
# endpoint annotations (``Request``) at runtime from the enclosing scope.

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from skeleton.gate_plane.agent_edge.auth import AgentAuthError, AgentAuthority, AgentPrincipal
from skeleton.gate_plane.agent_edge.edge import AgentEdge, EdgeError, SendRequest
from skeleton.gate_plane.backpressure.gate import BackpressureGate, backpressure_stage_factory
from skeleton.gate_plane.backpressure.snapshot import retry_after_header
from skeleton.gate_plane.pipeline.breaker import BreakerConfig, BreakerRegistry
from skeleton.gate_plane.pipeline.core import CallContext, PipelineRequest, PipelineResponse
from skeleton.gate_plane.pipeline.errors import PipelineError
from skeleton.gate_plane.pipeline.retry import RetrySpec
from skeleton.gate_plane.pipeline.routes import PipelineRouter, RouteConfig, RouteTable
from skeleton.gate_plane.s2s.authz import PolicyTable, RoutePolicy
from skeleton.gate_plane.s2s.gate import S2SAuthGate, TokenExtractionError, extract_token
from skeleton.gate_plane.s2s.tokens import TokenVerifier

DEFAULT_PREFIX = "/api/v1/agents"
CANONICAL_ROOT = "/agents"
UPSTREAM = "agent-bus"
TENANT_HEADER = "x-tenant-id"
PRIORITY_HEADER = "x-priority"
GATE_ORDER: Tuple[str, ...] = ("auth", "backpressure", "pipeline")


def default_edge_policies() -> PolicyTable:
    """Health is anonymous; every other edge op needs a valid agent token.

    Fine-grained capability checks (``msg:send:<topic>``, ``msg:recv`` ...)
    are enforced by :class:`AgentAuthority` because they depend on the body.
    """
    return PolicyTable(
        [
            RoutePolicy.build("agent-edge-health", f"{CANONICAL_ROOT}/health", methods=["GET", "HEAD"], allow_anonymous=True, priority=0),
            RoutePolicy.build("agent-edge-ops", f"{CANONICAL_ROOT}/**", priority=2),
        ]
    )


def default_edge_routes(*, timeout_s: float = 5.0, breaker: Optional[BreakerConfig] = None) -> RouteTable:
    return RouteTable(
        [
            RouteConfig(
                name="agent-edge",
                pattern=f"{CANONICAL_ROOT}/**",
                upstream=UPSTREAM,
                timeout_s=timeout_s,
                retry=RetrySpec.no_retry(),
                breaker=breaker or BreakerConfig(consecutive_failures=20, min_calls=50, window_size=100, cooldown_s=5.0),
            )
        ]
    )


@dataclass(frozen=True)
class GatewayResult:
    status: int
    body: Any
    headers: Tuple[Tuple[str, str], ...] = ()
    stage: str = "pipeline"

    def header(self, name: str) -> Optional[str]:
        low = name.lower()
        for k, v in self.headers:
            if k.lower() == low:
                return v
        return None


Operation = Callable[[AgentPrincipal], Tuple[int, Any]]


@dataclass
class AgentGateway:
    """Framework-neutral core: ``handle()`` runs auth -> backpressure -> pipeline."""

    edge: AgentEdge
    backpressure: Optional[BackpressureGate] = None
    policies: PolicyTable = field(default_factory=default_edge_policies)
    routes: RouteTable = field(default_factory=default_edge_routes)
    breakers: Optional[BreakerRegistry] = None
    stage_factories: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        authority: AgentAuthority = self.edge.authority
        self.s2s = S2SAuthGate(
            TokenVerifier(authority.audience, authority.keyring, clock=authority.clock, leeway_s=authority.leeway_s),
            self.policies,
            admission=False,  # load is governed by the backpressure stage below
        )
        factories: Dict[str, Any] = dict(self.stage_factories or {})
        if self.backpressure is not None and "backpressure" not in factories:
            factories["backpressure"] = backpressure_stage_factory(self.backpressure)
        self.pipelines = PipelineRouter(
            self.routes,
            clock=authority.clock,
            breakers=self.breakers or BreakerRegistry(clock=authority.clock),
            stage_factories=factories,
        )
        self.counts: Dict[str, int] = {}

    def _count(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1

    # -- stage 1: auth ------------------------------------------------------------------
    def authenticate(self, method: str, op_path: str, headers: Mapping[str, str]) -> Tuple[Optional[AgentPrincipal], Optional[GatewayResult]]:
        decision = self.s2s.evaluate(method, op_path, headers)
        if not decision.allowed:
            self._count(f"auth_{decision.outcome.value}")
            return None, GatewayResult(decision.http_status, decision.body(), tuple(decision.headers), "auth")
        if decision.principal is None or decision.principal.anonymous:
            return None, None
        try:
            raw = extract_token(headers)
        except TokenExtractionError as exc:  # pragma: no cover - S2S gate already rejected
            return None, GatewayResult(401, {"error": "unauthenticated", "reason": exc.detail}, (), "auth")
        if raw is None:  # pragma: no cover - principal implies a token
            return None, GatewayResult(401, {"error": "unauthenticated", "reason": "missing_token"}, (), "auth")
        try:
            return self.edge.authority.principal_from(self.s2s.verifier.verify(raw)), None
        except AgentAuthError as exc:
            self._count(f"auth_{exc.failure.value}")
            return None, GatewayResult(exc.http_status, exc.body(), (), "auth")
        except Exception as exc:  # noqa: BLE001 - token errors already mapped by the S2S gate
            return None, GatewayResult(401, {"error": "unauthenticated", "reason": type(exc).__name__}, (), "auth")

    # -- full chain ------------------------------------------------------------------------
    def handle(
        self,
        method: str,
        op: str,
        headers: Mapping[str, str],
        operation: Operation,
        *,
        anonymous_ok: bool = False,
    ) -> GatewayResult:
        op_path = f"{CANONICAL_ROOT}/{op.strip('/')}"
        lowered = {str(k).lower(): str(v) for k, v in headers.items()}
        principal, denied = self.authenticate(method, op_path, lowered)
        if denied is not None:
            return denied
        if principal is None and not anonymous_ok:
            return GatewayResult(401, {"error": "unauthenticated", "reason": "missing_token"}, (), "auth")
        priority = 1
        raw_prio = lowered.get(PRIORITY_HEADER)
        if raw_prio is not None and raw_prio.strip().isdigit():
            # callers may lower their priority, never claim control priority 0
            priority = max(1, min(9, int(raw_prio.strip())))
        request = PipelineRequest(
            method=method.upper(),
            path=op_path,
            headers=dict(lowered),
            tenant_id=lowered.get(TENANT_HEADER) or (principal.agent_id if principal else None),
            priority=priority,
            service=None if principal is None else principal.agent_id,
        )
        stage_box: Dict[str, str] = {"stage": "backpressure"}

        def handler(req: PipelineRequest, ctx: CallContext) -> PipelineResponse:
            stage_box["stage"] = "pipeline"
            try:
                status, body = operation(principal)  # type: ignore[arg-type]
            except AgentAuthError as exc:
                return PipelineResponse(exc.http_status, exc.body())
            except EdgeError as exc:
                hdrs: Tuple[Tuple[str, str], ...] = ()
                if exc.retry_after_s is not None:
                    hdrs = (("retry-after", retry_after_header(exc.retry_after_s)),)
                return PipelineResponse(exc.status, exc.body(), hdrs)
            return PipelineResponse(status, body)

        try:
            response, _ctx = self.pipelines.call(request, handler)
        except PipelineError as exc:
            self._count(f"pipeline_{type(exc).__name__}")
            hdrs = ()
            ra = exc.retry_after_header()
            if ra is not None:
                hdrs = (("retry-after", ra),)
            body = {"error": getattr(exc, "reason", "pipeline_error"), "detail": exc.detail}
            if exc.retry_after_s is not None:
                body["retry_after_s"] = exc.retry_after_s
            return GatewayResult(exc.status, body, hdrs, "pipeline")
        stage = stage_box["stage"]
        if stage == "backpressure":
            self._count("backpressure_shed")
        else:
            self._count(f"status_{response.status // 100}xx")
        return GatewayResult(response.status, response.body, tuple(response.headers), stage)

    def describe(self) -> Dict[str, Any]:
        return {
            "order": list(GATE_ORDER),
            "policies": self.policies.to_dicts(),
            "pipelines": self.pipelines.describe(),
            "counts": dict(self.counts),
        }


# ---------------------------------------------------------------------------------------
# FastAPI adapter
# ---------------------------------------------------------------------------------------


def _body_dict(raw: bytes) -> Dict[str, Any]:
    import json

    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise EdgeError("body is not valid JSON") from exc
    if not isinstance(data, dict):
        raise EdgeError("body must be a JSON object")
    return data


def build_agent_gateway_router(gateway: AgentGateway, *, prefix: str = DEFAULT_PREFIX, tags: Optional[List[str]] = None) -> Any:
    """Return a FastAPI ``APIRouter`` exposing the edge (include it; no lifespan)."""
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool

    router = APIRouter(prefix=prefix, tags=tags or ["agent-edge"])
    edge = gateway.edge

    def respond(result: GatewayResult) -> Any:
        headers = {k: v for k, v in result.headers}
        headers["x-gate-stage"] = result.stage
        return JSONResponse(status_code=result.status, content=result.body, headers=headers)

    async def run(request: Request, method: str, op: str, build: Callable[[Dict[str, Any]], Operation], *, anonymous_ok: bool = False) -> Any:
        try:
            body = _body_dict(await request.body()) if method in ("POST", "PUT", "PATCH") else {}
            operation = build(body)
        except EdgeError as exc:
            return respond(GatewayResult(exc.status, exc.body(), (), "request"))
        headers = {k: v for k, v in request.headers.items()}
        result = await run_in_threadpool(gateway.handle, method, op, headers, operation, anonymous_ok=anonymous_ok)
        return respond(result)

    @router.get("/health")
    async def health(request: Request) -> Any:
        def build(_b: Dict[str, Any]) -> Operation:
            def op(_p: Optional[AgentPrincipal]) -> Tuple[int, Any]:
                stats = edge.bus.stats()
                return 200, {"status": "ok", "pending": stats["pending"], "dead_letters": stats["dlq"]["size"], "order": list(GATE_ORDER)}

            return op  # type: ignore[return-value]

        return await run(request, "GET", "health", build, anonymous_ok=True)

    @router.post("/messages")
    async def send(request: Request) -> Any:
        def build(body: Dict[str, Any]) -> Operation:
            req = SendRequest.from_dict(body)

            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                out = edge.send(p, req)
                status = 202 if out.publish.accepted else 200
                return status, out.as_dict()

            return op

        return await run(request, "POST", "messages", build)

    @router.post("/mailbox/{agent_id}/pull")
    async def pull(agent_id: str, request: Request) -> Any:
        def build(body: Dict[str, Any]) -> Operation:
            try:
                max_messages = int(body.get("max_messages", 1))
                lease_s = None if body.get("lease_s") is None else float(body["lease_s"])
            except (TypeError, ValueError) as exc:
                raise EdgeError(str(exc)) from exc
            topics = body.get("topics")
            if topics is not None and (not isinstance(topics, list) or not all(isinstance(t, str) for t in topics)):
                raise EdgeError("topics must be a list of strings")

            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                ds = edge.pull(p, agent_id, max_messages=max_messages, lease_s=lease_s, topics=topics)
                return 200, {"deliveries": [d.as_dict() for d in ds]}

            return op

        return await run(request, "POST", f"mailbox/{agent_id}/pull", build)

    @router.post("/leases/{lease_id}/ack")
    async def ack(lease_id: str, request: Request) -> Any:
        def build(_b: Dict[str, Any]) -> Operation:
            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                env = edge.ack(p, lease_id)
                return 200, {"acked": env.message_id, "sequence": env.sequence}

            return op

        return await run(request, "POST", f"leases/{lease_id}/ack", build)

    @router.post("/leases/{lease_id}/nack")
    async def nack(lease_id: str, request: Request) -> Any:
        def build(body: Dict[str, Any]) -> Operation:
            try:
                delay = None if body.get("delay_s") is None else float(body["delay_s"])
            except (TypeError, ValueError) as exc:
                raise EdgeError(str(exc)) from exc
            error = str(body.get("error", ""))[:512]
            retry = bool(body.get("retry", True))
            poison = bool(body.get("poison", False))

            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                letter = edge.nack(p, lease_id, error=error, retry=retry, poison=poison, delay_s=delay)
                return 200, {"dead_lettered": letter is not None, "dead_letter": None if letter is None else letter.as_dict()}

            return op

        return await run(request, "POST", f"leases/{lease_id}/nack", build)

    @router.post("/leases/{lease_id}/extend")
    async def extend(lease_id: str, request: Request) -> Any:
        def build(body: Dict[str, Any]) -> Operation:
            try:
                lease_s = None if body.get("lease_s") is None else float(body["lease_s"])
            except (TypeError, ValueError) as exc:
                raise EdgeError(str(exc)) from exc

            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                return 200, {"lease_id": lease_id, "lease_expires_at": edge.extend(p, lease_id, lease_s=lease_s)}

            return op

        return await run(request, "POST", f"leases/{lease_id}/extend", build)

    @router.get("/routes/resolve")
    async def resolve(request: Request, capability: str, lane: Optional[str] = None) -> Any:
        def build(_b: Dict[str, Any]) -> Operation:
            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                d = edge.resolve(p, capability, lane=lane)
                return (200 if d.routed else 404 if d.outcome.value == "no_candidates" else 503), d.as_dict()

            return op

        return await run(request, "GET", "routes/resolve", build)

    @router.get("/dlq")
    async def dlq(request: Request, recipient: Optional[str] = None, reason: Optional[str] = None, limit: int = 100) -> Any:
        def build(_b: Dict[str, Any]) -> Operation:
            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                letters = edge.dead_letters(p, recipient=recipient, reason=reason, limit=limit)
                return 200, {"dead_letters": [dl.as_dict() for dl in letters], "stats": edge.bus.dlq.stats()}

            return op

        return await run(request, "GET", "dlq", build)

    @router.post("/dlq/{message_id}/replay")
    async def replay(message_id: str, request: Request) -> Any:
        def build(_b: Dict[str, Any]) -> Operation:
            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                return 200, edge.replay(p, message_id).as_dict()

            return op

        return await run(request, "POST", f"dlq/{message_id}/replay", build)

    @router.post("/delegations")
    async def delegate(request: Request) -> Any:
        def build(body: Dict[str, Any]) -> Operation:
            delegate_id = body.get("delegate")
            scopes = body.get("scopes")
            if not isinstance(delegate_id, str) or not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
                raise EdgeError("delegate (str) and scopes (list[str]) are required")
            try:
                ttl = None if body.get("ttl_s") is None else float(body["ttl_s"])
            except (TypeError, ValueError) as exc:
                raise EdgeError(str(exc)) from exc

            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                try:
                    token = edge.authority.delegate(p, delegate_id, scopes, ttl_s=ttl)
                except ValueError as exc:
                    raise EdgeError(str(exc)) from exc
                return 201, {"token": token, "delegate": delegate_id, "on_behalf_of": (p.chain or (p.agent_id,))[0]}

            return op

        return await run(request, "POST", "delegations", build)

    @router.get("/stats")
    async def stats(request: Request) -> Any:
        def build(_b: Dict[str, Any]) -> Operation:
            def op(p: AgentPrincipal) -> Tuple[int, Any]:
                edge.authority.require(p, "dlq:read")
                return 200, {**edge.stats(), "gateway": gateway.describe()}

            return op

        return await run(request, "GET", "stats", build)

    return router


def create_agent_gateway_app(gateway: AgentGateway, *, prefix: str = "", title: str = "Skeleton Agent Edge") -> Any:
    """Standalone ASGI app (no lifespan hooks) suitable for ``app.mount(...)``."""
    from fastapi import FastAPI

    app = FastAPI(title=title, docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(build_agent_gateway_router(gateway, prefix=prefix))
    app.state.agent_gateway = gateway
    return app


__all__ = [
    "AgentGateway",
    "CANONICAL_ROOT",
    "DEFAULT_PREFIX",
    "GATE_ORDER",
    "GatewayResult",
    "build_agent_gateway_router",
    "create_agent_gateway_app",
    "default_edge_policies",
    "default_edge_routes",
]
