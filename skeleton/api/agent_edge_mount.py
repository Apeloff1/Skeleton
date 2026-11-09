"""Fold the agent-edge gateway into ``create_app`` behind ``install_gate``.

#3622 follow-up. TD ruling: ``create_app`` is the only HTTP entry, so the
agent-edge gateway (``skeleton.gate_plane.agent_edge.gateway``) no longer
gets its own ASGI app factory and auth. Its routes are included into the app
built by ``create_app`` and run behind the same gate stack as every other
route::

    HeaderBound -> RequestSeal -> WriteAdmit -> BodyBound -> WORM -> Auth -> PolicyGate
        -> agent-edge router -> AgentGateway.handle (S2S token + AgentAuthority ->
           backpressure -> pipeline)

So a caller needs both a valid ``x-gf-seal`` (the main gate) and an agent
service token (the edge's own delegation-aware authority). The edge prefix is
chartered as the ``agents`` gate domain on the app's live ``GatePolicy``; it is
never an open route.

Two ways in, both extend-only (``api/server.py`` lifespan is untouched):

* ``register_agent_gateway(gw)`` before ``create_app()``; ``create_app`` calls
  :func:`install_registered_agent_edge`, which is a no-op when nothing is
  registered.
* ``install_agent_edge(create_app(), gw)`` after the fact. Starlette builds
  the middleware stack lazily, so routes added before the first request are
  still wrapped by the gate.
"""

from __future__ import annotations

import threading
from typing import Any, Optional, Tuple

from skeleton.api.middleware import GatePolicy, install_gate
from skeleton.gate_plane.agent_edge.gateway import (
    DEFAULT_PREFIX,
    AgentGateway,
    build_agent_gateway_router,
    create_agent_gateway_app,
)

AGENT_EDGE_DOMAIN = "agents"

_lock = threading.Lock()
_registered: Optional[Tuple[AgentGateway, str]] = None


class AgentEdgeMountError(RuntimeError):
    """The gateway cannot be folded into this app safely."""


def _live_policy(app: Any, policy: Optional[GatePolicy]) -> GatePolicy:
    if policy is not None:
        return policy
    state = getattr(app, "state", None)
    found = getattr(state, "gate_policy", None) if state is not None else None
    if not isinstance(found, GatePolicy):
        raise AgentEdgeMountError(
            "install_agent_edge needs an app whose gate stack was installed with "
            "install_gate (create_app does this); refusing to mount ungated routes"
        )
    return found


def install_agent_edge(
    app: Any,
    gateway: AgentGateway,
    *,
    prefix: str = DEFAULT_PREFIX,
    policy: Optional[GatePolicy] = None,
) -> Any:
    """Mount ``gateway``'s routes into ``app`` behind its ``install_gate`` stack.

    ``app`` is normally the one returned by ``create_app()``. ``policy``
    defaults to the live ``GatePolicy`` that ``install_gate`` recorded on
    ``app.state.gate_policy``; the edge prefix is chartered on it as the
    ``agents`` domain so PolicyGate admits (rather than 404-seals) the routes
    while RequestSeal and Auth still apply. Returns ``app``.
    """
    if not isinstance(gateway, AgentGateway):
        raise TypeError("gateway must be an AgentGateway")
    if not isinstance(prefix, str) or not prefix.startswith("/") or not prefix.rstrip("/"):
        raise AgentEdgeMountError("agent-edge prefix must be a non-root absolute path")
    prefix = prefix.rstrip("/")
    gate_policy = _live_policy(app, policy)
    if gate_policy.is_open_route(prefix):
        raise AgentEdgeMountError(f"agent-edge prefix {prefix!r} is an open (unsealed) route")
    if getattr(app.state, "agent_gateway", None) is not None:
        raise AgentEdgeMountError("an agent-edge gateway is already installed on this app")
    try:
        gate_policy.register_domain(prefix, AGENT_EDGE_DOMAIN)
    except ValueError as exc:
        raise AgentEdgeMountError(str(exc)) from exc
    app.include_router(build_agent_gateway_router(gateway, prefix=prefix))
    app.state.agent_gateway = gateway
    app.state.agent_edge_prefix = prefix
    return app


def register_agent_gateway(gateway: AgentGateway, *, prefix: str = DEFAULT_PREFIX) -> None:
    """Register the gateway that the next ``create_app()`` folds in."""
    global _registered
    if not isinstance(gateway, AgentGateway):
        raise TypeError("gateway must be an AgentGateway")
    with _lock:
        _registered = (gateway, prefix)


def clear_registered_agent_gateway() -> None:
    global _registered
    with _lock:
        _registered = None


def registered_agent_gateway() -> Optional[AgentGateway]:
    with _lock:
        return None if _registered is None else _registered[0]


def install_registered_agent_edge(app: Any) -> bool:
    """``create_app`` hook: fold the registered gateway in, if any."""
    with _lock:
        registered = _registered
    if registered is None:
        return False
    gateway, prefix = registered
    install_agent_edge(app, gateway, prefix=prefix)
    return True


class _StandaloneEdgePolicy(GatePolicy):
    """Gate policy for the deprecated standalone app: every path is ``agents``.

    The standalone app serves only the edge, and Starlette keeps the full
    path (``/edge/...``) when it is mounted, so the domain cannot be keyed on
    a prefix. Nothing is open: health needs a seal too.
    """

    def __init__(self) -> None:
        super().__init__(open_prefixes=(), domains=())

    def required_domain(self, path: str) -> Optional[str]:
        return AGENT_EDGE_DOMAIN


def gate_standalone_agent_edge(app: Any) -> Any:
    """``gate_installer`` for ``create_agent_gateway_app``: route its auth through install_gate."""
    return install_gate(app, policy=_StandaloneEdgePolicy())


def create_gated_agent_gateway_app(gateway: AgentGateway, *, prefix: str = "") -> Any:
    """Deprecated-path helper: the legacy standalone app, but behind ``install_gate``.

    Prefer ``install_agent_edge(create_app(), gateway)``. This exists so hosts
    that still ``app.mount(...)`` a standalone edge get the gate stack.
    """
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return create_agent_gateway_app(gateway, prefix=prefix, gate_installer=gate_standalone_agent_edge)


__all__ = [
    "AGENT_EDGE_DOMAIN",
    "AgentEdgeMountError",
    "clear_registered_agent_gateway",
    "create_gated_agent_gateway_app",
    "gate_standalone_agent_edge",
    "install_agent_edge",
    "install_registered_agent_edge",
    "register_agent_gateway",
    "registered_agent_gateway",
]
