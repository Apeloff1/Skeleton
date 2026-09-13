import pytest

from skeleton.frontier.gameforge_idempotency import IdempotencyWindow


def test_none_is_a_valid_first_writer_value():
    window = IdempotencyWindow(2)
    assert window.record("r1", None) == (True, None)
    assert window.record("r1", "replacement") == (False, None)
    assert window.stats().duplicates == 1


def test_window_evicts_oldest_key():
    window = IdempotencyWindow(2)
    window.record("r1", 1)
    window.record("r2", 2)
    window.record("r3", 3)
    assert window.lookup("r1") is None
    assert window.lookup("r2") == 2
    assert window.stats().evicted == 1


def test_capacity_rejects_bool_and_zero():
    with pytest.raises(ValueError):
        IdempotencyWindow(0)
    with pytest.raises(ValueError):
        IdempotencyWindow(True)
