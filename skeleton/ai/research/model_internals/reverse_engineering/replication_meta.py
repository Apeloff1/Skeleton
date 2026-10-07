"""Inverse-variance style meta-summary across independent replication groups."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ReplicationStudy:
    study_id: str
    claim_digest: str
    effect: float
    standard_error: float
    independent_actor: str

    def __post_init__(self) -> None:
        if not self.study_id or not self.independent_actor:
            raise ReverseEngineeringError("replication study identity is required")
        if not is_sha256_digest(self.claim_digest):
            raise ReverseEngineeringError("claim_digest must be sha256 hex")
        if not isfinite(self.effect):
            raise ReverseEngineeringError("replication effect must be finite")
        if not isfinite(self.standard_error) or self.standard_error <= 0.0:
            raise ReverseEngineeringError("standard_error must be finite and positive")


@dataclass(frozen=True)
class ReplicationMetaReport:
    study_count: int
    independent_actor_count: int
    pooled_effect: float
    pooled_standard_error: float
    heterogeneity_q: float
    sign_agreement_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "study_count": self.study_count,
            "independent_actor_count": self.independent_actor_count,
            "pooled_effect": self.pooled_effect,
            "pooled_standard_error": self.pooled_standard_error,
            "heterogeneity_q": self.heterogeneity_q,
            "sign_agreement_ratio": self.sign_agreement_ratio,
            "digest": self.digest,
        }


def analyze_replication_meta(
    studies: Sequence[ReplicationStudy],
) -> ReplicationMetaReport:
    if not studies:
        raise ReverseEngineeringError("replication meta-analysis requires studies")
    digests = {study.claim_digest for study in studies}
    if len(digests) != 1:
        raise ReverseEngineeringError("replication studies must share claim_digest")
    ids = [study.study_id for study in studies]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("replication study ids must be unique")
    weights = [1.0 / (study.standard_error ** 2) for study in studies]
    weight_total = sum(weights)
    pooled = sum(weight * study.effect for weight, study in zip(weights, studies)) / weight_total
    pooled_se = sqrt(1.0 / weight_total)
    q = sum(
        weight * (study.effect - pooled) ** 2
        for weight, study in zip(weights, studies)
    )
    pooled_sign = 0 if pooled == 0.0 else (1 if pooled > 0.0 else -1)
    agreement = sum(
        (0 if study.effect == 0.0 else (1 if study.effect > 0.0 else -1)) == pooled_sign
        for study in studies
    ) / len(studies)
    payload = {
        "claim_digest": next(iter(digests)),
        "studies": [
            {
                "study_id": study.study_id,
                "effect": study.effect,
                "standard_error": study.standard_error,
                "independent_actor": study.independent_actor,
            }
            for study in sorted(studies, key=lambda value: value.study_id)
        ],
    }
    return ReplicationMetaReport(
        study_count=len(studies),
        independent_actor_count=len({study.independent_actor for study in studies}),
        pooled_effect=pooled,
        pooled_standard_error=pooled_se,
        heterogeneity_q=q,
        sign_agreement_ratio=agreement,
        digest=stable_digest(payload),
    )
