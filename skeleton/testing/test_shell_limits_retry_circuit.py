import pytest

from skeleton.shells.circuit import CircuitBreaker, CircuitPolicy, CircuitRegistry, CircuitState
from skeleton.shells.errors import CircuitOpen
from skeleton.shells.limits import ResourceBudget, ResourceLimits
from skeleton.shells.retry import RetryPolicy


def test_resource_limits_narrow_rejects_widening():
    limits = ResourceLimits(max_commands=10, max_failures=2)
    child = limits.narrow(max_commands=5)
    assert child.max_commands == 5
    with pytest.raises(ValueError):
        limits.narrow(max_commands=11)


def test_resource_budget_reserves_and_exhausts_commands():
    budget = ResourceBudget(ResourceLimits(max_commands=2))
    assert budget.reserve_command() is True
    assert budget.reserve_command() is True
    assert budget.reserve_command() is False
    assert budget.snapshot().commands == 2


def test_resource_budget_tracks_result_dimensions():
    budget = ResourceBudget(ResourceLimits(max_commands=5, max_failures=1, max_duration_ms=100, max_stdout_bytes=10))
    budget.reserve_command()
    budget.record_result(ok=False, duration_ms=50, stdout_bytes=8, stderr_bytes=2)
    usage = budget.snapshot()
    assert usage.failures == 1
    assert usage.duration_ms == 50
    assert usage.stdout_bytes == 8
    assert budget.healthy()
    budget.record_result(ok=False, duration_ms=60, stdout_bytes=3, stderr_bytes=0)
    assert set(budget.exceeded()) >= {"failures", "duration_ms", "stdout_bytes"}


def test_retry_policy_exponential_cap():
    policy = RetryPolicy(max_attempts=5, initial_delay_seconds=1, multiplier=3, max_delay_seconds=5, retry_returncodes=frozenset({75}))
    assert policy.delay_for_attempt(1) == 1
    assert policy.delay_for_attempt(2) == 3
    assert policy.delay_for_attempt(3) == 5


def test_retry_policy_retries_selected_returncode():
    policy = RetryPolicy.transient_codes([75], max_attempts=3)
    decision = policy.decide(attempt=1, returncode=75, timed_out=False, output_limited=False)
    assert decision.retry is True
    assert "75" in decision.reason


def test_retry_policy_does_not_retry_unselected_failure():
    policy = RetryPolicy.transient_codes([75], max_attempts=3)
    decision = policy.decide(attempt=1, returncode=2, timed_out=False, output_limited=False)
    assert decision.retry is False


def test_retry_policy_timeout_requires_opt_in():
    base = RetryPolicy(max_attempts=2)
    assert not base.decide(attempt=1, returncode=None, timed_out=True, output_limited=False).retry
    enabled = RetryPolicy(max_attempts=2, retry_timeouts=True)
    assert enabled.decide(attempt=1, returncode=None, timed_out=True, output_limited=False).retry


def test_retry_policy_stops_at_attempt_limit():
    policy = RetryPolicy(max_attempts=2, retry_returncodes=frozenset({1}))
    assert policy.decide(attempt=2, returncode=1, timed_out=False, output_limited=False).retry is False


def test_circuit_opens_after_threshold_and_recovers_half_open():
    now = [0.0]
    breaker = CircuitBreaker(CircuitPolicy(failure_threshold=2, recovery_seconds=10, half_open_successes=1), clock=lambda: now[0])
    breaker.record_failure()
    assert breaker.state() is CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state() is CircuitState.OPEN
    with pytest.raises(CircuitOpen):
        breaker.allow(command="python")
    now[0] = 11
    assert breaker.state() is CircuitState.HALF_OPEN
    breaker.allow(command="python")
    breaker.record_success()
    assert breaker.state() is CircuitState.CLOSED


def test_half_open_failure_reopens_circuit():
    now = [0.0]
    breaker = CircuitBreaker(CircuitPolicy(failure_threshold=1, recovery_seconds=1), clock=lambda: now[0])
    breaker.record_failure()
    now[0] = 2
    assert breaker.state() is CircuitState.HALF_OPEN
    breaker.record_failure()
    assert breaker.state() is CircuitState.OPEN


def test_circuit_registry_reuses_keys_and_reset():
    registry = CircuitRegistry(CircuitPolicy(failure_threshold=1, recovery_seconds=100))
    first = registry.get("python")
    assert registry.get("python") is first
    first.record_failure()
    assert registry.snapshot()["python"].state is CircuitState.OPEN
    registry.reset("python")
    assert registry.snapshot()["python"].state is CircuitState.CLOSED
