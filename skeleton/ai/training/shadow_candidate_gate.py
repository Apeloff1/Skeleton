"""Model-improvement handoff: shadow evidence -> trained candidate -> host decision.

This module binds a reviewed shadow intake to the canonical dataset/training
lineage, candidate weights, independent champion/challenger comparisons and
qualified promotion evidence. It returns an immutable PROPOSAL, never loads a
weight shard, changes a registry alias or executes a model deployment.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .flgb_training_runtime import (
    CandidateWeights, MirrorEvaluation, PromotionEvidence, TrainingCheckpoint,
    TrainingManifest, digest_json, require_digest, require_id,
)
from .shadow_weight_pipeline import ShadowRecord, ShadowState, ShadowWeightError


class ImprovementDirection(str, Enum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True, slots=True)
class ImprovementAxis:
    """One predeclared criterion; values use integer millionths."""

    axis_id: str
    direction: ImprovementDirection
    baseline_ppm: int
    candidate_ppm: int
    tolerance_ppm: int = 0
    critical: bool = False

    def __post_init__(self) -> None:
        require_id(self.axis_id, "axis_id")
        if not isinstance(self.direction, ImprovementDirection):
            raise ShadowWeightError("invalid improvement direction")
        for name in ("baseline_ppm", "candidate_ppm", "tolerance_ppm"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 1_000_000:
                raise ShadowWeightError(f"{name} must be bounded millionths")
        if type(self.critical) is not bool:
            raise ShadowWeightError("critical axis must be boolean")

    @property
    def improvement_ppm(self) -> int:
        diff = self.candidate_ppm - self.baseline_ppm
        return diff if self.direction is ImprovementDirection.MAXIMIZE else -diff

    @property
    def within_floor(self) -> bool:
        return self.improvement_ppm >= -self.tolerance_ppm

    def as_dict(self) -> dict[str, object]:
        return {
            "axis_id": self.axis_id,
            "direction": self.direction.value,
            "baseline_ppm": self.baseline_ppm,
            "candidate_ppm": self.candidate_ppm,
            "tolerance_ppm": self.tolerance_ppm,
            "critical": self.critical,
        }


@dataclass(frozen=True, slots=True)
class ImprovementMatrix:
    """Paired model quality comparison against an immutable baseline.

    This is an evidence *description*. A host-controlled independent verifier
    must still attest the actual evaluation/canary run before deployment.
    """

    matrix_id: str
    suite_digest: str
    baseline_model_digest: str
    candidate_weights_digest: str
    evaluator_id: str
    evaluator_evidence_digest: str
    dataset_digest: str
    axes: tuple[ImprovementAxis, ...]
    minimum_net_improvement_ppm: int = 1
    safety_passed: bool = False
    rights_passed: bool = False
    rollback_ready: bool = False

    def __post_init__(self) -> None:
        for key in ("matrix_id", "evaluator_id"):
            require_id(getattr(self, key), key)
        for key in ("suite_digest", "baseline_model_digest", "candidate_weights_digest",
                    "evaluator_evidence_digest", "dataset_digest"):
            require_digest(getattr(self, key), key)
        if not isinstance(self.axes, tuple) or not 1 <= len(self.axes) <= 128:
            raise ShadowWeightError("matrix must contain 1..128 predeclared axes")
        if any(not isinstance(axis, ImprovementAxis) for axis in self.axes):
            raise ShadowWeightError("invalid matrix axis")
        if len({axis.axis_id for axis in self.axes}) != len(self.axes):
            raise ShadowWeightError("matrix axes cannot repeat")
        if type(self.minimum_net_improvement_ppm) is not int or not 1 <= self.minimum_net_improvement_ppm <= 1_000_000:
            raise ShadowWeightError("minimum net improvement must be positive")
        for name in ("safety_passed", "rights_passed", "rollback_ready"):
            if type(getattr(self, name)) is not bool:
                raise ShadowWeightError("matrix gates must be booleans")
        object.__setattr__(self, "axes", tuple(sorted(self.axes, key=lambda x: x.axis_id)))

    @property
    def net_improvement_ppm(self) -> int:
        return sum(axis.improvement_ppm for axis in self.axes) // len(self.axes)

    @property
    def regressions(self) -> tuple[str, ...]:
        return tuple(axis.axis_id for axis in self.axes if not axis.within_floor)

    @property
    def critical_regressions(self) -> tuple[str, ...]:
        return tuple(axis.axis_id for axis in self.axes
                     if axis.critical and not axis.within_floor)

    @property
    def promotable(self) -> bool:
        return (
            self.safety_passed and self.rights_passed and self.rollback_ready
            and not self.regressions
            and self.net_improvement_ppm >= self.minimum_net_improvement_ppm
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "skeleton.improvement_matrix.v1",
            "matrix_id": self.matrix_id,
            "suite_digest": self.suite_digest,
            "baseline_model_digest": self.baseline_model_digest,
            "candidate_weights_digest": self.candidate_weights_digest,
            "evaluator_id": self.evaluator_id,
            "evaluator_evidence_digest": self.evaluator_evidence_digest,
            "dataset_digest": self.dataset_digest,
            "axes": [axis.as_dict() for axis in self.axes],
            "minimum_net_improvement_ppm": self.minimum_net_improvement_ppm,
            "safety_passed": self.safety_passed,
            "rights_passed": self.rights_passed,
            "rollback_ready": self.rollback_ready,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class CandidateReleaseProposal:
    """Immutable exact-identity package for an external host admission gate."""

    intake_id: str
    intake_digest: str
    shadow_review_digest: str
    source_event_digest: str
    training_manifest_digest: str
    checkpoint_digest: str
    candidate_digest: str
    weights_digest: str
    comparison_digest: str
    evaluation_digest: str
    promotion_digest: str
    champion_digest: str
    exact_head_commit: str
    verifier_id: str
    rollback_checkpoint_digest: str

    def __post_init__(self) -> None:
        require_id(self.intake_id, "intake_id")
        require_id(self.verifier_id, "verifier_id")
        for name in (
            "intake_digest", "shadow_review_digest", "source_event_digest",
            "training_manifest_digest", "checkpoint_digest", "candidate_digest",
            "weights_digest", "comparison_digest", "evaluation_digest",
            "promotion_digest", "champion_digest", "exact_head_commit",
            "rollback_checkpoint_digest",
        ):
            require_digest(getattr(self, name), name)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "skeleton.candidate_release_proposal.v1",
            **{name: getattr(self, name) for name in (
                "intake_id", "intake_digest", "shadow_review_digest", "source_event_digest",
                "training_manifest_digest", "checkpoint_digest", "candidate_digest",
                "weights_digest", "comparison_digest", "evaluation_digest",
                "promotion_digest", "champion_digest", "exact_head_commit",
                "verifier_id", "rollback_checkpoint_digest",
            )},
            "dispatch_performed": False,
            "production_weights_changed": False,
            "requires": [
                "host runtime admission",
                "exact checkpoint rollback",
                "independent production canary",
                "external execution authorization",
            ],
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


def prepare_candidate_release(
    shadow: ShadowRecord,
    manifest: TrainingManifest,
    checkpoint: TrainingCheckpoint,
    candidate: CandidateWeights,
    comparison: ImprovementMatrix,
    evaluation: MirrorEvaluation,
    promotion: PromotionEvidence,
    *,
    expected_head_commit: str,
) -> CandidateReleaseProposal:
    """Bind independent evidence and training identity without deploying weights."""
    require_digest(expected_head_commit, "expected_head_commit")
    if not isinstance(shadow, ShadowRecord) or shadow.state is not ShadowState.CONSUMED:
        raise ShadowWeightError("shadow intake requires consumed candidate-only training")
    if not shadow.review_digest or not shadow.training_manifest_digest or not shadow.last_event_digest:
        raise ShadowWeightError("shadow identity has incomplete evidence chain")
    if any(not isinstance(item, cls) for item, cls in (
        (manifest, TrainingManifest), (checkpoint, TrainingCheckpoint),
        (candidate, CandidateWeights), (comparison, ImprovementMatrix),
        (evaluation, MirrorEvaluation), (promotion, PromotionEvidence),
    )):
        raise ShadowWeightError("candidate handoff contains invalid typed evidence")
    if (manifest.digest != shadow.training_manifest_digest
            or manifest.base_model_digest != shadow.intake.parent_model_digest
            or shadow.intake.proposed_dataset_digest not in manifest.dataset_revision_digests):
        raise ShadowWeightError("training manifest diverges from reviewed shadow intake")
    if (checkpoint.run_manifest_digest != manifest.digest
            or checkpoint.weights_digest != candidate.weights_digest
            or candidate.base_model_digest != manifest.base_model_digest
            or candidate.training_lineage_digest != checkpoint.digest):
        raise ShadowWeightError("candidate weights mismatch independently bound lineage")
    if shadow.consumed_candidate_digest != candidate.digest:
        raise ShadowWeightError("consumed shadow event does not bind this trained candidate")
    if candidate.status != "candidate":
        raise ShadowWeightError("handoff requires unpublished candidate-only weights")
    if (comparison.candidate_weights_digest != candidate.weights_digest
            or comparison.baseline_model_digest != candidate.base_model_digest
            or comparison.dataset_digest != shadow.intake.proposed_dataset_digest
            or comparison.evaluator_id == shadow.intake.proposed_by):
        raise ShadowWeightError("comparison not bound to independent candidate evaluation")
    if not comparison.promotable:
        raise ShadowWeightError("candidate fails at least one comparison floor or gate")
    if (evaluation.candidate_digest != candidate.digest
            or evaluation.champion_digest != candidate.base_model_digest
            or evaluation.independent_verifier != comparison.evaluator_id
            or not evaluation.candidate_wins):
        raise ShadowWeightError("independent mirror evaluation did not qualify candidate")
    if (promotion.candidate_digest != candidate.digest
            or promotion.evaluation_digest != digest_json(evaluation.__dict__)
            or promotion.exact_head_commit != expected_head_commit
            or promotion.independent_verifier != evaluation.independent_verifier
            or not promotion.qualified):
        raise ShadowWeightError("promotion evidence fails independent identity or gates")
    if promotion.rollback_digest == candidate.weights_digest:
        raise ShadowWeightError("rollback checkpoint must not point to candidate weights")
    return CandidateReleaseProposal(
        intake_id=shadow.identity,
        intake_digest=shadow.intake.digest,
        shadow_review_digest=shadow.review_digest,
        source_event_digest=shadow.last_event_digest,
        training_manifest_digest=manifest.digest,
        checkpoint_digest=checkpoint.digest,
        candidate_digest=candidate.digest,
        weights_digest=candidate.weights_digest,
        comparison_digest=comparison.digest,
        evaluation_digest=digest_json(evaluation.__dict__),
        promotion_digest=promotion.digest,
        champion_digest=candidate.base_model_digest,
        exact_head_commit=expected_head_commit,
        verifier_id=evaluation.independent_verifier,
        rollback_checkpoint_digest=promotion.rollback_digest,
    )


__all__ = [
    "ImprovementDirection", "ImprovementAxis", "ImprovementMatrix",
    "CandidateReleaseProposal", "prepare_candidate_release",
]
