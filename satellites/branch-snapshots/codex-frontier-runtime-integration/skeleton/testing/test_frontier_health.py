from skeleton.frontier.health import HealthState, evaluate_health


def test_health_gate_classifies_all_states():
    assert evaluate_health({}).state is HealthState.UNAVAILABLE
    assert evaluate_health({"db": False, "model": False}).state is HealthState.UNAVAILABLE
    assert evaluate_health({"db": True, "model": False}).state is HealthState.DEGRADED
    report = evaluate_health({"db": True, "model": True})
    assert report.state is HealthState.HEALTHY
    assert report.healthy
