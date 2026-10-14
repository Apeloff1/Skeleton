"""State and memory behavior reconstruction from reset-controlled trials."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class StateTrial:
    trial_id: str
    sequence_id: str
    step: int
    input_digest: str
    output_digest: str
    reset_before: bool = False
    recall_marker: bool = False

    def __post_init__(self) -> None:
        if not self.trial_id or not self.sequence_id:
            raise ReverseEngineeringError("state trial identity is required")
        if self.step < 0:
            raise ReverseEngineeringError("state step must be non-negative")
        if len(self.input_digest) != 64 or len(self.output_digest) != 64:
            raise ReverseEngineeringError("state digests must be sha256 length")


@dataclass(frozen=True)
class StateMemoryReport:
    trial_count: int
    sequence_count: int
    reset_count: int
    recall_count: int
    recall_ratio: float
    repeated_input_divergence_ratio: float
    cross_reset_carryover_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "trial_count": self.trial_count,
            "sequence_count": self.sequence_count,
            "reset_count": self.reset_count,
            "recall_count": self.recall_count,
            "recall_ratio": self.recall_ratio,
            "repeated_input_divergence_ratio": self.repeated_input_divergence_ratio,
            "cross_reset_carryover_count": self.cross_reset_carryover_count,
            "digest": self.digest,
        }


def analyze_state_memory(trials: Sequence[StateTrial]) -> StateMemoryReport:
    if not trials:
        raise ReverseEngineeringError("state analysis requires trials")
    ordered = sorted(trials, key=lambda item: (item.sequence_id, item.step, item.trial_id))
    by_input: dict[str, set[str]] = {}
    for item in ordered:
        by_input.setdefault(item.input_digest, set()).add(item.output_digest)
    repeat_groups = [outputs for outputs in by_input.values() if len(outputs) >= 1]
    divergent = sum(1 for outputs in repeat_groups if len(outputs) > 1)
    divergence_ratio = round(divergent / len(repeat_groups), 12) if repeat_groups else 0.0

    recall_count = sum(1 for item in ordered if item.recall_marker)
    recall_ratio = round(recall_count / len(ordered), 12)
    carryover = 0
    for index, item in enumerate(ordered):
        if not item.reset_before or not item.recall_marker:
            continue
        previous = [
            prior
            for prior in ordered[:index]
            if prior.sequence_id == item.sequence_id and prior.step < item.step
        ]
        if previous:
            carryover += 1

    payload = {
        "trials": [
            {
                "trial_id": item.trial_id,
                "sequence_id": item.sequence_id,
                "step": item.step,
                "input_digest": item.input_digest,
                "output_digest": item.output_digest,
                "reset_before": item.reset_before,
                "recall_marker": item.recall_marker,
            }
            for item in ordered
        ]
    }
    return StateMemoryReport(
        trial_count=len(ordered),
        sequence_count=len({item.sequence_id for item in ordered}),
        reset_count=sum(1 for item in ordered if item.reset_before),
        recall_count=recall_count,
        recall_ratio=recall_ratio,
        repeated_input_divergence_ratio=divergence_ratio,
        cross_reset_carryover_count=carryover,
        digest=stable_digest(payload),
    )
