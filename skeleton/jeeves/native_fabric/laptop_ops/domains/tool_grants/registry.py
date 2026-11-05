"""Keep host-controlled tool calls within explicitly granted finite per-principal quotas.

All eight source-only observations are necessary. Individual predicate
success never overrides the aggregate principal-scoped budget invariant.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    tool_calls,
    grant_capacity,
    grant_owner,
    policy_hash,
    explicit_approval,
    grant_epoch,
    grant_freshness,
    write_escalation,
)

DOMAIN = "tool_grants"
STAGES = ("tool_calls", "grant_capacity", "grant_owner", "policy_hash", "explicit_approval", "grant_epoch", "grant_freshness", "write_escalation",)
STAGE_TYPES = (("tool_calls","bounded"), ("grant_capacity","capacity"), ("grant_owner","same_owner"), ("policy_hash","sha_equal"), ("explicit_approval","true"), ("grant_epoch","monotonic"), ("grant_freshness","fresh"), ("write_escalation","false"),)
HANDLERS = (tool_calls, grant_capacity, grant_owner, policy_hash, explicit_approval, grant_epoch, grant_freshness, write_escalation,)


def evaluate(e: object):
    """Reject incomplete maps and cross-stage overbooking."""
    if type(e) is not dict or set(e) != set(STAGES):
        raise LaptopGateHold("incomplete tool_grants stage inventory")
    results = tuple(module.check(e[stage])
                    for stage,module in zip(STAGES,HANDLERS))
    if len(results) != 8 or len({v.stage for v in results}) != 8:
        raise LaptopGateHold("incomplete tool_grants typed verdict")
    if all(v.accepted for v in results) and not (e["tool_calls"]["used"] <= e["grant_capacity"]["reserved"]):
        raise LaptopGateHold("contradictory tool_grants resource reservation")
    return results


def contracts() -> tuple[dict[str, object], ...]:
    """Read-only machine-checkable source contracts, not grants."""
    return tuple(module.contract() for module in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
