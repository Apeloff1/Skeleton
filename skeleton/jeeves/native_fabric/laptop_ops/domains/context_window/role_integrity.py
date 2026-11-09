"""role_integrity - context-stage 4/8 for the approved local-first Jeeves path.

The observer is non-authoritative. Actual model admission and token counts
remain governed by source-bound native activation and its runtime.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate,
    required_keys,
)

DOMAIN = "context_window"
STAGE = "role_integrity"
PREDICATE = "sha_equal"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(observation: object) -> StageVerdict:
    """Require strict observable evidence without introducing side effects."""
    return evaluate_predicate(PREDICATE, STAGE, observation)


def contract() -> dict[str, object]:
    """Machine-readable stage inputs without permission or device claims."""
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
