"""bootstrap: operator_grant — an explicit fail-closed, source-only safeguard.

Caller-provided evidence cannot certify a physical model, device, or license.
Real authority remains the installed model, native supervisor and SQLite spine.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate, required_keys,
)

DOMAIN = "bootstrap"
STAGE = "operator_grant"
PREDICATE = "true"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(observation: object) -> StageVerdict:
    """Enforce strict typing and exact observed fields, never infer success."""
    return evaluate_predicate(PREDICATE, STAGE, observation)


def contract() -> dict[str, object]:
    """Expose auditable input requirements without exposing private payloads."""
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
