"""Fault injection harness — structured failure testing scenarios.

Runs structured failure scenarios against subsystems: dependency
down, slow dependency, partial failure, and cascading failure
chains. Each scenario asserts expected resilience behavior (circuit
opens, retries fire, shedder engages) and produces a pass/fail
verification report distinct from live chaos experiments.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Assertion:
    description: str
    check: Callable[[Dict[str, Any]], bool]
    passed: Optional[bool] = None
    detail: str = ""


@dataclass
class Scenario:
    name: str
    fault: str
    target: str
    assertions: List[Assertion] = field(default_factory=list)
    setup: Optional[Callable[[], Dict[str, Any]]] = None


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    assertions: List[Dict[str, Any]]
    duration_ms: float


class FaultInjectionHarness:
    """Structured resilience verification scenarios."""

    def __init__(self):
        self._scenarios: Dict[str, Scenario] = {}
        self._results: List[ScenarioResult] = []

    def scenario(self, name: str, fault: str, target: str,
                 setup: Optional[Callable[[], Dict[str, Any]]] = None) -> Scenario:
        s = Scenario(name=name, fault=fault, target=target, setup=setup)
        self._scenarios[name] = s
        return s

    def assert_that(self, scenario: str, description: str,
                    check: Callable[[Dict[str, Any]], bool]) -> None:
        self._scenarios[scenario].assertions.append(Assertion(description=description, check=check))

    def run(self, name: str) -> ScenarioResult:
        scenario = self._scenarios[name]
        start = time.time_ns()
        context: Dict[str, Any] = {}
        if scenario.setup:
            try:
                context = scenario.setup()
            except Exception as exc:  # noqa: BLE001
                context = {"setup_error": str(exc)}
        context["fault"] = scenario.fault
        context["target"] = scenario.target
        outcomes = []
        for assertion in scenario.assertions:
            try:
                assertion.passed = bool(assertion.check(context))
                assertion.detail = "" if assertion.passed else "check returned false"
            except Exception as exc:  # noqa: BLE001
                assertion.passed = False
                assertion.detail = str(exc)
            outcomes.append({
                "description": assertion.description,
                "passed": assertion.passed,
                "detail": assertion.detail,
            })
        result = ScenarioResult(
            name=name,
            passed=all(a["passed"] for a in outcomes) if outcomes else True,
            assertions=outcomes,
            duration_ms=(time.time_ns() - start) / 1e6,
        )
        self._results.append(result)
        return result

    def run_all(self) -> Dict[str, Any]:
        results = [self.run(name) for name in self._scenarios]
        passed = sum(1 for r in results if r.passed)
        return {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": round(passed / len(results), 3) if results else 1.0,
            "results": [{"name": r.name, "passed": r.passed, "ms": round(r.duration_ms, 2)} for r in results],
        }

    def verification_score(self) -> float:
        all_assertions = [a for r in self._results for a in r.assertions]
        if not all_assertions:
            return 1.0
        return sum(1 for a in all_assertions if a["passed"]) / len(all_assertions)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "fault-harness-card",
            "scenarios": len(self._scenarios),
            "runs": len(self._results),
            "verification_score": round(self.verification_score(), 3),
            "recent": [{"name": r.name, "passed": r.passed} for r in self._results[-5:]],
        }
