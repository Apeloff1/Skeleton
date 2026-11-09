"""Per-tool input and output guardrails for AI shell actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
from typing import Callable

from skeleton.shells.ai.observation import AIObservation
from skeleton.shells.ai.types import AIAction


class ToolGuardStage(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True)
class ToolGuardDecision:
    allowed: bool
    code: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"allowed": self.allowed, "code": self.code, "message": self.message}


class ToolGuardTripwire(RuntimeError):
    def __init__(self, decision: ToolGuardDecision) -> None:
        self.decision = decision
        super().__init__(decision.message or decision.code or "AI tool guardrail blocked call")


InputGuard = Callable[[AIAction], ToolGuardDecision]
OutputGuard = Callable[[AIAction, AIObservation], ToolGuardDecision]


class AIToolGuardRegistry:
    """Every registered guard runs; any denial trips the tool call."""

    def __init__(self, *, max_guards_per_command: int = 32) -> None:
        if max_guards_per_command <= 0:
            raise ValueError("max_guards_per_command must be positive")
        self.max_guards_per_command = max_guards_per_command
        self._input: dict[str, list[InputGuard]] = {}
        self._output: dict[str, list[OutputGuard]] = {}
        self._lock = threading.RLock()

    def register_input(self, command: str, guard: InputGuard) -> None:
        if not callable(guard):
            raise TypeError("input guard must be callable")
        with self._lock:
            guards = self._input.setdefault(command, [])
            if len(guards) >= self.max_guards_per_command:
                raise RuntimeError("input guard capacity exhausted")
            guards.append(guard)

    def register_output(self, command: str, guard: OutputGuard) -> None:
        if not callable(guard):
            raise TypeError("output guard must be callable")
        with self._lock:
            guards = self._output.setdefault(command, [])
            if len(guards) >= self.max_guards_per_command:
                raise RuntimeError("output guard capacity exhausted")
            guards.append(guard)

    def check_input(self, action: AIAction) -> tuple[ToolGuardDecision, ...]:
        with self._lock:
            guards = tuple(self._input.get(action.command, ()))
        decisions = []
        for guard in guards:
            decision = guard(action)
            if not isinstance(decision, ToolGuardDecision):
                raise TypeError("input guard must return ToolGuardDecision")
            decisions.append(decision)
            if not decision.allowed:
                raise ToolGuardTripwire(decision)
        return tuple(decisions)

    def check_output(
        self,
        action: AIAction,
        observation: AIObservation,
    ) -> tuple[ToolGuardDecision, ...]:
        with self._lock:
            guards = tuple(self._output.get(action.command, ()))
        decisions = []
        for guard in guards:
            decision = guard(action, observation)
            if not isinstance(decision, ToolGuardDecision):
                raise TypeError("output guard must return ToolGuardDecision")
            decisions.append(decision)
            if not decision.allowed:
                raise ToolGuardTripwire(decision)
        return tuple(decisions)
