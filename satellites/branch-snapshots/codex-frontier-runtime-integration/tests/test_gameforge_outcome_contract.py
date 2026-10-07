import pytest

from skeleton.frontier.gameforge_outcome import Outcome, OutcomeKind


def test_outcome_is_immutable_and_classified():
    outcome = Outcome(OutcomeKind.COMPLETED, "req-1", "ok")
    assert outcome.terminal
    assert outcome.accepted
    assert not outcome.failed
    with pytest.raises((AttributeError, TypeError)):
        outcome.detail = "changed"  # type: ignore[misc]


def test_outcome_rejects_invalid_provenance_and_detail():
    with pytest.raises(TypeError):
        Outcome("completed")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Outcome(OutcomeKind.FAILED, "")
    with pytest.raises(TypeError):
        Outcome(OutcomeKind.FAILED, "req", None)  # type: ignore[arg-type]


def test_outcome_terminal_boundaries():
    assert not Outcome(OutcomeKind.ACCEPTED).terminal
    assert not Outcome(OutcomeKind.SHED).terminal
    assert Outcome(OutcomeKind.COMPLETED).terminal
    assert Outcome(OutcomeKind.FAILED).terminal
