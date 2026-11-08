"""Perf budgets: absolute ceilings per workload metric, loaded from JSON."""
from __future__ import annotations

import json
import math
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
            if type(limit) not in (int, float) or not math.isfinite(limit) or limit < 0:
                raise ValueError(f"{self.workload}.{metric}: finite nonnegative budget required")

    def check(self, summary: Summary) -> List[BudgetViolation]:
        out = []
        for metric, limit in sorted(self.limits.items()):
            actual = summary.metric(metric)
            if actual > limit:
                out.append(BudgetViolation(self.workload, metric, float(limit), actual))
        return out


@dataclass(frozen=True)
class MissingBudgetedWorkload:
    workload: str

    def __str__(self) -> str:
        return f"{self.workload}: budgeted workload not measured"


@dataclass
class BudgetSet:
    budgets: Dict[str, Budget] = field(default_factory=dict)

    def check(self, summaries: Mapping[str, Summary]) -> List[BudgetViolation]:
        out: List[BudgetViolation] = []
        for name, budget in sorted(self.budgets.items()):
            if name not in summaries:
                out.append(MissingBudgetedWorkload(name))
            else:
                out.extend(budget.check(summaries[name]))
        return out


def load_budgets(source: Union[str, Path, Mapping]) -> BudgetSet:
    """Load ``{"version": 1, "workloads": {name: {metric: limit}}}``."""
    if isinstance(source, Mapping):
        data = source
    else:
        def unique(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError("duplicate budget JSON key")
                out[key] = value
            return out
        data = json.loads(Path(source).read_text(encoding="utf-8"),
                          object_pairs_hook=unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite budget JSON")))
    if type(data) is not dict or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("budget file must declare version 1")
    workloads = data.get("workloads")
    if not isinstance(workloads, Mapping):
        raise ValueError("budget file needs a 'workloads' mapping")
    if not 1 <= len(workloads) <= 256 or any(
            type(n) is not str or not 1 <= len(n) <= 128 or type(l) is not dict or not l
            for n, l in workloads.items()):
        raise ValueError("unbounded or empty workload budget inventory")
    return BudgetSet({n: Budget(n, dict(l)) for n, l in workloads.items()})
