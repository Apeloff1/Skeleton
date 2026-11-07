"""Pack F service-to-service (s2s) auth plane.

Signed HMAC service tokens backed by a kid-based key ring with rotation
overlap windows and revocation. Layered on top of the Pack B gate plane;
pure library code with injectable clocks — no host side effects and no
changes to ``skeleton/api/server.py``.
"""

from __future__ import annotations

from skeleton.gate_plane.s2s.authz import (
    AuthzReason,
    PolicyDecision,
    PolicyError,
    PolicyTable,
    Principal,
    RoutePattern,
    RoutePolicy,
    default_gate_plane_policies,
)
from skeleton.gate_plane.s2s.clock import Clock, ManualClock, SystemClock, system_clock
from skeleton.gate_plane.s2s.gate import (
    S2S_GATE_LAYER,
    S2SAuthGate,
    S2SAuthMiddleware,
    S2SDecision,
    S2SOutcome,
    extract_token,
    install_s2s_gate,
    stack_with_s2s,
)
from skeleton.gate_plane.s2s.keyring import (
    KeyRing,
    KeyRingError,
    KeyState,
    NoActiveKeyError,
    ServiceKey,
    UnknownKeyError,
)
from skeleton.gate_plane.s2s.rotation import (
    RevocationList,
    RotationPolicy,
    RotationScheduler,
    derived_secret_factory,
    random_secret_factory,
)
from skeleton.gate_plane.s2s.tokens import (
    ReplayCache,
    ServiceClaims,
    TokenError,
    TokenErrorCode,
    TokenSigner,
    TokenVerifier,
    VerifiedToken,
)

__all__ = [
    "AuthzReason",
    "PolicyDecision",
    "PolicyError",
    "PolicyTable",
    "Principal",
    "RoutePattern",
    "RoutePolicy",
    "S2SAuthGate",
    "S2SAuthMiddleware",
    "S2SDecision",
    "S2SOutcome",
    "S2S_GATE_LAYER",
    "default_gate_plane_policies",
    "extract_token",
    "install_s2s_gate",
    "stack_with_s2s",
    "Clock",
    "KeyRing",
    "KeyRingError",
    "KeyState",
    "ManualClock",
    "NoActiveKeyError",
    "ReplayCache",
    "RevocationList",
    "RotationPolicy",
    "RotationScheduler",
    "ServiceClaims",
    "ServiceKey",
    "SystemClock",
    "TokenError",
    "TokenErrorCode",
    "TokenSigner",
    "TokenVerifier",
    "UnknownKeyError",
    "VerifiedToken",
    "derived_secret_factory",
    "random_secret_factory",
    "system_clock",
]
