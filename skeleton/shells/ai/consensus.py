"""Multi-model proposal consensus without granting extra execution authority."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.ai.types import AIPlanProposal


def proposal_shape(proposal: AIPlanProposal) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "command": action.command,
            "args": list(action.args),
            "cwd": action.cwd,
            "env_keys": sorted(action.environment_refs),
            "timeout_seconds": action.timeout_seconds,
            "depends_on": sorted(action.depends_on),
            "continue_on_failure": action.continue_on_failure,
        }
        for action in proposal.actions
    )


def proposal_shape_digest(proposal: AIPlanProposal) -> str:
    raw = json.dumps(
        proposal_shape(proposal),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ConsensusGroup:
    shape_digest: str
    proposal_ids: tuple[str, ...]
    model_ids: tuple[str, ...]
    votes: int
    average_confidence: float
    average_uncertainty: float

    def to_dict(self) -> dict[str, object]:
        return {
            "shape_digest": self.shape_digest,
            "proposal_ids": list(self.proposal_ids),
            "model_ids": list(self.model_ids),
            "votes": self.votes,
            "average_confidence": self.average_confidence,
            "average_uncertainty": self.average_uncertainty,
        }


@dataclass(frozen=True)
class ConsensusReport:
    groups: tuple[ConsensusGroup, ...]
    winning_shape: str | None
    threshold: int

    @property
    def reached(self) -> bool:
        return self.winning_shape is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "reached": self.reached,
            "winning_shape": self.winning_shape,
            "threshold": self.threshold,
            "groups": [item.to_dict() for item in self.groups],
        }


class ProposalConsensus:
    def evaluate(
        self,
        proposals: tuple[AIPlanProposal, ...],
        *,
        threshold: int = 2,
    ) -> ConsensusReport:
        if threshold <= 0:
            raise ValueError("threshold must be positive")
        if not proposals:
            return ConsensusReport((), None, threshold)
        grouped: dict[str, list[AIPlanProposal]] = {}
        for proposal in proposals:
            grouped.setdefault(proposal_shape_digest(proposal), []).append(proposal)
        groups = []
        for digest, items in grouped.items():
            groups.append(
                ConsensusGroup(
                    digest,
                    tuple(sorted(item.proposal_id for item in items)),
                    tuple(sorted(item.model_id for item in items)),
                    len(items),
                    sum(item.confidence for item in items) / len(items),
                    sum(item.uncertainty for item in items) / len(items),
                )
            )
        groups.sort(
            key=lambda item: (
                -item.votes,
                -item.average_confidence,
                item.average_uncertainty,
                item.shape_digest,
            )
        )
        winner = groups[0].shape_digest if groups[0].votes >= threshold else None
        return ConsensusReport(tuple(groups), winner, threshold)
