import pytest

from skeleton.frontier.gameforge_outcome_v2 import ExecutionOutcomeV2


def test_outcome_rejects_blank_request_id():
    with pytest.raises(ValueError):
        ExecutionOutcomeV2("  ", True)


def test_outcome_preserves_recoverable_failure_semantics():
    outcome = ExecutionOutcomeV2("r1", False, terminal=False)
    assert outcome.recoverable is True
