"""Dependency-aware command pipelines over the canonical ``ShellExecutor``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping

from skeleton.shells.capabilities import ShellCapability
from skeleton.shells.errors import PipelineError, ShellErrorCode, ShellErrorContext
from skeleton.shells.executor import ExecutionOutcome, ShellExecutor
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand
from skeleton.shells.session import ShellSession


class StepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PipelineStep:
    step_id: str
    command: ShellCommand
    depends_on: frozenset[str] = frozenset()
    retry: RetryPolicy | None = None
    continue_on_failure: bool = False

    def __post_init__(self) -> None:
        if not self.step_id or len(self.step_id) > 128:
            raise ValueError("pipeline step_id must be non-empty and bounded")
        if self.step_id in self.depends_on:
            raise ValueError("pipeline step may not depend on itself")
        object.__setattr__(self, "depends_on", frozenset(self.depends_on))


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    steps: tuple[PipelineStep, ...]
    max_steps: int = 256

    def __post_init__(self) -> None:
        steps = tuple(self.steps)
        if not self.name or len(self.name) > 128:
            raise ValueError("pipeline name must be non-empty and bounded")
        if self.max_steps <= 0 or len(steps) > self.max_steps:
            raise ValueError("pipeline step count exceeds bound")
        ids = [step.step_id for step in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("pipeline step IDs must be unique")
        known = set(ids)
        for step in steps:
            missing = step.depends_on - known
            if missing:
                raise ValueError(f"pipeline step {step.step_id!r} has unknown dependencies")
        self._validate_acyclic(steps)
        object.__setattr__(self, "steps", steps)

    @staticmethod
    def _validate_acyclic(steps: tuple[PipelineStep, ...]) -> None:
        deps = {step.step_id: set(step.depends_on) for step in steps}
        remaining = set(deps)
        resolved: set[str] = set()
        while remaining:
            ready = {step_id for step_id in remaining if deps[step_id] <= resolved}
            if not ready:
                raise ValueError("pipeline dependency graph contains a cycle")
            remaining -= ready
            resolved |= ready

    def by_id(self) -> Mapping[str, PipelineStep]:
        return MappingProxyType({step.step_id: step for step in self.steps})

    def topological_order(self) -> tuple[str, ...]:
        deps = {step.step_id: set(step.depends_on) for step in self.steps}
        remaining = set(deps)
        resolved: set[str] = set()
        order: list[str] = []
        while remaining:
            ready = sorted(step_id for step_id in remaining if deps[step_id] <= resolved)
            if not ready:
                raise RuntimeError("validated pipeline unexpectedly became cyclic")
            order.extend(ready)
            remaining -= set(ready)
            resolved |= set(ready)
        return tuple(order)


@dataclass(frozen=True)
class PipelineStepResult:
    step_id: str
    state: StepState
    outcome: ExecutionOutcome | None = None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.state is StepState.SUCCEEDED


@dataclass(frozen=True)
class PipelineResult:
    name: str
    steps: Mapping[str, PipelineStepResult]
    order: tuple[str, ...]

    @property
    def ok(self) -> bool:
        terminal = {StepState.SUCCEEDED, StepState.SKIPPED}
        return all(result.state in terminal for result in self.steps.values())

    def failures(self) -> tuple[str, ...]:
        return tuple(sorted(step_id for step_id, result in self.steps.items() if result.state is StepState.FAILED))

    def blocked(self) -> tuple[str, ...]:
        return tuple(sorted(step_id for step_id, result in self.steps.items() if result.state is StepState.BLOCKED))


class PipelineExecutor:
    def __init__(self, executor: ShellExecutor) -> None:
        self.executor = executor

    def execute(
        self,
        spec: PipelineSpec,
        *,
        session: ShellSession | None = None,
        stop_on_failure: bool = True,
    ) -> PipelineResult:
        self.executor.grant.require(ShellCapability.PIPELINE, detail="pipeline execution requires capability")
        by_id = spec.by_id()
        results: dict[str, PipelineStepResult] = {}
        order: list[str] = []
        hard_stop = False

        for step_id in spec.topological_order():
            step = by_id[step_id]
            order.append(step_id)
            if hard_stop:
                results[step_id] = PipelineStepResult(step_id, StepState.SKIPPED, reason="pipeline stopped after failure")
                continue
            dependency_results = [results[dependency] for dependency in step.depends_on]
            failed_dependencies = [
                result.step_id
                for result in dependency_results
                if result.state not in {StepState.SUCCEEDED, StepState.SKIPPED}
            ]
            if failed_dependencies:
                results[step_id] = PipelineStepResult(
                    step_id,
                    StepState.BLOCKED,
                    reason="failed dependencies: " + ", ".join(sorted(failed_dependencies)),
                )
                continue
            try:
                outcome = self.executor.execute(step.command, retry=step.retry, session=session)
            except Exception as exc:
                results[step_id] = PipelineStepResult(step_id, StepState.FAILED, reason=type(exc).__name__)
                if stop_on_failure and not step.continue_on_failure:
                    hard_stop = True
                continue
            state = StepState.SUCCEEDED if outcome.ok else StepState.FAILED
            results[step_id] = PipelineStepResult(step_id, state, outcome=outcome)
            if state is StepState.FAILED and stop_on_failure and not step.continue_on_failure:
                hard_stop = True

        return PipelineResult(spec.name, MappingProxyType(results), tuple(order))


def pipeline_from_commands(name: str, commands: Iterable[ShellCommand]) -> PipelineSpec:
    steps: list[PipelineStep] = []
    previous: str | None = None
    for index, command in enumerate(commands, start=1):
        step_id = f"step-{index:03d}"
        dependencies = frozenset() if previous is None else frozenset({previous})
        steps.append(PipelineStep(step_id, command, depends_on=dependencies))
        previous = step_id
    return PipelineSpec(name, tuple(steps))
