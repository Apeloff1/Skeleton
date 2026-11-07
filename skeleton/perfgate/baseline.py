"""Baseline snapshots and relative regression comparison."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Union

from .stats import Summary

# Metrics compared relatively; lower is better for all of them.
COMPARED = ("p50_ms", "p95_ms", "p99_ms", "mean_ms")
DEFAULT_TOLERANCE = 0.20  # 20% slower than baseline = regression
DEFAULT_NOISE_FLOOR_MS = 2.0  # ignore absolute deltas below this


@dataclass
class Baseline:
    workloads: Dict[str, Dict[str, float]] = field(default_factory=dict)
    meta: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_summaries(cls, summaries: Mapping[str, Summary],
                       meta: Optional[Dict[str, str]] = None) -> "Baseline":
        return cls({n: {m: s.metric(m) for m in COMPARED} for n, s in summaries.items()},
                   dict(meta or {}))

    def to_json(self) -> str:
        return json.dumps({"version": 1, "meta": self.meta, "workloads": self.workloads},
                          indent=2, sort_keys=True) + "\n"


def save_baseline(baseline: Baseline, path: Union[str, Path]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(baseline.to_json(), encoding="utf-8")
    tmp.replace(p)


def load_baseline(path: Union[str, Path]) -> Baseline:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("baseline file must declare version 1")
    return Baseline({k: {m: float(v) for m, v in d.items()}
                     for k, d in data.get("workloads", {}).items()},
                    dict(data.get("meta", {})))


@dataclass(frozen=True)
class Delta:
    workload: str
    metric: str
    baseline: float
    current: float

    @property
    def ratio(self) -> float:
        return self.current / self.baseline if self.baseline > 0 else float("inf")


@dataclass
class RegressionReport:
    regressions: List[Delta] = field(default_factory=list)
    improvements: List[Delta] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)  # in baseline, not in run
    new: List[str] = field(default_factory=list)  # in run, not in baseline

    @property
    def ok(self) -> bool:
        return not self.regressions

    def lines(self) -> List[str]:
        out = [f"REGRESSION {d.workload}.{d.metric}: {d.baseline:.2f} -> {d.current:.2f} ms "
               f"(x{d.ratio:.2f})" for d in self.regressions]
        out += [f"improved {d.workload}.{d.metric}: {d.baseline:.2f} -> {d.current:.2f} ms"
                for d in self.improvements]
        out += [f"missing workload (not run): {n}" for n in self.missing]
        out += [f"new workload (no baseline): {n}" for n in self.new]
        return out


def compare(baseline: Baseline, summaries: Mapping[str, Summary],
            tolerance: float = DEFAULT_TOLERANCE,
            noise_floor_ms: float = DEFAULT_NOISE_FLOOR_MS) -> RegressionReport:
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    rep = RegressionReport()
    rep.missing = sorted(set(baseline.workloads) - set(summaries))
    rep.new = sorted(set(summaries) - set(baseline.workloads))
    for name in sorted(set(baseline.workloads) & set(summaries)):
        for metric, base in sorted(baseline.workloads[name].items()):
            if metric not in COMPARED:
                continue
            cur = summaries[name].metric(metric)
            delta = Delta(name, metric, base, cur)
            if abs(cur - base) < noise_floor_ms:
                continue
            if cur > base * (1 + tolerance):
                rep.regressions.append(delta)
            elif cur < base * (1 - tolerance):
                rep.improvements.append(delta)
    return rep
