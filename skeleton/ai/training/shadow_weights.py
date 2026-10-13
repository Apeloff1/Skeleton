"""Evidence-bound shadow weights: staged knowledge never silently becomes active model state.

This module is deliberately independent of model loading. A shadow candidate may
be collected and assessed repeatedly, but only a positively adjudicated
independent mirror evaluation plus a separate promotion/rollback receipt can
produce an admission permit. The native runtime must enforce that permit before
installing candidate bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from .flgb_training_runtime import (
    CandidateWeights, MirrorEvaluation, PromotionEvidence,
    TrainingContractError, digest_json, require_digest, require_id,
)


class ShadowWeightError(TrainingContractError):
    """Invalid shadow-weight evidence, identity or state transition."""


def _count(name: str, value: int, *, lower: int = 0, upper: int = 1_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ShadowWeightError(f"invalid {name}")
    return value


def _utc(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ShadowWeightError(f"{name} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ShadowWeightError(f"invalid {name}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ShadowWeightError(f"invalid {name} time zone")
    if parsed.year < 2000:
        raise ShadowWeightError(f"invalid {name} year")
    return value


@dataclass(frozen=True, slots=True)
class SourceAttestation:
    """Source provenance for a specific piece of shadow-weight evidence.

    root_id denotes an *independent origin*, not a mirror URL. Multiple pages
    syndicated from one publisher count as one independent root.
    """

    source_id: str
    root_id: str
    content_digest: str
    rights_digest: str
    observed_at: str
    quality_ppm: int
    allowed_for_training: bool
    contradiction: bool = False

    def __post_init__(self) -> None:
        require_id(self.source_id, "source_id")
        require_id(self.root_id, "root_id")
        require_digest(self.content_digest, "content_digest")
        require_digest(self.rights_digest, "rights_digest")
        _utc("observed_at", self.observed_at)
        _count("quality_ppm", self.quality_ppm)
        if not isinstance(self.allowed_for_training, bool):
            raise ShadowWeightError("training-rights flag must be boolean")
        if not isinstance(self.contradiction, bool):
            raise ShadowWeightError("contradiction flag must be boolean")

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "root_id": self.root_id,
            "content_digest": self.content_digest,
            "rights_digest": self.rights_digest,
            "observed_at": self.observed_at,
            "quality_ppm": self.quality_ppm,
            "allowed_for_training": self.allowed_for_training,
            "contradiction": self.contradiction,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class ShadowWeightPolicy:
    """Conservative bounds applied before independent sandbox evaluation."""

    minimum_independent_roots: int = 3
    minimum_quality_ppm: int = 850_000
    maximum_sources: int = 512
    require_uncontested_rights: bool = True

    def __post_init__(self) -> None:
        _count("minimum_independent_roots", self.minimum_independent_roots, lower=2, upper=100)
        _count("minimum_quality_ppm", self.minimum_quality_ppm)
        _count("maximum_sources", self.maximum_sources, lower=self.minimum_independent_roots, upper=10_000)
        if not isinstance(self.require_uncontested_rights, bool):
            raise ShadowWeightError("require_uncontested_rights must be boolean")

    @property
    def digest(self) -> str:
        return digest_json({
            "minimum_independent_roots": self.minimum_independent_roots,
            "minimum_quality_ppm": self.minimum_quality_ppm,
            "maximum_sources": self.maximum_sources,
            "require_uncontested_rights": self.require_uncontested_rights,
        })


@dataclass(frozen=True, slots=True)
class ShadowAssessment:
    candidate_digest: str
    source_manifest_digest: str
    policy_digest: str
    independent_roots: int
    accepted_sources: int
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("candidate_digest", "source_manifest_digest", "policy_digest"):
            require_digest(getattr(self, field), field)
        _count("independent_roots", self.independent_roots)
        _count("accepted_sources", self.accepted_sources)
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ShadowWeightError("reason codes must be canonical")
        for reason in self.reason_codes:
            require_id(reason, "reason_code")

    @property
    def eligible_for_mirror(self) -> bool:
        return not self.reason_codes

    @property
    def digest(self) -> str:
        return digest_json({
            "candidate_digest": self.candidate_digest,
            "source_manifest_digest": self.source_manifest_digest,
            "policy_digest": self.policy_digest,
            "independent_roots": self.independent_roots,
            "accepted_sources": self.accepted_sources,
            "reason_codes": list(self.reason_codes),
        })


@dataclass(frozen=True, slots=True)
class ShadowWeightBatch:
    candidate: CandidateWeights
    sources: tuple[SourceAttestation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CandidateWeights) or self.candidate.status != "candidate":
            raise ShadowWeightError("shadow batches require unpromoted candidate weights")
        sources = tuple(self.sources)
        if not sources or len(sources) > 10_000:
            raise ShadowWeightError("shadow source count out of bounds")
        if any(not isinstance(source, SourceAttestation) for source in sources):
            raise ShadowWeightError("invalid source attestation")
        ids = [source.source_id for source in sources]
        if len(set(ids)) != len(ids):
            raise ShadowWeightError("duplicated source identity")
        object.__setattr__(self, "sources", tuple(sorted(sources, key=lambda source: source.source_id)))

    @property
    def source_manifest_digest(self) -> str:
        return digest_json([source.as_dict() for source in self.sources])

    @property
    def digest(self) -> str:
        return digest_json({
            "candidate_digest": self.candidate.digest,
            "source_manifest_digest": self.source_manifest_digest,
        })

    def with_sources(self, additions: Sequence[SourceAttestation]) -> "ShadowWeightBatch":
        """Return a new immutable revision; conflicting source IDs never overwrite."""
        combined = {source.source_id: source for source in self.sources}
        for source in additions:
            if not isinstance(source, SourceAttestation):
                raise ShadowWeightError("invalid appended source")
            previous = combined.get(source.source_id)
            if previous is not None and previous != source:
                raise ShadowWeightError("source identity already bound to other content")
            combined[source.source_id] = source
        return ShadowWeightBatch(self.candidate, tuple(combined.values()))

    def assess(self, policy: ShadowWeightPolicy) -> ShadowAssessment:
        if not isinstance(policy, ShadowWeightPolicy):
            raise ShadowWeightError("shadow assessment requires explicit policy")
        reasons: set[str] = set()
        if len(self.sources) > policy.maximum_sources:
            reasons.add("source-budget-exceeded")
        rights = [source for source in self.sources if source.allowed_for_training]
        if policy.require_uncontested_rights and len(rights) != len(self.sources):
            reasons.add("training-rights-unresolved")
        if any(source.contradiction for source in self.sources):
            reasons.add("unresolved-contradiction")
        credible = [source for source in rights if (
            source.quality_ppm >= policy.minimum_quality_ppm and not source.contradiction
        )]
        independent_roots = len({source.root_id for source in credible})
        if independent_roots < policy.minimum_independent_roots:
            reasons.add("insufficient-independent-evidence")
        if len(credible) != len(self.sources):
            reasons.add("insufficient-source-quality")
        return ShadowAssessment(
            candidate_digest=self.candidate.digest,
            source_manifest_digest=self.source_manifest_digest,
            policy_digest=policy.digest,
            independent_roots=independent_roots,
            accepted_sources=len(credible),
            reason_codes=tuple(sorted(reasons)),
        )


@dataclass(frozen=True, slots=True)
class ShadowPromotionPermit:
    """Immutable admission permit; cannot itself mutate production weights."""

    candidate_id: str
    candidate_digest: str
    weights_digest: str
    base_model_digest: str
    assessment_digest: str
    evaluation_digest: str
    promotion_digest: str
    rollback_checkpoint_digest: str
    mirror_verifier: str
    admission_authority: str
    exact_head_commit: str

    def __post_init__(self) -> None:
        require_id(self.candidate_id, "candidate_id")
        for name in (
            "candidate_digest", "weights_digest", "base_model_digest",
            "assessment_digest", "evaluation_digest", "promotion_digest",
            "rollback_checkpoint_digest", "exact_head_commit",
        ):
            require_digest(getattr(self, name), name)
        require_id(self.mirror_verifier, "mirror_verifier")
        require_id(self.admission_authority, "admission_authority")
        if self.mirror_verifier == self.admission_authority:
            raise ShadowWeightError("admission authority must be separate from mirror evaluator")

    @property
    def digest(self) -> str:
        return digest_json({
            "candidate_id": self.candidate_id,
            "candidate_digest": self.candidate_digest,
            "weights_digest": self.weights_digest,
            "base_model_digest": self.base_model_digest,
            "assessment_digest": self.assessment_digest,
            "evaluation_digest": self.evaluation_digest,
            "promotion_digest": self.promotion_digest,
            "rollback_checkpoint_digest": self.rollback_checkpoint_digest,
            "mirror_verifier": self.mirror_verifier,
            "admission_authority": self.admission_authority,
            "exact_head_commit": self.exact_head_commit,
        })


def authorize_shadow_promotion(
    batch: ShadowWeightBatch,
    assessment: ShadowAssessment,
    evaluation: MirrorEvaluation,
    promotion: PromotionEvidence,
    *,
    admission_authority: str,
) -> ShadowPromotionPermit:
    """Fail closed until independent evidence qualifies a specific candidate.

    Mirror and promotion receipts remain externally produced. Callers cannot
    bypass the holdout/risk/rights conditions merely by staging a candidate.
    """
    if assessment.candidate_digest != batch.candidate.digest:
        raise ShadowWeightError("assessment is bound to a different candidate")
    if assessment.source_manifest_digest != batch.source_manifest_digest:
        raise ShadowWeightError("source attestations changed after assessment")
    if not assessment.eligible_for_mirror:
        raise ShadowWeightError("shadow evidence did not qualify for mirror evaluation")
    if not isinstance(evaluation, MirrorEvaluation) or not isinstance(promotion, PromotionEvidence):
        raise ShadowWeightError("independent evaluation and promotion receipts required")
    candidate = batch.candidate
    if evaluation.candidate_digest != candidate.digest:
        raise ShadowWeightError("independent evaluation candidate mismatch")
    if evaluation.champion_digest != candidate.base_model_digest:
        raise ShadowWeightError("independent evaluation champion mismatch")
    if not evaluation.candidate_wins:
        raise ShadowWeightError("candidate failed independent mirror improvement gate")
    if not promotion.qualified or promotion.candidate_digest != candidate.digest:
        raise ShadowWeightError("candidate lacks qualified promotion evidence")
    if promotion.evaluation_digest != digest_json(evaluation.__dict__):
        raise ShadowWeightError("promotion is not bound to evaluation")
    if promotion.independent_verifier != evaluation.independent_verifier:
        raise ShadowWeightError("mirror verifier identity mismatch")
    require_id(admission_authority, "admission_authority")
    if admission_authority == evaluation.independent_verifier:
        raise ShadowWeightError("mirror evaluator cannot authorize admission")
    return ShadowPromotionPermit(
        candidate_id=candidate.candidate_id,
        candidate_digest=candidate.digest,
        weights_digest=candidate.weights_digest,
        base_model_digest=candidate.base_model_digest,
        assessment_digest=assessment.digest,
        evaluation_digest=digest_json(evaluation.__dict__),
        promotion_digest=promotion.digest,
        rollback_checkpoint_digest=promotion.rollback_digest,
        mirror_verifier=evaluation.independent_verifier,
        admission_authority=admission_authority,
        exact_head_commit=promotion.exact_head_commit,
    )


__all__ = [
    "ShadowWeightError", "SourceAttestation", "ShadowWeightPolicy",
    "ShadowAssessment", "ShadowWeightBatch", "ShadowPromotionPermit",
    "authorize_shadow_promotion",
]
