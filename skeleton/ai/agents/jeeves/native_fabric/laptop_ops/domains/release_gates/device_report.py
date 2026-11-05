"""Release gate observation 6/8: device_report, source diagnostic only.

This pure predicate checks typed input, not real GitHub jobs, external
source rights, installed model bytes or Windows/GPU device qualification.
No stage result can certify a release from an operator self-report.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate, required_keys,
)

DOMAIN = "release_gates"
STAGE = "device_report"
PREDICATE = "true"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(evidence: object) -> StageVerdict:
    """Reject extra, missing, ambiguous or type-coerced evidence."""
    return evaluate_predicate(PREDICATE, STAGE, evidence)


def contract() -> dict[str, object]:
    """A non-authoritative policy input declaration, never release proof."""
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
