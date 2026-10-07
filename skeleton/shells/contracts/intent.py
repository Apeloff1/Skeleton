"""Multi-step typed command intentions and deterministic preflight planning."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence
import uuid

from skeleton.shells.contracts.core import (
    CommandContractCatalog,
    ContractDecision,
    ContractExecutionPolicy,
    RiskTier,
    ToolEffect,
)
from skeleton.shells.provenance import canonical_json


@dataclass(frozen=True)
class CommandIntentStep:
    command: str
    args: tuple[str, ...] = ()
    cwd: str = ""
    env_keys: frozenset[str] = frozenset()
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.command:
            raise ValueError("intent command is required")
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "env_keys", frozenset(self.env_keys))
        if any(not isinstance(key, str) or not key for key in self.env_keys):
            raise ValueError("environment keys must be non-empty strings")

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "args": list(self.args),
            "cwd": self.cwd,
            "env_keys": sorted(self.env_keys),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CommandIntent:
    steps: tuple[CommandIntentStep, ...]
    intent_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    principal: str = "anonymous"
    metadata: Mapping[str, str] = field(default_factory=dict)
    max_steps: int = 128

    def __post_init__(self) -> None:
        steps = tuple(self.steps)
        if not steps:
            raise ValueError("command intent requires at least one step")
        if isinstance(self.max_steps, bool) or self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if len(steps) > self.max_steps:
            raise ValueError("command intent exceeds step bound")
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            canonical_json(
                {
                    "intent_id": self.intent_id,
                    "principal": self.principal,
                    "steps": [step.to_dict() for step in self.steps],
                    "metadata": dict(sorted(self.metadata.items())),
                }
            )
        ).hexdigest()


@dataclass(frozen=True)
class PlannedStep:
    index: int
    step: CommandIntentStep
    decision: ContractDecision
    policy_decision: ContractDecision

    @property
    def allowed(self) -> bool:
        return self.policy_decision.allowed

    @property
    def requires_approval(self) -> bool:
        return (
            self.decision.requires_approval
            or self.policy_decision.requires_approval
        )


@dataclass(frozen=True)
class CommandPlan:
    intent_id: str
    intent_digest: str
    steps: tuple[PlannedStep, ...]
    effects: frozenset[ToolEffect]
    highest_risk: RiskTier
    allowed: bool
    requires_approval: bool
    plan_digest: str

    @property
    def denied_steps(self) -> tuple[PlannedStep, ...]:
        return tuple(step for step in self.steps if not step.allowed)

    def to_dict(self) -> dict[str, object]:
        return {
            "intent_id": self.intent_id,
            "intent_digest": self.intent_digest,
            "effects": sorted(effect.value for effect in self.effects),
            "highest_risk": self.highest_risk.value,
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "plan_digest": self.plan_digest,
            "steps": [
                {
                    "index": step.index,
                    "command": step.step.command,
                    "args": list(step.step.args),
                    "allowed": step.allowed,
                    "reason": step.policy_decision.reason,
                    "risk": step.decision.risk.value,
                    "effects": sorted(effect.value for effect in step.decision.effects),
                    "requires_approval": step.requires_approval,
                }
                for step in self.steps
            ],
        }


class ContractPlanner:
    def __init__(
        self,
        catalog: CommandContractCatalog,
        policy: ContractExecutionPolicy,
    ) -> None:
        self.catalog = catalog
        self.policy = policy

    def plan(
        self,
        intent: CommandIntent,
        *,
        approved: bool = False,
    ) -> CommandPlan:
        planned: list[PlannedStep] = []
        effects: set[ToolEffect] = set()
        highest = RiskTier.LOW
        rank = {
            RiskTier.LOW: 0,
            RiskTier.MEDIUM: 1,
            RiskTier.HIGH: 2,
            RiskTier.CRITICAL: 3,
        }
        for index, step in enumerate(intent.steps):
            contract = self.catalog.resolve(step.command)
            decision = contract.validate(step.args)
            policy_decision = self.policy.inspect(decision, approved=approved)
            planned.append(
                PlannedStep(
                    index,
                    step,
                    decision,
                    policy_decision,
                )
            )
            effects.update(decision.effects)
            if rank[decision.risk] > rank[highest]:
                highest = decision.risk

        allowed = all(step.allowed for step in planned)
        requires_approval = any(step.requires_approval for step in planned)
        payload = {
            "intent_id": intent.intent_id,
            "intent_digest": intent.digest,
            "steps": [
                {
                    "index": step.index,
                    "command": step.step.command,
                    "args": list(step.step.args),
                    "allowed": step.allowed,
                    "reason": step.policy_decision.reason,
                }
                for step in planned
            ],
            "effects": sorted(effect.value for effect in effects),
            "highest_risk": highest.value,
            "allowed": allowed,
            "requires_approval": requires_approval,
        }
        plan_digest = hashlib.sha256(canonical_json(payload)).hexdigest()
        return CommandPlan(
            intent.intent_id,
            intent.digest,
            tuple(planned),
            frozenset(effects),
            highest,
            allowed,
            requires_approval,
            plan_digest,
        )
