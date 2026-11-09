"""Memory/recall decay characterization across controlled delay horizons."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class MemoryDecayTrial:
    trial_id: str
    memory_digest: str
    delay_steps: int
    recall_score: float
    reset_between: bool = False

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise ReverseEngineeringError("memory decay trial requires identity")
        if not is_sha256_digest(self.memory_digest):
            raise ReverseEngineeringError("memory_digest must be a sha256 hex digest")
        if self.delay_steps < 0:
            raise ReverseEngineeringError("delay_steps must be non-negative")
        if not isfinite(self.recall_score) or not 0.0 <= self.recall_score <= 1.0:
            raise ReverseEngineeringError("recall_score must be within [0, 1]")


@dataclass(frozen=True)
class MemoryDecayReport:
    trial_count: int
    baseline_recall: float
    terminal_recall: float
    recall_drop: float
    half_recall_delay: int | None
    mean_adjacent_drop: float
    reset_trial_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "trial_count": self.trial_count,
            "baseline_recall": self.baseline_recall,
            "terminal_recall": self.terminal_recall,
            "recall_drop": self.recall_drop,
            "half_recall_delay": self.half_recall_delay,
            "mean_adjacent_drop": self.mean_adjacent_drop,
            "reset_trial_count": self.reset_trial_count,
            "digest": self.digest,
        }


def analyze_memory_decay(
    trials: Sequence[MemoryDecayTrial],
) -> MemoryDecayReport:
    if len(trials) < 2:
        raise ReverseEngineeringError("memory decay requires at least two trials")
    memory_digests = {trial.memory_digest for trial in trials}
    if len(memory_digests) != 1:
        raise ReverseEngineeringError("memory decay trials must share memory_digest")
    ordered = sorted(trials, key=lambda item: (item.delay_steps, item.trial_id))
    delays = [item.delay_steps for item in ordered]
    if len(delays) != len(set(delays)):
        raise ReverseEngineeringError("memory decay delay_steps must be unique")
    baseline = ordered[0].recall_score
    half_threshold = baseline * 0.5
    half = [
        item.delay_steps
        for item in ordered
        if item.recall_score <= half_threshold
    ]
    adjacent_drops = [
        left.recall_score - right.recall_score
        for left, right in zip(ordered, ordered[1:])
    ]
    payload = {
        "memory_digest": next(iter(memory_digests)),
        "trials": [
            {
                "trial_id": item.trial_id,
                "delay_steps": item.delay_steps,
                "recall_score": item.recall_score,
                "reset_between": item.reset_between,
            }
            for item in ordered
        ],
    }
    return MemoryDecayReport(
        trial_count=len(ordered),
        baseline_recall=baseline,
        terminal_recall=ordered[-1].recall_score,
        recall_drop=baseline - ordered[-1].recall_score,
        half_recall_delay=min(half) if half else None,
        mean_adjacent_drop=sum(adjacent_drops) / len(adjacent_drops),
        reset_trial_count=sum(item.reset_between for item in ordered),
        digest=stable_digest(payload),
    )
