"""Bounded planning budgets for model calls and proposal complexity."""

from __future__ import annotations

from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class AIBudgetLimit:
    max_model_calls: int = 8
    max_candidates: int = 8
    max_actions_proposed: int = 128
    max_critique_calls: int = 4
    max_verification_rounds: int = 2

    def __post_init__(self) -> None:
        for value in (
            self.max_model_calls,
            self.max_candidates,
            self.max_actions_proposed,
            self.max_critique_calls,
            self.max_verification_rounds,
        ):
            if value <= 0:
                raise ValueError("AI budget limits must be positive")


@dataclass(frozen=True)
class AIBudgetUsage:
    model_calls: int = 0
    candidates: int = 0
    actions_proposed: int = 0
    critique_calls: int = 0
    verification_rounds: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "model_calls": self.model_calls,
            "candidates": self.candidates,
            "actions_proposed": self.actions_proposed,
            "critique_calls": self.critique_calls,
            "verification_rounds": self.verification_rounds,
        }


class AIBudgetExceeded(RuntimeError):
    pass


class AIBudget:
    def __init__(self, limit: AIBudgetLimit | None = None) -> None:
        self.limit = limit or AIBudgetLimit()
        self._usage = AIBudgetUsage()
        self._lock = threading.RLock()

    def _replace(self, **changes: int) -> AIBudgetUsage:
        values = self._usage.to_dict()
        values.update(changes)
        usage = AIBudgetUsage(**values)
        if usage.model_calls > self.limit.max_model_calls:
            raise AIBudgetExceeded("model call budget exhausted")
        if usage.candidates > self.limit.max_candidates:
            raise AIBudgetExceeded("candidate budget exhausted")
        if usage.actions_proposed > self.limit.max_actions_proposed:
            raise AIBudgetExceeded("proposed action budget exhausted")
        if usage.critique_calls > self.limit.max_critique_calls:
            raise AIBudgetExceeded("critique call budget exhausted")
        if usage.verification_rounds > self.limit.max_verification_rounds:
            raise AIBudgetExceeded("verification round budget exhausted")
        self._usage = usage
        return usage

    def model_call(self, *, actions: int = 0, candidate: bool = True) -> AIBudgetUsage:
        if actions < 0:
            raise ValueError("actions may not be negative")
        with self._lock:
            return self._replace(
                model_calls=self._usage.model_calls + 1,
                candidates=self._usage.candidates + int(candidate),
                actions_proposed=self._usage.actions_proposed + actions,
            )

    def critique_call(self) -> AIBudgetUsage:
        with self._lock:
            return self._replace(critique_calls=self._usage.critique_calls + 1)

    def verification_round(self) -> AIBudgetUsage:
        with self._lock:
            return self._replace(
                verification_rounds=self._usage.verification_rounds + 1
            )

    def snapshot(self) -> AIBudgetUsage:
        with self._lock:
            return self._usage
