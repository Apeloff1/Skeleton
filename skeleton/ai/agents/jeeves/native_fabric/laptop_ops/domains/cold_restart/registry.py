"""Cross-check cold-reopen checkpoint identity against persisted source digest and in-flight holds.

A source-level report cannot unlock an uncertain durable native call,
resume a tool step or replace SQLite revision-CAS reconciliation.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    checkpoint_digest,
    loaded_checkpoint,
    scope_owner,
    model_tokenizer_pair,
    sqlite_bound,
    recovery_budget,
    journal_revision,
    unresolved_inflight,
)

DOMAIN = "cold_restart"
STAGES = ("checkpoint_digest", "loaded_checkpoint", "scope_owner", "model_tokenizer_pair", "sqlite_bound", "recovery_budget", "journal_revision", "unresolved_inflight",)
STAGE_TYPES = (("checkpoint_digest", "sha_equal"), ("loaded_checkpoint", "sha_equal"), ("scope_owner", "same_owner"), ("model_tokenizer_pair", "sha_equal"), ("sqlite_bound", "true"), ("recovery_budget", "bounded"), ("journal_revision", "monotonic"), ("unresolved_inflight", "false"),)
HANDLERS = (checkpoint_digest, loaded_checkpoint, scope_owner, model_tokenizer_pair, sqlite_bound, recovery_budget, journal_revision, unresolved_inflight,)


def evaluate(e: object):
    """All eight stages plus source-coherent restart/cancellation fence."""
    if type(e) is not dict or set(e) != set(STAGES):
        raise LaptopGateHold("missing or extra cold_restart source evidence")
    result = tuple(module.check(e[name])
                   for name,module in zip(STAGES,HANDLERS))
    if len(result) != 8 or len({row.stage for row in result}) != 8:
        raise LaptopGateHold("incomplete cold_restart source roster")
    if all(row.accepted for row in result) and not (e["checkpoint_digest"]["observed_sha256"] == e["loaded_checkpoint"]["observed_sha256"]):
        raise LaptopGateHold("stale or conflicting cold_restart source observation")
    return result


def contracts() -> tuple[dict[str, object], ...]:
    return tuple(handler.contract() for handler in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
