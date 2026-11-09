"""Adversarial robustness summaries for paired reverse-engineering probes."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class AdversarialProbePair:
    pair_id: str
    probe_digest: str
    baseline_score: float
    adversarial_score: float
    baseline_output_digest: str
    adversarial_output_digest: str

    def __post_init__(self) -> None:
        if not self.pair_id:
            raise ReverseEngineeringError("adversarial probe pair requires identity")
        for digest in (
            self.probe_digest,
            self.baseline_output_digest,
            self.adversarial_output_digest,
        ):
            if not is_sha256_digest(digest):
                raise ReverseEngineeringError("adversarial probe digests must be sha256 hex digests")
        if not isfinite(self.baseline_score) or not isfinite(self.adversarial_score):
            raise ReverseEngineeringError("adversarial probe scores must be finite")


@dataclass(frozen=True)
class AdversarialProbeReport:
    pair_count: int
    mean_score_drop: float
    mean_absolute_score_change: float
    output_change_ratio: float
    non_degrading_ratio: float
    worst_score_drop: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "pair_count": self.pair_count,
            "mean_score_drop": self.mean_score_drop,
            "mean_absolute_score_change": self.mean_absolute_score_change,
            "output_change_ratio": self.output_change_ratio,
            "non_degrading_ratio": self.non_degrading_ratio,
            "worst_score_drop": self.worst_score_drop,
            "digest": self.digest,
        }


def analyze_adversarial_probe_robustness(
    pairs: Sequence[AdversarialProbePair],
) -> AdversarialProbeReport:
    if not pairs:
        raise ReverseEngineeringError("adversarial probe analysis requires pairs")
    ids = [pair.pair_id for pair in pairs]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("adversarial probe pair ids must be unique")
    probe_digests = {pair.probe_digest for pair in pairs}
    if len(probe_digests) != 1:
        raise ReverseEngineeringError("adversarial probe pairs must share probe_digest")
    drops = [pair.baseline_score - pair.adversarial_score for pair in pairs]
    payload = {
        "probe_digest": next(iter(probe_digests)),
        "pairs": [
            {
                "pair_id": pair.pair_id,
                "baseline_score": pair.baseline_score,
                "adversarial_score": pair.adversarial_score,
                "baseline_output_digest": pair.baseline_output_digest,
                "adversarial_output_digest": pair.adversarial_output_digest,
            }
            for pair in sorted(pairs, key=lambda item: item.pair_id)
        ],
    }
    return AdversarialProbeReport(
        pair_count=len(pairs),
        mean_score_drop=sum(drops) / len(drops),
        mean_absolute_score_change=sum(abs(value) for value in drops) / len(drops),
        output_change_ratio=sum(
            pair.baseline_output_digest != pair.adversarial_output_digest
            for pair in pairs
        ) / len(pairs),
        non_degrading_ratio=sum(value <= 0.0 for value in drops) / len(drops),
        worst_score_drop=max(drops),
        digest=stable_digest(payload),
    )
