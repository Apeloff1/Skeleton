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

    def mean(self) -> float:
        return sum(self.outcomes) / len(self.outcomes) if self.outcomes else 0.0

    def std(self) -> float:
        if len(self.outcomes) < 2:
            return 0.0
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
        self.alpha = significance_level
        self._experiments: Dict[str, Experiment] = {}

    def create(self, name: str, variants: Optional[List[str]] = None,
               weights: Optional[List[int]] = None) -> Experiment:
        names = variants or ["control", "treatment"]
        ws = weights or [100 // len(names)] * len(names)
        exp = Experiment(
            name=name,
            variants={n: Variant(name=n, weight=w) for n, w in zip(names, ws)},
            created_ns=time.time_ns(),
        )
        self._experiments[name] = exp
        return exp

    def assign(self, experiment: str, subject_id: str) -> Optional[str]:
        exp = self._experiments.get(experiment)
        if not exp or exp.concluded:
            return exp.winner if exp else None
        digest = int(hashlib.sha256(f"{experiment}:{subject_id}".encode()).hexdigest(), 16)
        roll = digest % 100
        acc = 0
        total = sum(v.weight for v in exp.variants.values())
        for name, v in exp.variants.items():
            acc += (v.weight / total) * 100
            if roll < acc:
                return name
        return list(exp.variants.keys())[-1]

    def record(self, experiment: str, variant: str, outcome: float) -> None:
        exp = self._experiments[experiment]
        if variant in exp.variants:
            exp.variants[variant].outcomes.append(outcome)

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
                    "variants": {v: {"weight": v2.weight, "samples": len(v2.outcomes), "mean": round(v2.mean(), 4)} for v, v2 in e.variants.items()},
                    "concluded": e.concluded,
                    "winner": e.winner,
                }
                for n, e in self._experiments.items()
            },
        }
