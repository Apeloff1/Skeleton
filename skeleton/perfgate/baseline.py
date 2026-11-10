"""Baseline snapshots and relative regression comparison."""
from __future__ import annotations

import json
import math
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
        if (not summaries or any(s.count <= s.errors or s.max_ms <= 0
                                  for s in summaries.values())):
            raise ValueError("baseline requires successful positive measured samples")
        return cls({n: {m: s.metric(m) for m in COMPARED} for n, s in summaries.items()},
                   dict(meta or {}))

    def __post_init__(self) -> None:
        if (type(self.workloads) is not dict or len(self.workloads) > 256
                or type(self.meta) is not dict):
            raise ValueError("invalid baseline inventory")
        for name, values in self.workloads.items():
            if (type(name) is not str or not 1 <= len(name) <= 128
                    or type(values) is not dict or set(values) != set(COMPARED)
                    or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
                           for v in values.values())):
                raise ValueError("noncanonical baseline metrics")

    def to_json(self) -> str:
        self.__post_init__()
        return json.dumps({"version": 1, "meta": self.meta, "workloads": self.workloads},
                          indent=2, sort_keys=True, allow_nan=False) + "\n"


def save_baseline(baseline: Baseline, path: Union[str, Path]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(baseline.to_json(), encoding="utf-8")
    tmp.replace(p)


def load_baseline(path: Union[str, Path]) -> Baseline:
    p = Path(path)
    if p.is_symlink() or p.stat().st_size > 262144:
        raise ValueError("unsafe or oversized baseline source")
    def unique(pairs):
        out = {}
        for k, value in pairs:
            if k in out:
                raise ValueError("duplicate baseline JSON key")
            out[k] = value
        return out
    data = json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite baseline JSON")))
    if type(data) is not dict or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("baseline file must declare version 1")
    if (set(data) - {"version", "workloads", "meta"}
            or type(data.get("workloads")) is not dict
            or type(data.get("meta", {})) is not dict):
        raise ValueError("invalid baseline fields")
    return Baseline(data["workloads"], data.get("meta", {}))


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
        return not self.regressions and not self.missing

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
    if (type(tolerance) not in (int, float) or not math.isfinite(tolerance)
            or not 0 <= tolerance <= 10 or type(noise_floor_ms) not in (int, float)
            or not math.isfinite(noise_floor_ms) or noise_floor_ms < 0):
        raise ValueError("finite bounded tolerance/noise floor required")
    rep = RegressionReport()
    measured = {name: sample for name, sample in summaries.items()
                if sample.count > sample.errors and sample.max_ms > 0}
    rep.missing = sorted(set(baseline.workloads) - set(measured))
    rep.new = sorted(set(measured) - set(baseline.workloads))
    for name in sorted(set(baseline.workloads) & set(measured)):
        for metric, base in sorted(baseline.workloads[name].items()):
            if metric not in COMPARED:
                continue
            cur = measured[name].metric(metric)
            delta = Delta(name, metric, base, cur)
            if abs(cur - base) < noise_floor_ms:
                continue
            if cur > base * (1 + tolerance):
                rep.regressions.append(delta)
            elif cur < base * (1 - tolerance):
                rep.improvements.append(delta)
    return rep
