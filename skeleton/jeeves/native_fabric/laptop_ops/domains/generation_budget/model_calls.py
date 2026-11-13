"""generation_budget.model_calls: named observation 1/8 for operational Jeeves.

Reserve finite native call and output token budgets as one aggregate source contract. This does not establish trusted device/rights provenance.
Only the already installed and verified native stack authorizes execution.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate, required_keys,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict

DOMAIN = "generation_budget"
STAGE = "model_calls"
PREDICATE = "bounded"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(evidence: object) -> StageVerdict:
    """Strict evidence shape and predicate, without implicit type conversion."""
    return evaluate_predicate(PREDICATE, STAGE, evidence)


def contract() -> dict[str, object]:
    """Machine-readable source-only contract, not authority or a model grant."""
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
