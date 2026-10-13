"""Provider-diverse multi-model consensus without execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.ai.consensus import proposal_shape_digest
from skeleton.shells.ai.types import AIPlanProposal


@dataclass(frozen=True)
class ConsensusPolicy:
    min_unique_models: int = 2
    min_unique_providers: int = 1
    min_average_confidence: float = 0.0
    max_average_uncertainty: float = 1.0
    reject_missing_model_id: bool = True
    reject_missing_provider_id: bool = False

    def __post_init__(self) -> None:
        if self.min_unique_models <= 0:
            raise ValueError("min_unique_models must be positive")
        if self.min_unique_providers <= 0:
            raise ValueError("min_unique_providers must be positive")
        if not 0 <= self.min_average_confidence <= 1:
            raise ValueError("min_average_confidence out of range")
        if not 0 <= self.max_average_uncertainty <= 1:
            raise ValueError("max_average_uncertainty out of range")


@dataclass(frozen=True)
class RobustConsensusGroup:
    shape_digest: str
    proposal_ids: tuple[str, ...]
    model_ids: tuple[str, ...]
    provider_ids: tuple[str, ...]
    unique_model_votes: int
    unique_provider_votes: int
    average_confidence: float
    average_uncertainty: float
    eligible: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "shape_digest": self.shape_digest,
            "proposal_ids": list(self.proposal_ids),
            "model_ids": list(self.model_ids),
            "provider_ids": list(self.provider_ids),
            "unique_model_votes": self.unique_model_votes,
            "unique_provider_votes": self.unique_provider_votes,
            "average_confidence": self.average_confidence,
            "average_uncertainty": self.average_uncertainty,
            "eligible": self.eligible,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RobustConsensusReport:
    groups: tuple[RobustConsensusGroup, ...]
    winning_shape: str | None
    policy: ConsensusPolicy

    @property
    def reached(self) -> bool:
        return self.winning_shape is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "reached": self.reached,
            "winning_shape": self.winning_shape,
            "groups": [item.to_dict() for item in self.groups],
            "policy": {
                "min_unique_models": self.policy.min_unique_models,
                "min_unique_providers": self.policy.min_unique_providers,
                "min_average_confidence": self.policy.min_average_confidence,
                "max_average_uncertainty": self.policy.max_average_uncertainty,
            },
        }


class RobustProposalConsensus:
    """One model identity gets at most one vote for one shape."""

    def __init__(self, policy: ConsensusPolicy | None = None) -> None:
        self.policy = policy or ConsensusPolicy()

    def evaluate(
        self,
        proposals: tuple[AIPlanProposal, ...],
        *,
        provider_by_model: Mapping[str, str] | None = None,
    ) -> RobustConsensusReport:
        providers = MappingProxyType(dict(provider_by_model or {}))
        by_shape: dict[str, dict[str, AIPlanProposal]] = {}
        missing_model = []
        for proposal in proposals:
            model_id = proposal.model_id
            if not model_id:
                if self.policy.reject_missing_model_id:
                    missing_model.append(proposal)
                    continue
                model_id = f"anonymous:{proposal.proposal_id}"
            digest = proposal_shape_digest(proposal)
            model_map = by_shape.setdefault(digest, {})
            current = model_map.get(model_id)
            if current is None or self._better(proposal, current):
                model_map[model_id] = proposal

        groups = []
        for digest, model_map in by_shape.items():
            chosen = tuple(model_map[key] for key in sorted(model_map))
            model_ids = tuple(sorted(model_map))
            provider_ids = []
            missing_provider = False
            for model_id in model_ids:
                provider = providers.get(model_id, "")
                if not provider:
                    if self.policy.reject_missing_provider_id:
                        missing_provider = True
                    provider = f"unknown:{model_id}"
                provider_ids.append(provider)
            unique_providers = tuple(sorted(set(provider_ids)))
            avg_confidence = sum(item.confidence for item in chosen) / len(chosen)
            avg_uncertainty = sum(item.uncertainty for item in chosen) / len(chosen)
            reasons = []
            if len(model_ids) < self.policy.min_unique_models:
                reasons.append("insufficient unique model votes")
            if len(unique_providers) < self.policy.min_unique_providers:
                reasons.append("insufficient provider diversity")
            if avg_confidence < self.policy.min_average_confidence:
                reasons.append("average confidence below consensus threshold")
            if avg_uncertainty > self.policy.max_average_uncertainty:
                reasons.append("average uncertainty above consensus threshold")
            if missing_provider:
                reasons.append("provider identity missing for one or more models")
            groups.append(
                RobustConsensusGroup(
                    digest,
                    tuple(sorted(item.proposal_id for item in chosen)),
                    model_ids,
                    unique_providers,
                    len(model_ids),
                    len(unique_providers),
                    avg_confidence,
                    avg_uncertainty,
                    not reasons,
                    tuple(reasons),
                )
            )
        groups.sort(
            key=lambda item: (
                not item.eligible,
                -item.unique_provider_votes,
                -item.unique_model_votes,
                -item.average_confidence,
                item.average_uncertainty,
                item.shape_digest,
            )
        )
        winner = groups[0].shape_digest if groups and groups[0].eligible else None
        return RobustConsensusReport(tuple(groups), winner, self.policy)

    @staticmethod
    def _better(candidate: AIPlanProposal, current: AIPlanProposal) -> bool:
        return (
            candidate.confidence,
            -candidate.uncertainty,
            candidate.proposal_id,
        ) > (
            current.confidence,
            -current.uncertainty,
            current.proposal_id,
        )
