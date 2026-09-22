"""Eval framework — regression suites for model and subsystem behavior.

Defines eval cases (input → expected predicate), runs them against
subsystem callables, and reports pass rates, regressions vs baseline,
and flakiness across repeated runs. Baselines are versioned so a new
code version is always compared against the previous best.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class EvalCase:
    name: str
    input: Dict[str, Any]
    expect: Callable[[Any], bool]
    tags: List[str] = field(default_factory=list)


@dataclass
class EvalResult:
    case: str
    passed: bool
    output: Any
    duration_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {"case": self.case, "passed": self.passed, "duration_ms": self.duration_ms}


class EvalSuite:
    """Named eval suite with baselines and regression detection."""

    def __init__(self, name: str, root: Optional[Path] = None):
        self.name = name
        self.root = root or Path(".skeleton")
        self._cases: List[EvalCase] = []
        self._baseline_file = self.root / f"eval_baseline_{name}.json"

    def case(self, name: str, input: Dict[str, Any],
             expect: Callable[[Any], bool], tags: Optional[List[str]] = None) -> EvalCase:
        c = EvalCase(name=name, input=input, expect=expect, tags=tags or [])
        self._cases.append(c)
        return c

    def run(self, fn: Callable[[Dict[str, Any]], Any],
            tags: Optional[List[str]] = None) -> Dict[str, Any]:
        results: List[EvalResult] = []
        for c in self._cases:
            if tags and not set(tags) & set(c.tags):
                continue
            start = time.time_ns()
            output: Any = None
            passed = False
            try:
                output = fn(c.input)
                passed = bool(c.expect(output))
            except Exception:  # noqa: BLE001
                passed = False
            results.append(EvalResult(c.name, passed, output, (time.time_ns() - start) / 1e6))
        passed_count = sum(1 for r in results if r.passed)
        total = len(results)
        report = {
            "suite": self.name,
            "ran": total,
            "passed": passed_count,
            "pass_rate": round(passed_count / total, 4) if total else 1.0,
            "results": [r.to_dict() for r in results],
            "regressions": self._diff_baseline(results),
            "timestamp_ns": time.time_ns(),
        }
        return report

    def _diff_baseline(self, results: List[EvalResult]) -> List[str]:
        baseline = self._load_baseline()
        regressions = []
        for r in results:
            if baseline.get(r.case) is True and not r.passed:
                regressions.append(r.case)
        return regressions

    def _load_baseline(self) -> Dict[str, bool]:
        if self._baseline_file.exists():
            return json.loads(self._baseline_file.read_text(encoding="utf-8"))
        return {}

    def save_baseline(self, results: Dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._baseline_file.write_text(json.dumps(
            {r["case"]: r["passed"] for r in results["results"]}, indent=2
        ), encoding="utf-8")

    def flakiness(self, fn: Callable[[Dict[str, Any]], Any], runs: int = 3) -> Dict[str, float]:
        outcomes: Dict[str, List[bool]] = {}
        for _ in range(runs):
            report = self.run(fn)
            for r in report["results"]:
                outcomes.setdefault(r["case"], []).append(r["passed"])
        flaky: Dict[str, float] = {}
        for case, passes in outcomes.items():
            rate = sum(passes) / len(passes)
            if 0.0 < rate < 1.0:
                flaky[case] = round(rate, 3)
        return flaky

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "eval-suite-card",
            "suite": self.name,
            "cases": len(self._cases),
            "has_baseline": self._baseline_file.exists(),
        }
