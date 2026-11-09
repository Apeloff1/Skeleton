"""Bind isolated GGUF sessions to the exact model, tokenizer and principal epoch.

All eight source-only observations are required. Consistent synthetic input
is never proof of a real running model, source license or physical device.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    session_model,
    active_model,
    tokenizer_digest,
    scope_owner,
    session_lease,
    live_sessions,
    revision_cas,
    session_observation,
)

DOMAIN = "native_session"
STAGES = ("session_model", "active_model", "tokenizer_digest", "scope_owner", "session_lease", "live_sessions", "revision_cas", "session_observation",)
STAGE_TYPES = (("session_model", "sha_equal"), ("active_model", "sha_equal"), ("tokenizer_digest", "sha_equal"), ("scope_owner", "same_owner"), ("session_lease", "true"), ("live_sessions", "bounded"), ("revision_cas", "monotonic"), ("session_observation", "fresh"),)
HANDLERS = (session_model, active_model, tokenizer_digest, scope_owner, session_lease, live_sessions, revision_cas, session_observation,)


def evaluate(evidence: object):
    """Fail closed on missing stages and mutually inconsistent source claims."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("missing or extra native_session source safeguard")
    observed = tuple(handler.check(evidence[stage])
                     for stage, handler in zip(STAGES, HANDLERS))
    if len(observed) != 8 or len({item.stage for item in observed}) != 8:
        raise LaptopGateHold("incomplete native_session stage inventory")
    if all(item.accepted for item in observed) and not (evidence["session_model"]["observed_sha256"] == evidence["active_model"]["observed_sha256"]):
        raise LaptopGateHold("inconsistent native_session cross-stage facts")
    return observed


def contracts() -> tuple[dict[str, object], ...]:
    """Publish stable stage input inventory, not native startup authorization."""
    return tuple(handler.contract() for handler in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
