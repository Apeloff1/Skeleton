"""Reserve finite native call and output token budgets as one aggregate source contract.

Read-only source checks that require eight mutually consistent stages.
Cannot authorize runtime work, read source data or grant model rights.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    model_calls,
    per_call_tokens,
    total_tokens,
    context_reservation,
    wall_clock,
    session_owner,
    budget_revision,
    unapproved_overdraft,
)

DOMAIN = "generation_budget"
STAGES = ("model_calls", "per_call_tokens", "total_tokens", "context_reservation", "wall_clock", "session_owner", "budget_revision", "unapproved_overdraft",)
STAGE_TYPES = (("model_calls", "bounded"), ("per_call_tokens", "bounded"), ("total_tokens", "capacity"), ("context_reservation", "capacity"), ("wall_clock", "bounded"), ("session_owner", "same_owner"), ("budget_revision", "monotonic"), ("unapproved_overdraft", "false"),)
HANDLERS = (model_calls, per_call_tokens, total_tokens, context_reservation, wall_clock, session_owner, budget_revision, unapproved_overdraft,)


def evaluate(e: object):
    """Reject unknown stages and aggregate source-claim inconsistencies."""
    if type(e) is not dict or set(e) != set(STAGES):
        raise LaptopGateHold("incomplete generation_budget source evidence")
    checks = tuple(module.check(e[label])
                   for label, module in zip(STAGES, HANDLERS))
    if len(checks) != 8 or len({v.stage for v in checks}) != 8:
        raise LaptopGateHold("incomplete generation_budget typed safeguard set")
    # Retain individual negative verdicts; evaluate cross-stage data only
    # after the strict input shape and local bounds have all passed.
    if all(c.accepted for c in checks) and not (e["model_calls"]["used"] * e["per_call_tokens"]["used"] <= e["total_tokens"]["available"]):
        raise LaptopGateHold("contradictory generation_budget source observations")
    return checks


def contracts() -> tuple[dict[str, object], ...]:
    """Eight fixed stage contracts; no source-only release permission."""
    return tuple(module.contract() for module in HANDLERS)


__all__ = ["STAGES", "STAGE_TYPES", "evaluate", "contracts"]
