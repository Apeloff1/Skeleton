import pytest

from skeleton.frontier.gameforge_rate import RateWindow


def test_rate_window_rejects_boolean_limits():
    with pytest.raises(ValueError):
        RateWindow(True)
    with pytest.raises(ValueError):
        RateWindow(1, True)


def test_rate_window_rejects_boolean_time():
    window = RateWindow(2, 10)
    with pytest.raises(TypeError):
        window.allow(True)


def test_rate_window_preserves_boundary_expiry():
    window = RateWindow(1, 10)
    assert window.allow(0)
    assert window.remaining(9) == 0
    assert window.remaining(10) == 1
