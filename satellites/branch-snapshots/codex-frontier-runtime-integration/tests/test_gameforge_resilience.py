from skeleton.kernel.gameforge_resilience import BackgroundBudget, Degradation, DegradationPolicy


def test_background_budget_is_bounded_and_releases() -> None:
    budget = BackgroundBudget(limit=2)
    assert budget.try_acquire()
    assert budget.try_acquire()
    assert not budget.try_acquire()
    budget.release()
    assert budget.try_acquire()
    assert budget.stats() == {"active": 2, "limit": 2}


def test_degradation_is_fail_safe_and_monotonic() -> None:
    policy = DegradationPolicy()
    assert policy.state is Degradation.NORMAL
    assert policy.background_allowed
    for expected in (
        Degradation.REDUCED_CACHING,
        Degradation.SHED_BACKGROUND,
        Degradation.STALE_READS,
        Degradation.EMERGENCY_READ_ONLY,
    ):
        assert policy.degrade() is expected
    assert policy.read_only
    assert not policy.background_allowed
    assert policy.degrade() is Degradation.EMERGENCY_READ_ONLY


def test_recovery_is_one_step_at_a_time() -> None:
    policy = DegradationPolicy()
    policy.degrade()
    policy.degrade()
    assert policy.recover() is Degradation.REDUCED_CACHING
    assert policy.recover() is Degradation.NORMAL
    assert policy.recover() is Degradation.NORMAL
