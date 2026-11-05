"""Composition of all eight bootstrap first-laptop safeguards."""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import source_approval
from . import model_archive
from . import tokenizer_approval
from . import state_privacy
from . import operator_grant
from . import memory_reservation
from . import startup_deadline
from . import sqlite_supervisor

DOMAIN = "bootstrap"
STAGES = ("source_approval", "model_archive", "tokenizer_approval", "state_privacy", "operator_grant", "memory_reservation", "startup_deadline", "sqlite_supervisor",)
STAGE_TYPES = (("source_approval", "true"), ("model_archive", "sha_equal"), ("tokenizer_approval", "sha_equal"), ("state_privacy", "true"), ("operator_grant", "true"), ("memory_reservation", "capacity"), ("startup_deadline", "bounded"), ("sqlite_supervisor", "true"),)
HANDLERS = (source_approval, model_archive, tokenizer_approval, state_privacy, operator_grant, memory_reservation, startup_deadline, sqlite_supervisor,)


def evaluate(evidence: object):
    """A partial domain never gains a positive verdict."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("missing or unknown bootstrap evidence stage")
    results = tuple(handler.check(evidence[stage])
                    for stage, handler in zip(STAGES, HANDLERS))
    if len(results) != len(STAGES):
        raise LaptopGateHold("incomplete bootstrap evaluation")
    return results


def contracts():
    return tuple(module.contract() for module in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
