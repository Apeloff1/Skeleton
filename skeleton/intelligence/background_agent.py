"""Bounded background agent.

This is the control loop for assistant.background_agent: a goal, a planner,
and an executor. The loop enforces the step budget and the child fan-out
before any tool is called. Writes stay off unless the run was opened with
approval. An illegal plan does not reach the executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


class AgentError(ValueError):
    """The agent was constructed or planned incorrectly."""


READ_TOOLS = frozenset({"network.search", "repository.query"})
WRITE_TOOLS = frozenset({"sandbox.compile", "artifact.package"})


@dataclass(frozen=True)
class AgentStep:
    tool: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    children: tuple["AgentStep", ...] = ()


@dataclass(frozen=True)
class AgentResult:
    status: str
    steps: int
    calls: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "steps": self.steps,
            "calls": list(self.calls),
            "reason": self.reason,
        }


class BackgroundAgent:
    """Run a planner until it stops, the budget ends, or a step is not allowed."""

    def __init__(self, *, max_steps: int = 8, max_children: int = 2, allow_writes: bool = False) -> None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
            raise AgentError("max_steps must be a positive integer")
        if isinstance(max_children, bool) or not isinstance(max_children, int) or max_children < 0:
            raise AgentError("max_children must be a non-negative integer")
        if not isinstance(allow_writes, bool):
            raise AgentError("allow_writes must be a bool")
        self.max_steps = max_steps
        self.max_children = max_children
        self.allow_writes = allow_writes
        self.allowed = READ_TOOLS | (WRITE_TOOLS if allow_writes else frozenset())

    def run(
        self,
        goal: str,
        planner: Callable[[str, tuple[str, ...]], AgentStep | None],
        executor: Callable[[AgentStep], str],
    ) -> AgentResult:
        if not isinstance(goal, str) or not goal.strip():
            raise AgentError("goal is required")
        if not callable(planner) or not callable(executor):
            raise AgentError("planner and executor are required")
        calls: list[str] = []
        used = 0
        while used < self.max_steps:
            step = planner(goal, tuple(calls))
            if step is None:
                return AgentResult("completed", used, tuple(calls), "planner stopped")
            problem = self._problem(step)
            if problem is not None:
                return AgentResult("blocked", used, tuple(calls), problem)
            cost = self._cost(step)
            if used + cost > self.max_steps:
                return AgentResult("budget", used, tuple(calls), "step would exceed the step budget")
            self._execute(step, executor, calls)
            used += cost
        return AgentResult("budget", used, tuple(calls), "step budget exhausted")

    def _problem(self, step: AgentStep, *, depth: int = 0) -> str | None:
        if not isinstance(step, AgentStep):
            return "step must be an AgentStep"
        if depth > 1:
            return "child fan-out cannot nest"
        if step.tool not in self.allowed:
            return f"tool {step.tool} is not in the allow profile"
        if not isinstance(step.arguments, Mapping):
            return "arguments must be a mapping"
        if len(step.children) > self.max_children:
            return "child fan-out exceeds the bound"
        for child in step.children:
            problem = self._problem(child, depth=depth + 1)
            if problem is not None:
                return problem
        return None

    def _cost(self, step: AgentStep) -> int:
        return 1 + sum(self._cost(child) for child in step.children)

    def _execute(self, step: AgentStep, executor: Callable[[AgentStep], str], calls: list[str]) -> None:
        receipt = executor(step)
        if not isinstance(receipt, str) or not receipt:
            raise AgentError("executor must return a non-empty receipt")
        calls.append(step.tool)
        for child in step.children:
            self._execute(child, executor, calls)


__all__ = ["AgentError", "AgentResult", "AgentStep", "BackgroundAgent", "READ_TOOLS", "WRITE_TOOLS"]
