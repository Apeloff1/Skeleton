"""Deterministic iteration-level scheduler for prefill/decode coexistence."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json


class InferencePhase(str, Enum):
    PREFILL = "prefill"
    DECODE = "decode"


@dataclass(frozen=True, slots=True)
class IterationWork:
    request_id: str
    phase: InferencePhase
    remaining_tokens: int
    priority: int = 0
    age: int = 0

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id required")
        if isinstance(self.remaining_tokens, bool) or not isinstance(self.remaining_tokens, int) or self.remaining_tokens <= 0:
            raise ValueError("positive remaining_tokens required")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("integer priority required")
        if isinstance(self.age, bool) or not isinstance(self.age, int) or self.age < 0:
            raise ValueError("non-negative age required")


@dataclass(frozen=True, slots=True)
class IterationSlice:
    request_id: str
    phase: InferencePhase
    tokens: int


@dataclass(frozen=True, slots=True)
class IterationPlan:
    slices: tuple[IterationSlice, ...]
    used_tokens: int
    deferred: tuple[str, ...]
    digest: str


class IterationScheduler:
    def __init__(
        self,
        *,
        token_budget: int = 2048,
        prefill_quantum: int = 512,
        decode_priority_boost: int = 100,
        max_age_boost: int = 1000,
    ) -> None:
        for name, value in (
            ("token_budget", token_budget),
            ("prefill_quantum", prefill_quantum),
            ("decode_priority_boost", decode_priority_boost),
            ("max_age_boost", max_age_boost),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"positive {name} required")
        self.token_budget = token_budget
        self.prefill_quantum = prefill_quantum
        self.decode_priority_boost = decode_priority_boost
        self.max_age_boost = max_age_boost

    def _score(self, work: IterationWork) -> tuple[int, int, str]:
        phase_boost = self.decode_priority_boost if work.phase is InferencePhase.DECODE else 0
        effective = work.priority + phase_boost + min(work.age, self.max_age_boost)
        return (-effective, -work.age, work.request_id)

    def plan(self, work: tuple[IterationWork, ...]) -> IterationPlan:
        ids = [item.request_id for item in work]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate iteration request identity")
        remaining_budget = self.token_budget
        slices: list[IterationSlice] = []
        deferred: list[str] = []
        for item in sorted(work, key=self._score):
            if remaining_budget <= 0:
                deferred.append(item.request_id)
                continue
            quantum = 1 if item.phase is InferencePhase.DECODE else self.prefill_quantum
            tokens = min(item.remaining_tokens, quantum, remaining_budget)
            if tokens <= 0:
                deferred.append(item.request_id)
                continue
            slices.append(IterationSlice(item.request_id, item.phase, tokens))
            remaining_budget -= tokens
        body = {
            "schema": "skeleton.ai.iteration-plan.v1",
            "slices": [
                {"request_id": s.request_id, "phase": s.phase.value, "tokens": s.tokens}
                for s in slices
            ],
            "used_tokens": self.token_budget - remaining_budget,
            "deferred": deferred,
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return IterationPlan(tuple(slices), self.token_budget - remaining_budget, tuple(deferred), digest)


__all__ = ["InferencePhase", "IterationPlan", "IterationScheduler", "IterationSlice", "IterationWork"]
