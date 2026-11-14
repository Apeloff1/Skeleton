import pytest

from skeleton.frontier.gameforge_rate import RateWindow


def test_rate_window_rejects_time_regression():
    window = RateWindow(2, 10)
    assert window.allow(10)
    with pytest.raises(ValueError):
        window.allow(9)


def test_rate_window_reports_remaining_and_retry_after():
    window = RateWindow(2, 10)
    assert window.remaining(0) == 2
    assert window.allow(0)
    assert window.allow(1)
    assert window.remaining(1) == 0
    assert window.retry_after(1) == 9
    assert window.remaining(10) == 1
