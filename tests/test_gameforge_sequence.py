import pytest
from skeleton.frontier.gameforge_sequence import Sequence


def test_sequence_is_monotonic():
    s = Sequence(4)
    assert s.value == 4
    assert s.next() == 5
    assert s.next() == 6


def test_sequence_rejects_negative_start():
    with pytest.raises(ValueError):
        Sequence(-1)
