from skeleton.frontier.gameforge_rate import RateWindow


def test_rate_window_rejects_boolean_time():
    window = RateWindow(1)
    try:
        window.allow(True)
    except TypeError:
        pass
    else:
        raise AssertionError("boolean timestamps must be rejected")


def test_rate_window_preserves_monotonic_clock_contract():
    window = RateWindow(2, 10)
    assert window.allow(10)
    assert window.allow(11)
    assert not window.allow(12)
    assert window.retry_after(12) == 8
    assert window.remaining(20) == 1
