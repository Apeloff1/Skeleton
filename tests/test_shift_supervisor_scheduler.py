from core.shift_supervisor.scheduler import SupervisorScheduler


def test_scheduler_advance_skips_missed_ticks_without_bursting():
    assert SupervisorScheduler._advance(100.0, 900, 100.0) == 1000.0
    assert SupervisorScheduler._advance(100.0, 900, 2800.0) == 3700.0


def test_scheduler_rejects_non_positive_interval():
    try:
        SupervisorScheduler._advance(100.0, 0, 100.0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
