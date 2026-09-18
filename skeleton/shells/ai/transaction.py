"""Compensation planning for reversible AI shell actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.effects import EffectRegistry
from skeleton.shells.ai.types import AIAction, AIPlanProposal


class TransactionState(str, Enum):
    PREPARED = "prepared"
    EXECUTING = "executing"
    COMMITTED = "committed"
    COMPENSATION_REQUIRED = "compensation_required"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass(frozen=True)
class CompensationAction:
    source_action_id: str
    command: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_action_id": self.source_action_id,
            "command": self.command,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TransactionPlan:
    proposal_id: str
    reversible: bool
    compensation: tuple[CompensationAction, ...]
    uncompensated_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "reversible": self.reversible,
            "compensation": [item.to_dict() for item in self.compensation],
            "uncompensated_actions": list(self.uncompensated_actions),
        }


class AITransactionPlanner:
    """Build compensation metadata only; compensation is never auto-executed."""

    def __init__(self, effects: EffectRegistry) -> None:
        self.effects = effects

    def plan(self, proposal: AIPlanProposal) -> TransactionPlan:
        compensation = []
        uncompensated = []
        for action in reversed(proposal.actions):
            contract = self.effects.inspect(action.command)
            if contract is None or not contract.reversible:
                uncompensated.append(action.action_id)
                continue
            if contract.compensation_command:
                compensation.append(
                    CompensationAction(
                        source_action_id=action.action_id,
                        command=contract.compensation_command,
                        reason="declared effect compensation",
                    )
                )
            else:
                uncompensated.append(action.action_id)
        return TransactionPlan(
            proposal.proposal_id,
            not uncompensated,
            tuple(compensation),
            tuple(uncompensated),
        )
