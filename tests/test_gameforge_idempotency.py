import pytest

from skeleton.frontier.gameforge_idempotency import IdempotencyWindow


def test_first_writer_wins_and_replays_value() -> None:
    window = IdempotencyWindow[str](capacity=2)
    assert window.record("k", "first") == (True, "first")
    assert window.record("k", "second") == (False, "first")
    assert window.lookup("k") == "first"
    assert window.stats().duplicates == 1


def test_window_is_hard_bounded() -> None:
    window = IdempotencyWindow[int](capacity=2)
    window.record("a", 1)
    window.record("b", 2)
    window.record("c", 3)
    assert len(window) == 2
    assert window.lookup("a") is None
    assert window.lookup("c") == 3
    assert window.stats().evicted == 1


def test_invalid_capacity_rejected() -> None:
    with pytest.raises(ValueError):
        IdempotencyWindow(capacity=0)
