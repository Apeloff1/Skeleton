"""pressure_recovery.unknown_override local-first diagnostic 8/8.

Block simultaneous local model and KV cache memory reservations exceeding known headroom. A source observation cannot replace canonical SQLite,
actual model identity, explicit rights or trusted host-grant enforcement.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as predicate_check, required_keys,
)

DOMAIN = "pressure_recovery"
STAGE = "unknown_override"
PREDICATE = "false"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(observation: object) -> StageVerdict:
    """No implicit conversions, extra fields or unknown predicate kinds."""
    return predicate_check(PREDICATE, STAGE, observation)


def contract() -> dict[str, object]:
    """Exact audit schema; not an execution or memory grant."""
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
