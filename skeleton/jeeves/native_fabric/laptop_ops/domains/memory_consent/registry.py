"""Preserve strict consent and per-principal bounded memory-write budgets.

All eight source-only observations are necessary. Individual predicate
success never overrides the aggregate principal-scoped budget invariant.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    memory_writes,
    consent_capacity,
    consent_owner,
    scope_digest,
    explicit_consent,
    consent_revision,
    consent_freshness,
    unauthorized_persistence,
)

DOMAIN = "memory_consent"
STAGES = ("memory_writes", "consent_capacity", "consent_owner", "scope_digest", "explicit_consent", "consent_revision", "consent_freshness", "unauthorized_persistence",)
STAGE_TYPES = (("memory_writes","bounded"), ("consent_capacity","capacity"), ("consent_owner","same_owner"), ("scope_digest","sha_equal"), ("explicit_consent","true"), ("consent_revision","monotonic"), ("consent_freshness","fresh"), ("unauthorized_persistence","false"),)
HANDLERS = (memory_writes, consent_capacity, consent_owner, scope_digest, explicit_consent, consent_revision, consent_freshness, unauthorized_persistence,)


def evaluate(e: object):
    """Reject incomplete maps and cross-stage overbooking."""
    if type(e) is not dict or set(e) != set(STAGES):
        raise LaptopGateHold("incomplete memory_consent stage inventory")
    results = tuple(module.check(e[stage])
                    for stage,module in zip(STAGES,HANDLERS))
    if len(results) != 8 or len({v.stage for v in results}) != 8:
        raise LaptopGateHold("incomplete memory_consent typed verdict")
    if all(v.accepted for v in results) and not (e["memory_writes"]["used"] <= e["consent_capacity"]["reserved"]):
        raise LaptopGateHold("contradictory memory_consent resource reservation")
    return results


def contracts() -> tuple[dict[str, object], ...]:
    """Read-only machine-checkable source contracts, not grants."""
    return tuple(module.contract() for module in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
