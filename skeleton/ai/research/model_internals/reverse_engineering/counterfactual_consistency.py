"""Counterfactual consistency for controlled paired-output experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class CounterfactualPair:
    pair_id: str
    base_input_digest: str
    counterfactual_input_digest: str
    base_output_digest: str
    counterfactual_output_digest: str
    expected_change: bool

    def __post_init__(self) -> None:
        if not self.pair_id:
            raise ReverseEngineeringError("counterfactual pair requires pair_id")
        for digest in (
            self.base_input_digest,
            self.counterfactual_input_digest,
            self.base_output_digest,
            self.counterfactual_output_digest,
        ):
            if not is_sha256_digest(digest):
                raise ReverseEngineeringError("counterfactual digests must be sha256 hex digests")


@dataclass(frozen=True)
class CounterfactualConsistencyReport:
    pair_count: int
    expected_change_count: int
    expected_invariance_count: int
    observed_change_count: int
    change_sensitivity: float | None
    invariance_specificity: float | None
    overall_consistency: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "pair_count": self.pair_count,
            "expected_change_count": self.expected_change_count,
            "expected_invariance_count": self.expected_invariance_count,
            "observed_change_count": self.observed_change_count,
            "change_sensitivity": self.change_sensitivity,
            "invariance_specificity": self.invariance_specificity,
            "overall_consistency": self.overall_consistency,
            "digest": self.digest,
        }


def analyze_counterfactual_consistency(
    pairs: Sequence[CounterfactualPair],
) -> CounterfactualConsistencyReport:
    if not pairs:
        raise ReverseEngineeringError("counterfactual consistency requires pairs")
    ids = [pair.pair_id for pair in pairs]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("counterfactual pair ids must be unique")
    expected_change = [pair for pair in pairs if pair.expected_change]
    expected_invariance = [pair for pair in pairs if not pair.expected_change]
    changed = {
        pair.pair_id: pair.base_output_digest != pair.counterfactual_output_digest
        for pair in pairs
    }
    change_hits = sum(changed[pair.pair_id] for pair in expected_change)
    invariance_hits = sum(not changed[pair.pair_id] for pair in expected_invariance)
    consistent = change_hits + invariance_hits
    payload = {
        "pairs": [
            {
                "pair_id": pair.pair_id,
                "base_input_digest": pair.base_input_digest,
                "counterfactual_input_digest": pair.counterfactual_input_digest,
                "base_output_digest": pair.base_output_digest,
                "counterfactual_output_digest": pair.counterfactual_output_digest,
                "expected_change": pair.expected_change,
            }
            for pair in sorted(pairs, key=lambda item: item.pair_id)
        ]
    }
    return CounterfactualConsistencyReport(
        pair_count=len(pairs),
        expected_change_count=len(expected_change),
        expected_invariance_count=len(expected_invariance),
        observed_change_count=sum(changed.values()),
        change_sensitivity=(change_hits / len(expected_change) if expected_change else None),
        invariance_specificity=(
            invariance_hits / len(expected_invariance) if expected_invariance else None
        ),
        overall_consistency=consistent / len(pairs),
        digest=stable_digest(payload),
    )
