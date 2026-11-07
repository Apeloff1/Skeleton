"""Perf budgets: absolute ceilings per workload metric, loaded from JSON."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Union

from .stats import Summary

ALLOWED_METRICS = frozenset(
    {"mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms", "error_rate", "drift_ratio"}
)


@dataclass(frozen=True)
class BudgetViolation:
    workload: str
    metric: str
    limit: float
    actual: float

    def __str__(self) -> str:
        return f"{self.workload}.{self.metric}: {self.actual:.3f} > budget {self.limit:.3f}"


@dataclass(frozen=True)
class Budget:
    workload: str
    limits: Mapping[str, float]

    def __post_init__(self) -> None:
        for metric, limit in self.limits.items():
            if metric not in ALLOWED_METRICS:
                raise ValueError(f"{self.workload}: unknown budget metric {metric!r}")
            if not isinstance(limit, (int, float)) or limit < 0:
                raise ValueError(f"{self.workload}.{metric}: limit must be >= 0")

    def check(self, summary: Summary) -> List[BudgetViolation]:
        out = []
        for metric, limit in sorted(self.limits.items()):
            actual = summary.metric(metric)
            if actual > limit:
                out.append(BudgetViolation(self.workload, metric, float(limit), actual))
        return out


@dataclass
class BudgetSet:
    budgets: Dict[str, Budget] = field(default_factory=dict)

    def check(self, summaries: Mapping[str, Summary]) -> List[BudgetViolation]:
        out: List[BudgetViolation] = []
        for name, budget in sorted(self.budgets.items()):
            if name in summaries:
                out.extend(budget.check(summaries[name]))
        return out


def load_budgets(source: Union[str, Path, Mapping]) -> BudgetSet:
    """Load ``{"version": 1, "workloads": {name: {metric: limit}}}``."""
    if isinstance(source, Mapping):
        data = source
    else:
        data = json.loads(Path(source).read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("budget file must declare version 1")
    workloads = data.get("workloads")
    if not isinstance(workloads, Mapping):
        raise ValueError("budget file needs a 'workloads' mapping")
    return BudgetSet({n: Budget(n, dict(l)) for n, l in workloads.items()})
