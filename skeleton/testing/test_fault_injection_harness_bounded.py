from __future__ import annotations

import pytest

from skeleton.reliability.fault_injection_harness import FaultInjectionHarness


@pytest.mark.parametrize("value", [True, False, 1.5, "10", None])
def test_max_results_requires_integer(value: object) -> None:
    with pytest.raises(TypeError):
        FaultInjectionHarness(max_results=value)  # type: ignore[arg-type]


def test_max_results_must_be_positive() -> None:
    with pytest.raises(ValueError):
        FaultInjectionHarness(max_results=0)


def test_bounded_history_preserves_lifetime_run_count_and_score() -> None:
    harness = FaultInjectionHarness(max_results=2)
    state = {"passes": False}
    harness.scenario("dependency", "down", "provider")
    harness.assert_that("dependency", "recovers", lambda _context: state["passes"])

    for _ in range(3):
        assert not harness.run("dependency").passed
    state["passes"] = True
    for _ in range(2):
        assert harness.run("dependency").passed

    card = harness.card()
    assert card["runs"] == 5
    assert card["retained_runs"] == 2
    assert card["max_results"] == 2
    assert card["recent"] == [
        {"name": "dependency", "passed": True},
        {"name": "dependency", "passed": True},
    ]
    assert harness.verification_score() == pytest.approx(2 / 5)
    assert card["verification_score"] == 0.4


def test_zero_assertion_runs_keep_perfect_score_without_unbounded_history() -> None:
    harness = FaultInjectionHarness(max_results=1)
    harness.scenario("noop", "none", "self")

    for _ in range(5):
        assert harness.run("noop").passed

    assert harness.verification_score() == 1.0
    card = harness.card()
    assert card["runs"] == 5
    assert card["retained_runs"] == 1
