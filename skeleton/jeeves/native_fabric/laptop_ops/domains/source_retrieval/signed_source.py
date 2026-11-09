"""source_retrieval.signed_source: named observation 4/8 for operational Jeeves.

Enforce source-authorized retrieval limits before private bytes can enter Jeeves context. This does not establish trusted device/rights provenance.
Only the already installed and verified native stack authorizes execution.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate, required_keys,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict

DOMAIN = "source_retrieval"
STAGE = "signed_source"
PREDICATE = "true"
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
