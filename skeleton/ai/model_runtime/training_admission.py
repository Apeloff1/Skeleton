"""Governed FLGB-07 candidate-weight admission into the native FLGB-02 runtime.

This bridge does not apply weights. Training owns mutation of the candidate model;
this module only permits runtime re-admission after the candidate and independent
promotion evidence prove that the mutation is the exact governed artifact.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac

from skeleton.ai.training.flgb_training_runtime import (
    CandidateWeights,
    PromotionEvidence,
)

from .native_llm_runtime import NativeLLMRuntime
from .runtime_checkpoint import portable_model_snapshot, snapshot_digest
from .runtime_contracts import RuntimeContractError


@dataclass(frozen=True)
class TrainingAdmissionReceipt:
    candidate_digest: str
    promotion_evidence_digest: str
    prior_model_digest: str
    admitted_model_digest: str
    model_identity_digest: str

    def __post_init__(self) -> None:
        for name in (
            "candidate_digest",
            "promotion_evidence_digest",
            "prior_model_digest",
            "admitted_model_digest",
            "model_identity_digest",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(
                ch not in "0123456789abcdef" for ch in value
            ):
                raise RuntimeContractError(f"invalid {name}")


def admit_promoted_candidate(
    runtime: NativeLLMRuntime,
    candidate: CandidateWeights,
    evidence: PromotionEvidence,
) -> TrainingAdmissionReceipt:
    """Atomically re-admit an already-mutated model only with exact promotion evidence."""
    if not isinstance(runtime, NativeLLMRuntime):
        raise RuntimeContractError("NativeLLMRuntime required")
    if not isinstance(candidate, CandidateWeights):
        raise RuntimeContractError("CandidateWeights required")
    if not isinstance(evidence, PromotionEvidence):
        raise RuntimeContractError("PromotionEvidence required")
    if candidate.status != "promoted":
        raise RuntimeContractError("candidate is not promoted")
    if not evidence.qualified:
        raise RuntimeContractError("promotion evidence is not qualified")
    if not hmac.compare_digest(evidence.candidate_digest, candidate.digest):
        raise RuntimeContractError("promotion evidence candidate mismatch")

    prior = runtime.model_digest
    if not hmac.compare_digest(candidate.base_model_digest, prior):
        raise RuntimeContractError("candidate base model does not match admitted runtime")

    observed = snapshot_digest(portable_model_snapshot(runtime.model))
    if not hmac.compare_digest(candidate.weights_digest, observed):
        raise RuntimeContractError("candidate weights do not match mutated runtime model")
    if hmac.compare_digest(observed, prior):
        raise RuntimeContractError("candidate does not change admitted weights")

    admitted = runtime.refresh_model_identity()
    if not hmac.compare_digest(admitted, candidate.weights_digest):
        raise RuntimeContractError("runtime admitted unexpected candidate weights")

    return TrainingAdmissionReceipt(
        candidate_digest=candidate.digest,
        promotion_evidence_digest=evidence.digest,
        prior_model_digest=prior,
        admitted_model_digest=admitted,
        model_identity_digest=runtime.model_identity.identity_digest,
    )


__all__ = ["TrainingAdmissionReceipt", "admit_promoted_candidate"]
