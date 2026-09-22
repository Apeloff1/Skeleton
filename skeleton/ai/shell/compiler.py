"""Compile validated AI proposals into ordinary immutable ExecutionPlan objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from skeleton.shells.ai.effects import EffectRegistry
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep


EnvironmentResolver = Callable[[str, str, str], str]


@dataclass(frozen=True)
class CompiledAIPlan:
    plan: ExecutionPlan
    intent_fingerprint: str
    proposal_fingerprint: str
    effect_digest: str
    environment_references: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan.plan_id,
            "intent_fingerprint": self.intent_fingerprint,
            "proposal_fingerprint": self.proposal_fingerprint,
            "effect_digest": self.effect_digest,
            "environment_references": list(self.environment_references),
            "plan_fingerprint": self.plan.fingerprint,
        }


class AIPlanCompiler:
    """Convert AI actions into ShellCommand-based plan steps.

    Secret/environment values are resolved outside the model protocol. Resolution
    receives action ID, environment key, and opaque reference name.
    """

    def __init__(
        self,
        effects: EffectRegistry,
        *,
        environment_resolver: EnvironmentResolver | None = None,
    ) -> None:
        self.effects = effects
        self.environment_resolver = environment_resolver

    def _environment(self, action: AIAction) -> tuple[dict[str, str], tuple[str, ...]]:
        if not action.environment_refs:
            return {}, ()
        if self.environment_resolver is None:
            raise ValueError("proposal has unresolved environment references")
        values: dict[str, str] = {}
        refs = []
        for key, reference in sorted(action.environment_refs.items()):
            value = self.environment_resolver(action.action_id, key, reference)
            if not isinstance(value, str):
                raise TypeError("environment resolver must return strings")
            values[key] = value
            refs.append(reference)
        return values, tuple(refs)

    def compile(self, intent: AIIntent, proposal: AIPlanProposal) -> CompiledAIPlan:
        if proposal.intent_id != intent.intent_id:
            raise ValueError("proposal does not belong to intent")
        if len(proposal.actions) > intent.constraint.max_steps:
            raise ValueError("proposal exceeds intent step limit")

        steps = []
        references: list[str] = []
        for action in proposal.actions:
            if not intent.constraint.allows_command(action.command):
                raise ValueError("proposal violates command constraint")
            if (
                action.timeout_seconds is not None
                and action.timeout_seconds > intent.constraint.max_timeout_seconds
            ):
                raise ValueError("proposal violates timeout constraint")
            environment, refs = self._environment(action)
            references.extend(refs)
            command = action.to_shell_command(environment=environment)
            steps.append(
                PlanStep(
                    action.action_id,
                    command,
                    action.depends_on,
                    action.continue_on_failure,
                )
            )

        plan = ExecutionPlan(
            proposal.proposal_id,
            tuple(steps),
            metadata={
                "intent_id": intent.intent_id,
                "intent_fingerprint": intent.fingerprint,
                "proposal_fingerprint": proposal.fingerprint,
                "model_id": proposal.model_id,
                "effect_digest": self.effects.digest,
            },
        )
        return CompiledAIPlan(
            plan=plan,
            intent_fingerprint=intent.fingerprint,
            proposal_fingerprint=proposal.fingerprint,
            effect_digest=self.effects.digest,
            environment_references=tuple(sorted(set(references))),
        )
