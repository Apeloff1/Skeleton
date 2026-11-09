import pytest

from skeleton.frontier.gameforge_outcome_v2 import ExecutionOutcomeV2


def test_outcome_rejects_non_boolean_flags():
    with pytest.raises(TypeError):
        ExecutionOutcomeV2("r1", 1)
    with pytest.raises(TypeError):
        ExecutionOutcomeV2("r1", False, 1)


def test_outcome_rejects_non_string_fields():
    with pytest.raises(ValueError):
        ExecutionOutcomeV2(1, True)
    with pytest.raises(TypeError):
        ExecutionOutcomeV2("r1", True, reason=1)


def test_recoverable_requires_non_terminal_failure():
    assert ExecutionOutcomeV2("r1", False, False).recoverable
    assert not ExecutionOutcomeV2("r2", False, True).recoverable
