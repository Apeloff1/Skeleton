import pytest

from skeleton.frontier.gameforge_sequence import MAX_SEQUENCE, Sequence


def test_sequence_rejects_boolean_start():
    with pytest.raises(ValueError):
        Sequence(True)


def test_sequence_rejects_start_above_maximum():
    with pytest.raises(ValueError):
        Sequence(MAX_SEQUENCE + 1)


def test_sequence_stops_at_maximum():
    sequence = Sequence(MAX_SEQUENCE)
    with pytest.raises(OverflowError):
        sequence.next()
