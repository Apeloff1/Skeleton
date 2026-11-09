"""Read-only CPU thread/queue admission consistency checks.

A healthy individual thread reservation and queue reservation can still
oversubscribe the same CPU. Preserve that aggregate invariant without
granting operator source assertions authority over native workers.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    thread_capacity,
    cpu_utilization,
    worker_lease,
    affinity_owner,
    queue_admission,
    worker_generation,
    cpu_probe,
    oversubscription,
)

DOMAIN = "cpu_admission"
STAGES = ("thread_capacity", "cpu_utilization", "worker_lease", "affinity_owner", "queue_admission", "worker_generation", "cpu_probe", "oversubscription",)
STAGE_TYPES = (("thread_capacity", "capacity"), ("cpu_utilization", "bounded"), ("worker_lease", "true"), ("affinity_owner", "same_owner"), ("queue_admission", "capacity"), ("worker_generation", "monotonic"), ("cpu_probe", "fresh"), ("oversubscription", "false"),)
HANDLERS = (thread_capacity, cpu_utilization, worker_lease, affinity_owner, queue_admission, worker_generation, cpu_probe, oversubscription,)


def evaluate(evidence: object):
    """Require eight exact independent predicates and no total oversubscription."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("incomplete or unexpected CPU admission stage")
    verdicts = tuple(module.check(evidence[stage])
                     for stage, module in zip(STAGES, HANDLERS))
    if len(verdicts) != len(STAGES):
        raise LaptopGateHold("CPU safeguard evaluator incomplete")
    if all(row.accepted for row in verdicts):
        available = evidence["thread_capacity"]["available"]
        admitted = (evidence["thread_capacity"]["reserved"]
                    + evidence["queue_admission"]["reserved"])
        if admitted > available:
            raise LaptopGateHold("CPU queue and thread reservations oversubscribe host")
    return verdicts


def contracts() -> tuple[dict[str, object], ...]:
    """Every required observation with an explicit non-attestation flag."""
    return tuple(module.contract() for module in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
