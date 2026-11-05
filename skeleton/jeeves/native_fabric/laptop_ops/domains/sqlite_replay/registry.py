"""Reconcile committed native output and read-only SQLite replay without duplicate inference.

Read-only source checks that require eight mutually consistent stages.
Cannot authorize runtime work, read source data or grant model rights.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    committed_output,
    replayed_output,
    scope_owner,
    model_digest,
    journal_state,
    replay_limit,
    sequence,
    no_second_generation,
)

DOMAIN = "sqlite_replay"
STAGES = ("committed_output", "replayed_output", "scope_owner", "model_digest", "journal_state", "replay_limit", "sequence", "no_second_generation",)
STAGE_TYPES = (("committed_output", "sha_equal"), ("replayed_output", "sha_equal"), ("scope_owner", "same_owner"), ("model_digest", "sha_equal"), ("journal_state", "true"), ("replay_limit", "bounded"), ("sequence", "monotonic"), ("no_second_generation", "false"),)
HANDLERS = (committed_output, replayed_output, scope_owner, model_digest, journal_state, replay_limit, sequence, no_second_generation,)


def evaluate(e: object):
    """Reject unknown stages and aggregate source-claim inconsistencies."""
    if type(e) is not dict or set(e) != set(STAGES):
        raise LaptopGateHold("incomplete sqlite_replay source evidence")
    checks = tuple(module.check(e[label])
                   for label, module in zip(STAGES, HANDLERS))
    if len(checks) != 8 or len({v.stage for v in checks}) != 8:
        raise LaptopGateHold("incomplete sqlite_replay typed safeguard set")
    # Retain individual negative verdicts; evaluate cross-stage data only
    # after the strict input shape and local bounds have all passed.
    if all(c.accepted for c in checks) and not (e["committed_output"]["observed_sha256"] == e["replayed_output"]["observed_sha256"]):
        raise LaptopGateHold("contradictory sqlite_replay source observations")
    return checks


def contracts() -> tuple[dict[str, object], ...]:
    """Eight fixed stage contracts; no source-only release permission."""
    return tuple(module.contract() for module in HANDLERS)


__all__ = ["STAGES", "STAGE_TYPES", "evaluate", "contracts"]
