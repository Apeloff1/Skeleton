"""Plan construction, validation, scheduling, and revision for Jeeves."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .types import (
    AgentContractError,
    Goal,
    Plan,
    PlanStep,
    RiskTier,
    StepStatus,
    json_safe,
    require_id,
    stable_id,
)


class PlanningError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PlanValidationReport:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    critical_path: tuple[str, ...]
    executable_steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReplanDecision:
    should_replan: bool
    reason: str
    failed_step_id: str | None = None
    retain_completed: bool = True


class PlanValidator:
    def __init__(self, *, maximum_steps: int = 64, require_verification_for_mutation: bool = True) -> None:
        if isinstance(maximum_steps, bool) or not isinstance(maximum_steps, int) or maximum_steps < 1:
            raise ValueError("maximum_steps must be a positive integer")
        self._maximum_steps = maximum_steps
        self._require_verification = bool(require_verification_for_mutation)

    def validate(self, plan: Plan, *, available_tools: set[str] | None = None) -> PlanValidationReport:
        if not isinstance(plan, Plan):
            raise TypeError("plan must be Plan")
        errors: list[str] = []
        warnings: list[str] = []
        if len(plan.steps) > self._maximum_steps:
            errors.append(f"plan exceeds maximum step count {self._maximum_steps}")
        tool_set = None if available_tools is None else set(available_tools)
        for step in plan.steps:
            if step.tool and tool_set is not None and step.tool not in tool_set:
                errors.append(f"step {step.step_id} references unavailable tool {step.tool}")
            if step.risk in {RiskTier.MUTATING, RiskTier.EXTERNAL, RiskTier.HIGH_IMPACT}:
                if self._require_verification and not step.verification:
                    errors.append(f"step {step.step_id} is mutating but lacks verification")
            if step.tool is None and step.status is StepStatus.PENDING and not step.expected_outcome:
                warnings.append(f"reasoning step {step.step_id} has no expected outcome")
            if step.attempts >= step.max_attempts and step.status not in {
                StepStatus.SUCCEEDED,
                StepStatus.FAILED,
                StepStatus.SKIPPED,
            }:
                warnings.append(f"step {step.step_id} has exhausted attempts without terminal status")
        critical = self._critical_path(plan)
        executable = tuple(step.step_id for step in plan.ready_steps())
        return PlanValidationReport(
            valid=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            critical_path=critical,
            executable_steps=executable,
        )

    @staticmethod
    def _critical_path(plan: Plan) -> tuple[str, ...]:
        by_id = {step.step_id: step for step in plan.steps}
        memo: dict[str, tuple[str, ...]] = {}

        def path_to(step_id: str) -> tuple[str, ...]:
            if step_id in memo:
                return memo[step_id]
            step = by_id[step_id]
            if not step.dependencies:
                path = (step_id,)
            else:
                prefixes = [path_to(dep) for dep in step.dependencies]
                longest = max(prefixes, key=lambda item: (len(item), item))
                path = longest + (step_id,)
            memo[step_id] = path
            return path

        paths = [path_to(step.step_id) for step in plan.steps]
        return max(paths, key=lambda item: (len(item), item)) if paths else ()


class PlanScheduler:
    """Compute deterministic ready/blocked state without executing steps."""

    TERMINAL_SUCCESS = frozenset({StepStatus.SUCCEEDED, StepStatus.SKIPPED})
    TERMINAL_FAILURE = frozenset({StepStatus.FAILED, StepStatus.BLOCKED})

    def normalize(self, plan: Plan) -> Plan:
        states = {step.step_id: step.status for step in plan.steps}
        updated: list[PlanStep] = []
        for step in plan.steps:
            if step.status in self.TERMINAL_SUCCESS | self.TERMINAL_FAILURE | {StepStatus.RUNNING}:
                updated.append(step)
                continue
            dependency_states = [states[dep] for dep in step.dependencies]
            if any(state in self.TERMINAL_FAILURE for state in dependency_states):
                updated.append(step.with_status(StepStatus.BLOCKED))
            elif all(state in self.TERMINAL_SUCCESS for state in dependency_states):
                updated.append(step.with_status(StepStatus.READY))
            else:
                updated.append(step.with_status(StepStatus.PENDING))
        return Plan(
            plan_id=plan.plan_id,
            goal_id=plan.goal_id,
            steps=tuple(updated),
            version=plan.version,
            rationale=plan.rationale,
            created_at=plan.created_at,
        )

    def start(self, plan: Plan, step_id: str) -> Plan:
        plan = self.normalize(plan)
        step = plan.step(step_id)
        if step.status is not StepStatus.READY:
            raise PlanningError(f"step {step_id} is not ready")
        if step.attempts >= step.max_attempts:
            raise PlanningError(f"step {step_id} exhausted its attempts")
        return plan.replace_step(step.with_status(StepStatus.RUNNING, increment_attempt=True))

    def succeed(self, plan: Plan, step_id: str) -> Plan:
        step = plan.step(step_id)
        if step.status is not StepStatus.RUNNING:
            raise PlanningError("only running steps can succeed")
        return self.normalize(plan.replace_step(step.with_status(StepStatus.SUCCEEDED)))

    def fail(self, plan: Plan, step_id: str, *, retryable: bool) -> Plan:
        step = plan.step(step_id)
        if step.status is not StepStatus.RUNNING:
            raise PlanningError("only running steps can fail")
        if retryable and step.attempts < step.max_attempts:
            return self.normalize(plan.replace_step(step.with_status(StepStatus.PENDING)))
        return self.normalize(plan.replace_step(step.with_status(StepStatus.FAILED)))

    def skip(self, plan: Plan, step_id: str) -> Plan:
        step = plan.step(step_id)
        if step.status not in {StepStatus.PENDING, StepStatus.READY}:
            raise PlanningError("only pending/ready steps can be skipped")
        return self.normalize(plan.replace_step(step.with_status(StepStatus.SKIPPED)))


class ReplanPolicy:
    def __init__(
        self,
        *,
        replan_on_tool_failure: bool = True,
        replan_on_evidence_conflict: bool = True,
        max_plan_versions: int = 4,
    ) -> None:
        self.replan_on_tool_failure = bool(replan_on_tool_failure)
        self.replan_on_evidence_conflict = bool(replan_on_evidence_conflict)
        if isinstance(max_plan_versions, bool) or not isinstance(max_plan_versions, int) or max_plan_versions < 1:
            raise ValueError("max_plan_versions must be positive")
        self.max_plan_versions = max_plan_versions

    def decide(
        self,
        plan: Plan,
        *,
        failed_step_id: str | None = None,
        tool_failed: bool = False,
        evidence_conflict: bool = False,
    ) -> ReplanDecision:
        if plan.version >= self.max_plan_versions:
            return ReplanDecision(False, "plan version budget exhausted", failed_step_id)
        if evidence_conflict and self.replan_on_evidence_conflict:
            return ReplanDecision(True, "new evidence contradicts current plan assumptions", failed_step_id)
        if tool_failed and self.replan_on_tool_failure:
            return ReplanDecision(True, "tool execution invalidated current plan", failed_step_id)
        if failed_step_id is not None:
            step = plan.step(failed_step_id)
            if step.status is StepStatus.FAILED:
                dependents = [candidate for candidate in plan.steps if failed_step_id in candidate.dependencies]
                if dependents:
                    return ReplanDecision(True, "failed dependency blocks downstream work", failed_step_id)
        return ReplanDecision(False, "current plan remains viable", failed_step_id)


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["rationale", "steps"],
    "properties": {
        "rationale": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title", "description", "dependencies", "risk"],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "tool": {"type": ["string", "null"]},
                    "arguments": {"type": "object"},
                    "expected_outcome": {"type": "string"},
                    "verification": {"type": "string"},
                    "risk": {"type": "string"},
                    "max_attempts": {"type": "integer"},
                },
            },
        },
    },
}


class ModelPlanParser:
    """Strict parser for untrusted model plan proposals."""

    def __init__(self, *, maximum_steps: int = 32) -> None:
        if maximum_steps < 1:
            raise ValueError("maximum_steps must be positive")
        self.maximum_steps = maximum_steps

    def parse(self, goal: Goal, content: str) -> Plan:
        if not isinstance(content, str) or not content.strip():
            raise PlanningError("model plan response is empty")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise PlanningError("model plan response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise PlanningError("plan response must be an object")
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise PlanningError("plan requires a non-empty steps array")
        if len(raw_steps) > self.maximum_steps:
            raise PlanningError("plan exceeds step limit")
        steps: list[PlanStep] = []
        for index, raw in enumerate(raw_steps, start=1):
            if not isinstance(raw, dict):
                raise PlanningError(f"step {index} must be an object")
            step_id = self._step_id(raw.get("id"), index)
            try:
                risk = RiskTier(str(raw.get("risk", RiskTier.READ_ONLY.value)))
            except ValueError as exc:
                raise PlanningError(f"step {step_id} has invalid risk tier") from exc
            dependencies = raw.get("dependencies", [])
            if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
                raise PlanningError(f"step {step_id} dependencies must be strings")
            tool = raw.get("tool")
            if tool is not None and not isinstance(tool, str):
                raise PlanningError(f"step {step_id} tool must be string or null")
            arguments = raw.get("arguments", {})
            if not isinstance(arguments, dict):
                raise PlanningError(f"step {step_id} arguments must be an object")
            steps.append(
                PlanStep(
                    step_id=step_id,
                    title=str(raw.get("title", f"Step {index}")),
                    description=str(raw.get("description", "Execute the planned step.")),
                    dependencies=tuple(dependencies),
                    tool=tool,
                    arguments=json_safe(arguments),
                    expected_outcome=str(raw.get("expected_outcome", "")),
                    verification=str(raw.get("verification", "")),
                    risk=risk,
                    max_attempts=int(raw.get("max_attempts", 2)),
                )
            )
        plan_id = stable_id("plan", {"goal": goal.goal_id, "steps": [step.step_id for step in steps]})
        return Plan(
            plan_id=plan_id,
            goal_id=goal.goal_id,
            steps=tuple(steps),
            rationale=str(payload.get("rationale", "")),
        )

    @staticmethod
    def _step_id(raw: Any, index: int) -> str:
        if isinstance(raw, str) and raw.strip():
            candidate = raw.strip()
        else:
            candidate = f"step-{index}"
        candidate = re.sub(r"[^A-Za-z0-9._:/-]", "-", candidate)[:128]
        if not candidate or not candidate[0].isalnum():
            candidate = f"step-{index}"
        return require_id("step_id", candidate)


def retain_completed_steps(old: Plan, proposed: Plan) -> Plan:
    """Carry verified completion forward only when step semantics are unchanged."""
    old_by_id = {step.step_id: step for step in old.steps}
    revised: list[PlanStep] = []
    for step in proposed.steps:
        prior = old_by_id.get(step.step_id)
        if prior is None or prior.status not in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}:
            revised.append(step)
            continue
        semantic_old = (
            prior.title,
            prior.description,
            prior.dependencies,
            prior.tool,
            dict(prior.arguments),
            prior.expected_outcome,
            prior.verification,
            prior.risk,
        )
        semantic_new = (
            step.title,
            step.description,
            step.dependencies,
            step.tool,
            dict(step.arguments),
            step.expected_outcome,
            step.verification,
            step.risk,
        )
        revised.append(step.with_status(prior.status) if semantic_old == semantic_new else step)
    return Plan(
        plan_id=proposed.plan_id,
        goal_id=proposed.goal_id,
        steps=tuple(revised),
        version=max(old.version + 1, proposed.version),
        rationale=proposed.rationale,
        created_at=proposed.created_at,
    )
