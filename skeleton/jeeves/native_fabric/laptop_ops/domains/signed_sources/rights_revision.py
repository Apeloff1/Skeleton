"""signed_sources.rights_revision: source-bounded laptop operational observation 6 of 8.

Keep signed offline source manifests, operator approval and revocation in a single scope.
This non-authoritative input cannot activate a model or grant file rights.
The actual installed GGUF and durable supervisor remain canonical.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.predicates import (
    evaluate as evaluate_predicate,
    required_keys,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import StageVerdict

DOMAIN = "signed_sources"
STAGE = "rights_revision"
PREDICATE = "monotonic"
REQUIRED_FIELDS = required_keys(PREDICATE, STAGE)


def check(observation: object) -> StageVerdict:
    """Reject unknown keys and type confusion before returning typed evidence."""
    return evaluate_predicate(PREDICATE, STAGE, observation)


def contract() -> dict[str, object]:
    """The exact diagnostic schema, without a source/rights/device grant."""
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
