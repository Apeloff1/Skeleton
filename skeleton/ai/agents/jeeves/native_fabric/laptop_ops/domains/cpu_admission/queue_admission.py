"""Jeeves source-check queue_admission, CPU diagnostic 5 of 8.

This observation cannot claim a real CPU measurement; canonical
model startup must independently constrain threads and execution.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate, required_keys,
)

DOMAIN = "cpu_admission"
STAGE = "queue_admission"
PREDICATE = "capacity"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(observation: object) -> StageVerdict:
    """Evaluate exact bounded inputs; no implicit casts or fallback."""
    return evaluate_predicate(PREDICATE, STAGE, observation)


def contract() -> dict[str, object]:
    """Publish read-only source inputs, not native-device authority."""
    return {
        "schema": "jeeves.laptop_ops.stage_contract.v1",
        "domain": DOMAIN,
        "stage": STAGE,
        "predicate": PREDICATE,
        "required_fields": list(REQUIRED_FIELDS),
        "operator_proof_is_insufficient_for_activation": True,
        "device_qualified": False,
    }


__all__ = ["check", "contract", "DOMAIN", "STAGE"]
