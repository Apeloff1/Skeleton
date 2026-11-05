"""Fence cancelled native work against stale operation/lease generations.

A source-level report cannot unlock an uncertain durable native call,
resume a tool step or replace SQLite revision-CAS reconciliation.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    cancel_epoch,
    lease_epoch,
    active_run,
    owner_scope,
    cancel_deadline,
    worker_count,
    request_digest,
    implicit_retry,
)

DOMAIN = "cancellation"
STAGES = ("cancel_epoch", "lease_epoch", "active_run", "owner_scope", "cancel_deadline", "worker_count", "request_digest", "implicit_retry",)
STAGE_TYPES = (("cancel_epoch", "monotonic"), ("lease_epoch", "monotonic"), ("active_run", "true"), ("owner_scope", "same_owner"), ("cancel_deadline", "bounded"), ("worker_count", "capacity"), ("request_digest", "sha_equal"), ("implicit_retry", "false"),)
HANDLERS = (cancel_epoch, lease_epoch, active_run, owner_scope, cancel_deadline, worker_count, request_digest, implicit_retry,)


def evaluate(e: object):
    """All eight stages plus source-coherent restart/cancellation fence."""
    if type(e) is not dict or set(e) != set(STAGES):
        raise LaptopGateHold("missing or extra cancellation source evidence")
    result = tuple(module.check(e[name])
                   for name,module in zip(STAGES,HANDLERS))
    if len(result) != 8 or len({row.stage for row in result}) != 8:
        raise LaptopGateHold("incomplete cancellation source roster")
    if all(row.accepted for row in result) and not (e["cancel_epoch"]["current"] >= e["lease_epoch"]["current"]):
        raise LaptopGateHold("stale or conflicting cancellation source observation")
    return result


def contracts() -> tuple[dict[str, object], ...]:
    return tuple(handler.contract() for handler in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
