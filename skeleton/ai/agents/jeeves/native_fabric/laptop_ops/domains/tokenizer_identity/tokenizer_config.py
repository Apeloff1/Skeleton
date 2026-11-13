"""tokenizer_identity.tokenizer_config: specific first-laptop readiness observation 3/8.

Bind immutable tokenization, vocabulary, model pairing and source identity before real native use.
No client statement may authorize GGUF loading, tool effects or license rights.
Only the existing installed model and native supervisor possess runtime authority.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict
from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate,
    required_keys,
)

DOMAIN = "tokenizer_identity"
STAGE = "tokenizer_config"
PREDICATE = "sha_equal"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(observation: object) -> StageVerdict:
    """Enforce the strict local evidence schema without side effects."""
    return evaluate_predicate(PREDICATE, STAGE, observation)


def contract() -> dict[str, object]:
    """Publish auditable input requirements, never a physical device verdict."""
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
