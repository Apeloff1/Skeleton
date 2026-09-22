"""Model-admitted wrapper for provider-diverse ensemble planning."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.ensemble_planner import (
    EnsembleAIPlanner,
    EnsemblePlanningResult,
)
from skeleton.shells.ai.model_admission import (
    AIModelAdmission,
    ModelAdmissionReport,
    ModelAdmissionRequirement,
)
from skeleton.shells.ai.types import AIIntent


@dataclass(frozen=True)
class AdmittedEnsembleResult:
    planning: EnsemblePlanningResult
    admissions: tuple[ModelAdmissionReport, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "planning": self.planning.to_dict(),
            "admissions": [item.to_dict() for item in self.admissions],
        }


class AdmittedEnsembleAIPlanner:
    """Require every participating ensemble member to pass model admission."""

    def __init__(
        self,
        ensemble: EnsembleAIPlanner,
        admission: AIModelAdmission,
        requirements: tuple[ModelAdmissionRequirement, ...],
    ) -> None:
        self.ensemble = ensemble
        self.admission = admission
        by_identity = {
            (item.provider_id, item.model_id): item
            for item in requirements
        }
        if len(by_identity) != len(requirements):
            raise ValueError("duplicate ensemble admission requirement")
        expected = {
            (member.provider_id, member.model_id)
            for member in ensemble.members
        }
        if set(by_identity) != expected:
            raise ValueError("ensemble admission requirements do not match members")
        self.requirements = by_identity

    def propose(
        self,
        intent: AIIntent,
        *,
        prior_observations: tuple[dict[str, object], ...] = (),
    ) -> AdmittedEnsembleResult:
        reports = []
        for member in self.ensemble.members:
            requirement = self.requirements[
                (member.provider_id, member.model_id)
            ]
            reports.append(self.admission.require(requirement))
        planning = self.ensemble.propose(
            intent,
            prior_observations=prior_observations,
        )
        return AdmittedEnsembleResult(planning, tuple(reports))
