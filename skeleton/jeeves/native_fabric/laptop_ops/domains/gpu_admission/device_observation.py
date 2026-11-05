"""gpu_admission.device_observation: first-laptop source safeguard 7/8.

Bound requested local GPU offload layers by observed accelerator reservation. This is only a typed diagnostic, not a valid GGUF activation,
rights, resource telemetry, privilege or release attestation.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate, required_keys,
)

DOMAIN = "gpu_admission"
STAGE = "device_observation"
PREDICATE = "fresh"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(observation: object) -> StageVerdict:
    """Check exact schema, predicate and bounded evidence."""
    return evaluate_predicate(PREDICATE, STAGE, observation)


def contract() -> dict[str, object]:
    """Describe stage input contract without granting runtime authority."""
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
