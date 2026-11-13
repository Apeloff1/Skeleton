"""B074 — Performance budget gates.

Success criterion: "CPU/GPU/memory/frame/load/network budgets are
target-specific and regression-gated."

Each target (e.g. ``desktop``, ``mobile``, ``web``) has absolute ceilings per
:class:`Metric`. :class:`BudgetGate` checks samples against them (using a
percentile, not the mean) and against a baseline with an allowed regression
fraction. Missing samples for a budgeted metric fail closed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence


class BudgetError(ValueError):
    pass


class Metric(str, Enum):
    CPU_MS = "cpu_ms"
    GPU_MS = "gpu_ms"
    MEMORY_MB = "memory_mb"
    FRAME_MS = "frame_ms"
    LOAD_MS = "load_ms"
    NETWORK_KB = "network_kb"


@dataclass(frozen=True)
class Budget:
    metric: Metric
    ceiling: float
    percentile: float = 95.0
    max_regression: float = 0.05

    def __post_init__(self):
        if self.ceiling <= 0:
            raise BudgetError("ceiling must be positive")
        if not 0 < self.percentile <= 100:
            raise BudgetError("percentile must be in (0, 100]")
        if self.max_regression < 0:
            raise BudgetError("max_regression must be >= 0")


@dataclass
class TargetBudgets:
    target: str
    budgets: Dict[Metric, Budget] = field(default_factory=dict)

    def add(self, b: Budget) -> "TargetBudgets":
        if b.metric in self.budgets:
            raise BudgetError(f"duplicate budget for {b.metric.value}")
        self.budgets[b.metric] = b
        return self


def percentile(samples: Sequence[float], p: float) -> float:
    if not samples:
        raise BudgetError("no samples")
    s = sorted(samples)
    k = max(0, math.ceil(p / 100 * len(s)) - 1)
    return s[k]


@dataclass(frozen=True)
class GateResult:
    target: str
    passed: bool
    violations: tuple
    measured: Mapping[str, float]


class BudgetGate:
    def __init__(self, targets: Sequence[TargetBudgets]) -> None:
        self.targets = {t.target: t for t in targets}

    def check(self, target: str, samples: Mapping[Metric, Sequence[float]],
              baseline: Optional[Mapping[Metric, float]] = None) -> GateResult:
        if target not in self.targets:
            raise BudgetError(f"unknown target {target!r}")
        violations: List[str] = []
        measured: Dict[str, float] = {}
        for metric, b in sorted(self.targets[target].budgets.items(), key=lambda kv: kv[0].value):
            data = samples.get(metric)
            if not data:
                violations.append(f"{metric.value}: missing samples")
                continue
            v = percentile(data, b.percentile)
            measured[metric.value] = v
            if v > b.ceiling:
                violations.append(f"{metric.value}: p{b.percentile:g}={v:g} > ceiling {b.ceiling:g}")
            if baseline and metric in baseline and baseline[metric] > 0:
                limit = baseline[metric] * (1 + b.max_regression)
                if v > limit:
                    violations.append(f"{metric.value}: regression {v:g} > {limit:g}")
        return GateResult(target, not violations, tuple(violations), measured)
