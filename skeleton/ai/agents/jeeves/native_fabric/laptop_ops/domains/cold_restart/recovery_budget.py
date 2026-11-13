"""cold_restart: recovery_budget (6/8), immutable first-laptop source observation.

Cross-check cold-reopen checkpoint identity against persisted source digest and in-flight holds. Only the canonical native supervisor, SQLite and explicit
operator reconciliation may determine whether actual work can proceed.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate, required_keys,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict

DOMAIN = "cold_restart"
STAGE = "recovery_budget"
PREDICATE = "bounded"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(value: object) -> StageVerdict:
    """No extra fields, implicit casting, or source-asserted permissions."""
    return evaluate_predicate(PREDICATE, STAGE, value)


def contract() -> dict[str, object]:
    """Stage evidence shape, explicitly not a native-execution permission."""
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
