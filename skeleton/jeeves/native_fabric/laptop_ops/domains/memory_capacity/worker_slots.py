"""First-laptop worker_slots safeguard: observable diagnostics, never activation rights."""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.predicates import evaluate as predicate
from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
DOMAIN = "memory_capacity"
STAGE = "worker_slots"
PREDICATE = "capacity"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)

def check(observation: object) -> StageVerdict:
    """Fail closed on unrecognized, type-confused, missing or mismatched fields."""
    return predicate(PREDICATE, STAGE, observation)

def contract() -> dict[str, object]:
    """Read-only observable evidence contract, never a license or device proof."""
    return {"schema": "jeeves.laptop_ops.stage_contract.v1", "domain": DOMAIN,
            "stage": STAGE, "predicate": PREDICATE,
            "required_fields": list(REQUIRED_FIELDS),
            "operator_proof_is_insufficient_for_activation": True,
            "device_qualified": False}
