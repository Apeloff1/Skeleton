"""Test scaffolding — helper methods every builder module imports.

Moved the `render()`/grammar helpers out of each agent pipeline module.
Avoids duplication between the swarm/jeeves/qq test scaffolding helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import AgentError


class TestScaffoldError(AgentError):
    code = "TSC.SCAFFOLD"


@dataclass
class TestCase:
    name: str
    given: Dict[str, Any]
    expect: Dict[str, Any]
    timeout_ms: int = 1000


@dataclass(frozen=True)
class TestOutcome:
    case: TestCase
    ok: bool
    output: Any = None
    failure: Optional[TestScaffoldError] = None


class TestScaffold:
    """Ordered registry; per-test data + lifecycle."""

    def __init__(self) -> None:
        self._cases: List[TestCase] = []

    def register(self, case: TestCase) -> None:
        self._cases.append(case)

    def run(
        self,
        fn: Callable[[TestCase], Any],
        *,
        checker: Optional[Callable[[TestCase, Any], bool]] = None,
    ) -> Tuple[TestOutcome, ...]:
        outcomes: List[TestOutcome] = []
        for case in self._cases:
            try:
                output = fn(case)
                ok = checker(case, output) if checker else True
                outcomes.append(TestOutcome(case=case, ok=bool(ok), output=output))
            except TestScaffoldError as exc:
                outcomes.append(TestOutcome(case=case, ok=False, failure=exc))
        return tuple(outcomes)

    def summary(self, outcomes: Tuple[TestOutcome, ...]) -> Dict[str, int]:
        passed = sum(1 for o in outcomes if o.ok)
        return {"total": len(outcomes), "passed": passed, "failed": len(outcomes) - passed}
