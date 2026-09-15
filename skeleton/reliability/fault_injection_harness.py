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
    """Structured resilience verification scenarios with bounded history."""

    def __init__(self, max_results: int = 1000):
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            raise TypeError("max_results must be an integer")
        if max_results < 1:
            raise ValueError("max_results must be at least 1")
        self._scenarios: Dict[str, Scenario] = {}
        self._results: List[ScenarioResult] = []
        self._max_results = max_results

    def scenario(
        self,
        name: str,
        fault: str,
        target: str,
        setup: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> Scenario:
        scenario = Scenario(name=name, fault=fault, target=target, setup=setup)
        self._scenarios[name] = scenario
        return scenario

    def assert_that(
        self,
        scenario: str,
        description: str,
        check: Callable[[Dict[str, Any]], bool],
    ) -> None:
        self._scenarios[scenario].assertions.append(
            Assertion(description=description, check=check)
        )

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
            outcomes.append(
                {
                    "description": assertion.description,
                    "passed": assertion.passed,
                    "detail": assertion.detail,
                }
            )
        result = ScenarioResult(
            name=name,
            passed=all(assertion["passed"] for assertion in outcomes)
            if outcomes
            else True,
            assertions=outcomes,
            duration_ms=(time.time_ns() - start) / 1e6,
        )
        self._results.append(result)
        if len(self._results) > self._max_results:
            del self._results[: len(self._results) - self._max_results]
        return result

    def run_all(self) -> Dict[str, Any]:
        results = [self.run(name) for name in self._scenarios]
        passed = sum(1 for result in results if result.passed)
        return {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": round(passed / len(results), 3) if results else 1.0,
            "results": [
                {
                    "name": result.name,
                    "passed": result.passed,
                    "ms": round(result.duration_ms, 2),
                }
                for result in results
            ],
        }

    def verification_score(self) -> float:
        all_assertions = [
            assertion
            for result in self._results
            for assertion in result.assertions
        ]
        if not all_assertions:
            return 1.0
        return sum(1 for assertion in all_assertions if assertion["passed"]) / len(
            all_assertions
        )

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "fault-harness-card",
            "scenarios": len(self._scenarios),
            "runs": len(self._results),
            "max_results": self._max_results,
            "verification_score": round(self.verification_score(), 3),
            "recent": [
                {"name": result.name, "passed": result.passed}
                for result in self._results[-5:]
            ],
        }
