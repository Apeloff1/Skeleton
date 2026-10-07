import pytest

from skeleton.frontier.gameforge_checkpoint import Checkpoint


def test_checkpoint_only_advances():
    checkpoint = Checkpoint()
    assert checkpoint.advance(2)
    assert not checkpoint.advance(2)
    assert not checkpoint.advance(1)
    assert checkpoint.sequence == 2
    assert checkpoint.advance(3)


def test_checkpoint_rejects_negative():
    with pytest.raises(ValueError):
        Checkpoint(-2)
    with pytest.raises(ValueError):
        Checkpoint().advance(-1)


def test_checkpoint_rejects_boolean_sequences():
    with pytest.raises(ValueError):
        Checkpoint(True)
    with pytest.raises(ValueError):
        Checkpoint().advance(True)
