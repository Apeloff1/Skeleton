import pytest
from skeleton.frontier.gameforge_outcome_v2 import ExecutionOutcomeV2


def test_terminal_failure_is_not_recoverable():
    outcome = ExecutionOutcomeV2("r1", False)
    assert outcome.terminal
    assert not outcome.recoverable


def test_nonterminal_failure_is_recoverable():
    outcome = ExecutionOutcomeV2("r2", False, terminal=False, reason="retry")
    assert outcome.recoverable


def test_outcome_requires_request_id():
    with pytest.raises(ValueError):
        ExecutionOutcomeV2("", True)
