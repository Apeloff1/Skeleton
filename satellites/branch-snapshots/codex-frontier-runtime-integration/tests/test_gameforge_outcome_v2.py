import pytest

from skeleton.frontier.gameforge_outcome_v2 import ExecutionOutcomeV2


def test_terminal_failure_is_not_recoverable():
    outcome = ExecutionOutcomeV2("r1", False)
    assert outcome.terminal
    assert outcome.failed
    assert not outcome.recoverable


def test_nonterminal_failure_is_recoverable():
    outcome = ExecutionOutcomeV2("r2", False, terminal=False, reason="retry")
    assert outcome.recoverable
    assert outcome.failed


def test_outcome_requires_request_id():
    with pytest.raises(ValueError):
        ExecutionOutcomeV2("", True)


def test_success_must_be_terminal():
    with pytest.raises(ValueError):
        ExecutionOutcomeV2("r3", True, terminal=False)


def test_outcome_rejects_boolean_like_values():
    with pytest.raises(TypeError):
        ExecutionOutcomeV2("r4", 1)
    with pytest.raises(TypeError):
        ExecutionOutcomeV2("r5", False, terminal=1)


def test_reason_is_text():
    with pytest.raises(TypeError):
        ExecutionOutcomeV2("r6", False, reason=None)
