"""Experiment tracker — A/B testing with statistical significance.

Defines experiments with control and treatment variants, assigns
subjects deterministically, records metric outcomes, and computes
significance (Welch t-test for means). Declares winners automatically
when significance is reached.
"""
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Variant:
    name: str
    weight: int = 50
    outcomes: List[float] = field(default_factory=list)

    def mean(self) -> float | None:
        if not self.outcomes:
            return None
        return sum(self.outcomes) / len(self.outcomes)

    def std(self) -> float | None:
        if len(self.outcomes) < 2:
            return None
        m = self.mean()
        return math.sqrt(sum((x - m) ** 2 for x in self.outcomes) / (len(self.outcomes) - 1))


@dataclass
class Experiment:
    name: str
    variants: Dict[str, Variant] = field(default_factory=dict)
    created_ns: int = 0
    concluded: bool = False
    winner: Optional[str] = None


class ExperimentTracker:
    """A/B experiment runner with significance testing."""

    def __init__(self, significance_level: float = 0.05):
        if isinstance(significance_level, bool) or not isinstance(significance_level, (int, float)) or not 0.0 < float(significance_level) < 1.0:
            raise ValueError("significance level must be in (0, 1)")
        self.alpha = float(significance_level)
        self._experiments: Dict[str, Experiment] = {}

    def create(self, name: str, variants: Optional[List[str]] = None,
               weights: Optional[List[int]] = None) -> Experiment:
        names = list(variants or ["control", "treatment"])
        if not names or any(not isinstance(item, str) or not item.strip() for item in names):
            raise ValueError("variants must be non-empty strings")
        if len(set(names)) != len(names):
            raise ValueError("variant names must be unique")
        if weights is None:
            ws = [1] * len(names)
        else:
            if len(weights) != len(names):
                raise ValueError("weights must match the variant list")
            if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in weights):
                raise ValueError("weights must be non-negative integers")
            if sum(weights) <= 0:
                raise ValueError("weights must sum to a positive total")
            ws = list(weights)
        exp = Experiment(
            name=name,
            variants={n: Variant(name=n, weight=w) for n, w in zip(names, ws)},
            created_ns=time.time_ns(),
        )
        self._experiments[name] = exp
        return exp

    def assign(self, experiment: str, subject_id: str) -> Optional[str]:
        if experiment not in self._experiments:
            raise KeyError(experiment)
        if not isinstance(subject_id, str) or not subject_id:
            raise ValueError("subject id is required")
        exp = self._experiments[experiment]
        if exp.concluded:
            return exp.winner
        digest = int(hashlib.sha256(f"{experiment}:{subject_id}".encode()).hexdigest(), 16)
        roll = digest % 100
        acc = 0.0
        total = sum(v.weight for v in exp.variants.values())
        for name, variant in exp.variants.items():
            acc += (variant.weight / total) * 100
            if roll < acc:
                return name
        return list(exp.variants.keys())[-1]

    def record(self, experiment: str, variant: str, outcome: float) -> None:
        if experiment not in self._experiments:
            raise KeyError(experiment)
        exp = self._experiments[experiment]
        if variant not in exp.variants:
            raise ValueError(f"unknown variant {variant!r}")
        if isinstance(outcome, bool) or not isinstance(outcome, (int, float)) or not math.isfinite(float(outcome)):
            raise ValueError("outcome must be finite")
        exp.variants[variant].outcomes.append(float(outcome))

    def significance(self, experiment: str) -> Dict[str, Any]:
        exp = self._experiments[experiment]
        names = list(exp.variants.keys())
        if len(names) < 2:
            return {"significant": False, "reason": "need two variants"}
        a = exp.variants[names[0]]
        b = exp.variants[names[1]]
        if len(a.outcomes) < 10 or len(b.outcomes) < 10:
            return {"significant": False, "reason": "insufficient samples", "samples": {names[0]: len(a.outcomes), names[1]: len(b.outcomes)}}
        ma, mb = a.mean(), b.mean()
        va = a.std() ** 2 / len(a.outcomes) if len(a.outcomes) else 0.0
        vb = b.std() ** 2 / len(b.outcomes) if len(b.outcomes) else 0.0
        denom = math.sqrt(va + vb)
        if denom == 0:
            return {"significant": False, "reason": "zero variance"}
        t_stat = abs(ma - mb) / denom
        p = 2 * (1 - self._normal_cdf(t_stat))
        return {
            "significant": p < self.alpha,
            "t_stat": round(t_stat, 3),
            "p_value": round(p, 5),
            "means": {names[0]: round(ma, 4), names[1]: round(mb, 4)},
            "samples": {names[0]: len(a.outcomes), names[1]: len(b.outcomes)},
        }

    def _normal_cdf(self, x: float) -> float:
        return (1 + math.erf(x / math.sqrt(2))) / 2

    def conclude(self, experiment: str) -> Dict[str, Any]:
        exp = self._experiments[experiment]
        sig = self.significance(experiment)
        if sig.get("significant"):
            means = sig["means"]
            exp.winner = max(means, key=means.get)
            exp.concluded = True
            return {"concluded": True, "winner": exp.winner, **sig}
        return {"concluded": False, **sig}

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "experiment-card",
            "experiments": {
                n: {
                    "variants": {
                        v: {
                            "weight": variant.weight,
                            "samples": len(variant.outcomes),
                            "mean": None if variant.mean() is None else round(variant.mean(), 4),
                        }
                        for v, variant in e.variants.items()
                    },
                    "concluded": e.concluded,
                    "winner": e.winner,
                }
                for n, e in self._experiments.items()
            },
        }
