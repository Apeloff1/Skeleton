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
import re
from typing import Any, Callable, Dict, List, Optional


class EvalError(ValueError):
    """The eval suite itself is invalid."""


_SUITE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


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
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {"case": self.case, "passed": self.passed, "duration_ms": self.duration_ms}
        if self.error:
            payload["error"] = self.error
        return payload


class EvalSuite:
    """Named eval suite with baselines and regression detection."""

    def __init__(self, name: str, root: Optional[Path] = None):
        if not isinstance(name, str) or _SUITE_NAME.fullmatch(name) is None:
            raise EvalError("suite name must be a safe token")
        self.name = name
        self.root = root or Path(".skeleton")
        self._cases: List[EvalCase] = []
        self._baseline_file = self.root / f"eval_baseline_{name}.json"

    def case(self, name: str, input: Dict[str, Any],
             expect: Callable[[Any], bool], tags: Optional[List[str]] = None) -> EvalCase:
        if not isinstance(name, str) or not name.strip() or any(item.name == name for item in self._cases):
            raise EvalError("case name must be unique and non-empty")
        if not callable(expect):
            raise EvalError("expect must be callable")
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
            error: Optional[str] = None
            try:
                output = fn(c.input)
                verdict = c.expect(output)
                if verdict is not True and verdict is not False:
                    raise EvalError(f"expect for {c.name} must return a bool")
                passed = verdict is True
            except EvalError:
                raise
            except Exception as exc:
                passed = False
                output = None
                error = type(exc).__name__
            results.append(EvalResult(c.name, passed, output, (time.time_ns() - start) / 1e6, error))
        passed_count = sum(1 for r in results if r.passed)
        total = len(results)
        report = {
            "suite": self.name,
            "ran": total,
            "passed": passed_count,
            "pass_rate": round(passed_count / total, 4) if total else 0.0,
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
        if not self._baseline_file.exists():
            return {}
        loaded = json.loads(self._baseline_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or any(
            not isinstance(key, str) or (value is not True and value is not False)
            for key, value in loaded.items()
        ):
            raise EvalError("eval baseline is not a map of bools")
        return loaded

    def save_baseline(self, results: Dict[str, Any]) -> None:
        rows = results.get("results")
        if not isinstance(rows, list):
            raise EvalError("baseline results are required")
        merged = self._load_baseline()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("case"), str):
                raise EvalError("baseline row is invalid")
            passed = row.get("passed")
            if passed is not True and passed is not False:
                raise EvalError("baseline pass flag must be a bool")
            # A passing case stays the previous best. A later failure does not erase it.
            if merged.get(row["case"]) is True and passed is False:
                continue
            merged[row["case"]] = passed
        self.root.mkdir(parents=True, exist_ok=True)
        self._baseline_file.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")

    def flakiness(self, fn: Callable[[Dict[str, Any]], Any], runs: int = 3) -> Dict[str, float]:
        if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
            raise ValueError("runs must be a positive integer")
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
