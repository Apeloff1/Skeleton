"""Agent/swarm edge: inter-agent bus, routing, agent auth and the API gateway.

Layered on the Pack F gate plane (s2s tokens + authz, backpressure,
pipeline/breakers). Pure library code: hosts opt in by including
:func:`build_agent_gateway_router` or mounting :func:`create_agent_gateway_app`;
``skeleton/api/server.py`` and its lifespan are never modified. Internal
Systems' swarm is consumed through :mod:`.swarm_adapter` only.
"""

from __future__ import annotations

from skeleton.gate_plane.agent_edge.auth import (
    EDGE_AUDIENCE,
    SCOPE_DELEGATE,
    SCOPE_DLQ_ADMIN,
    SCOPE_DLQ_READ,
    SCOPE_RECV,
    SCOPE_RESOLVE,
    AgentAuthError,
    AgentAuthority,
    AgentPrincipal,
    AuthFailure,
    ScopeCeiling,
    cap_granted,
    send_scope,
)
from skeleton.gate_plane.agent_edge.bus import (
    AgentBus,
    BusFull,
    Delivery,
    PoisonMessage,
    PublishResult,
    PublishStatus,
    StaleLease,
    UnknownLease,
    backoff_delay,
)
from skeleton.gate_plane.agent_edge.dedup import DedupWindow
from skeleton.gate_plane.agent_edge.dlq import DeadLetter, DeadLetterQueue, DeadLetterReason
from skeleton.gate_plane.agent_edge.edge import (
    AgentEdge,
    EdgeError,
    LeaseConflict,
    LeaseNotFound,
    NoRoute,
    RouteUnavailable,
    SendOutcome,
    SendRequest,
)
from skeleton.gate_plane.agent_edge.envelope import Envelope, EnvelopeError
from skeleton.gate_plane.agent_edge.gateway import (
    GATE_ORDER,
    AgentGateway,
    GatewayResult,
    build_agent_gateway_router,
    create_agent_gateway_app,
    default_edge_policies,
    default_edge_routes,
)
from skeleton.gate_plane.agent_edge.routing import (
    AgentEndpoint,
    AgentRegistry,
    AgentRouter,
    RouteDecision,
    RouteOutcome,
    RoutingError,
)
from skeleton.gate_plane.agent_edge.swarm_adapter import (
    CallableSwarmDirectory,
    ModuleSwarmDirectory,
    StaticSwarmDirectory,
    SwarmRegistryAdapter,
)

__all__ = [
    "AgentAuthError",
    "AgentAuthority",
    "AgentBus",
    "AgentEdge",
    "AgentEndpoint",
    "AgentGateway",
    "AgentPrincipal",
    "AgentRegistry",
    "AgentRouter",
    "AuthFailure",
    "BusFull",
    "CallableSwarmDirectory",
    "DeadLetter",
    "DeadLetterQueue",
    "DeadLetterReason",
    "DedupWindow",
    "Delivery",
    "EDGE_AUDIENCE",
    "EdgeError",
    "Envelope",
    "EnvelopeError",
    "GATE_ORDER",
    "GatewayResult",
    "LeaseConflict",
    "LeaseNotFound",
    "ModuleSwarmDirectory",
    "NoRoute",
    "PoisonMessage",
    "PublishResult",
    "PublishStatus",
    "RouteDecision",
    "RouteOutcome",
    "RouteUnavailable",
    "RoutingError",
    "SCOPE_DELEGATE",
    "SCOPE_DLQ_ADMIN",
    "SCOPE_DLQ_READ",
    "SCOPE_RECV",
    "SCOPE_RESOLVE",
    "ScopeCeiling",
    "SendOutcome",
    "SendRequest",
    "StaleLease",
    "StaticSwarmDirectory",
    "SwarmRegistryAdapter",
    "UnknownLease",
    "backoff_delay",
    "build_agent_gateway_router",
    "cap_granted",
    "create_agent_gateway_app",
    "default_edge_policies",
    "default_edge_routes",
    "send_scope",
]
