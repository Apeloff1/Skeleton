"""Model tokenizer source check: last_inspection, no real-model authority."""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate, required_keys,
)
DOMAIN = "tokenizer_identity"
STAGE = "last_inspection"
PREDICATE = "fresh"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)

def check(observation: object) -> StageVerdict:
    """Deny untyped, incomplete or inconsistent observations."""
    return evaluate_predicate(PREDICATE, STAGE, observation)

def contract() -> dict[str, object]:
    """Describe exact schema without granting model load or release rights."""
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
