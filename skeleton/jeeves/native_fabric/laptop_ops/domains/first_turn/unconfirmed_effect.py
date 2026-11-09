"""first_turn.unconfirmed_effect: named source inspection 8/8.

Check a model-bound first Jeeves turn has enough shared context for prompt and output. Self-reported input is not independent source-rights,
hardware inference, device, native-replay or release qualification.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as predicate, required_keys,
)

DOMAIN = "first_turn"
STAGE = "unconfirmed_effect"
PREDICATE = "false"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(evidence: object) -> StageVerdict:
    """Deny undeclared fields and ambiguous scalar representations."""
    return predicate(PREDICATE, STAGE, evidence)


def contract() -> dict[str, object]:
    """Auditable source input shape, never actual installed model approval."""
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
