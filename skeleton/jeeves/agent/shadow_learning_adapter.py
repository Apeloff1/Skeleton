"""Jeeves lessons -> shadow knowledge proposals, never production weights.

An improved runtime policy is not a trained model. This bridge converts
independently evaluated evolution lessons into *reviewable* shadow-data
candidates. Dataset rights, source independence, contamination, real model
training and promotion remain separate gates owned by the canonical training
and serving planes.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.ai.training.flgb_training_runtime import digest_json, require_digest, require_id
from skeleton.ai.training.shadow_weight_pipeline import (
    ShadowWeightIntake, SourceAttestation,
)
from .self_evolution import (
    EvaluationReport, EvolutionProposal, ProposalStatus,
)


class ShadowLearningError(ValueError):
    """Evolution proposal cannot be legitimately converted into shadow intake."""


@dataclass(frozen=True, slots=True)
class ShadowLearningHandoff:
    intake: ShadowWeightIntake
    evolution_proposal_digest: str
    paired_evaluation_digest: str
    lesson_ids: tuple[str, ...]
    initial_state: str = "inbox"

    @property
    def digest(self) -> str:
        return digest_json({
            "schema": "jeeves.shadow_learning_handoff.v1",
            "intake_digest": self.intake.digest,
            "evolution_proposal_digest": self.evolution_proposal_digest,
            "paired_evaluation_digest": self.paired_evaluation_digest,
            "lesson_ids": list(self.lesson_ids),
            "initial_state": self.initial_state,
        })


def prepare_shadow_learning_handoff(
    proposal: EvolutionProposal, report: EvaluationReport,
    *,
    intake_id: str,
    target_scope: str,
    parent_model_digest: str,
    proposed_dataset_digest: str,
    source_attestations: tuple[SourceAttestation, ...],
    builder_id: str,
    observed_at_ns: int,
    task_relevance_ppm: int,
    independent_novelty_ppm: int,
) -> ShadowLearningHandoff:
    """Propose only evidence-backed lessons, with no training or promotion."""
    if not isinstance(proposal, EvolutionProposal) or not isinstance(report, EvaluationReport):
        raise ShadowLearningError("typed evolution proposal and paired evaluation required")
    if proposal.status not in (
        ProposalStatus.VALIDATED, ProposalStatus.CANARY, ProposalStatus.PROMOTED,
    ):
        raise ShadowLearningError("draft/rejected/rolled-back learning is ineligible")
    if proposal.proposal_id != report.proposal_id:
        raise ShadowLearningError("paired evaluation belongs to another evolution proposal")
    if (not report.passed or report.cases < 8
            or report.weighted_improvement <= 0 or report.critical_regressions):
        raise ShadowLearningError("independent paired improvement evidence has not passed")
    if not proposal.support_lesson_ids:
        raise ShadowLearningError("shadow proposal requires grounded lesson lineage")
    if not isinstance(source_attestations, tuple) or len(source_attestations) < 2:
        raise ShadowLearningError("multiple source attestations required")
    require_id(builder_id, "builder_id")
    require_digest(parent_model_digest, "parent_model_digest")
    require_digest(proposed_dataset_digest, "proposed_dataset_digest")
    if type(observed_at_ns) is not int or observed_at_ns < 0:
        raise ShadowLearningError("observed_at_ns must be non-negative")
    if type(task_relevance_ppm) is not int or not 0 <= task_relevance_ppm <= 1_000_000:
        raise ShadowLearningError("relevance must be integer millionths")
    if type(independent_novelty_ppm) is not int or not 0 <= independent_novelty_ppm <= 1_000_000:
        raise ShadowLearningError("novelty must be integer millionths")
    if any(source.claim_digest != proposal.fingerprint for source in source_attestations):
        raise ShadowLearningError("source attestations do not bind the exact lesson proposal")
    if len({source.independence_group for source in source_attestations}) < 2:
        raise ShadowLearningError("independent source groups required for shadow intake")
    confidence = round(min(proposal.confidence, report.candidate_success_rate) * 1_000_000)
    intake = ShadowWeightIntake(
        intake_id=intake_id, subject_id=proposal.proposal_id,
        claim_digest=proposal.fingerprint,
        target_scope=target_scope, sources=source_attestations,
        proposed_dataset_digest=proposed_dataset_digest,
        parent_model_digest=parent_model_digest,
        proposed_by=builder_id,
        relevance_ppm=task_relevance_ppm,
        confidence_ppm=confidence,
        novelty_ppm=independent_novelty_ppm,
        observed_at_ns=observed_at_ns,
    )
    return ShadowLearningHandoff(
        intake=intake,
        evolution_proposal_digest=proposal.fingerprint,
        paired_evaluation_digest=report.fingerprint,
        lesson_ids=proposal.support_lesson_ids,
    )


__all__ = [
    "ShadowLearningError", "ShadowLearningHandoff",
    "prepare_shadow_learning_handoff",
]
