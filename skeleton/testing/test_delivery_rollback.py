import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.health_check import HealthReport
from skeleton.build.delivery.release_history import ReleaseHistory
from skeleton.build.delivery.rollback import decide, plan_rollback

C = "c" * 64


def test_decide():
    assert decide(HealthReport("unhealthy", (), ("liveness",))).should_rollback
    assert not decide(HealthReport("degraded", (), ("x",))).should_rollback
    assert decide(HealthReport("degraded", (), ("x",)), tolerate_degraded=False).should_rollback
    assert decide(HealthReport("healthy", (), ()), error_rate=0.05).reason.startswith("error-budget")
    assert not decide(HealthReport("healthy", (), ())).should_rollback
    with pytest.raises(DeliveryError):
        decide(HealthReport("healthy", (), ()), error_rate=2)


def test_plan_targets_previous_good_release():
    h = ReleaseHistory("staging")
    h.record(release_id="r1", manifest_digest="1" * 64, config_digest=C, outcome="deployed", recorded_at=1)
    h.record(release_id="r2", manifest_digest="2" * 64, config_digest=C, outcome="deployed", recorded_at=2)
    plan = plan_rollback(h, trigger="health")
    assert (plan.from_release, plan.to_release) == ("r2", "r1")
    assert plan.steps[0] == "freeze:staging" and plan.steps[-1] == "unfreeze:staging"
    assert "health-gate" in plan.steps


def test_plan_errors():
    h = ReleaseHistory("staging")
    with pytest.raises(DeliveryError):
        plan_rollback(h, trigger="manual")
    h.record(release_id="r1", manifest_digest="1" * 64, config_digest=C, outcome="deployed", recorded_at=1)
    with pytest.raises(DeliveryError, match="known-good"):
        plan_rollback(h, trigger="manual")
    with pytest.raises(DeliveryError):
        plan_rollback(h, trigger="vibes")


def test_rollback_rejects_nonfinite_and_boolean_error_evidence():
    health = HealthReport("healthy", (), ())
    for bad in (float("nan"), float("inf"), float("-inf"), True, "0.01"):
        with pytest.raises(DeliveryError, match="fractions"):
            decide(health, error_rate=bad)
        with pytest.raises(DeliveryError, match="fractions"):
            decide(health, error_budget=bad)


def test_rollback_rejects_nonboolean_degraded_policy():
    report = HealthReport("degraded", (), ("readiness",))
    for bad in ("false", 0, 1, None):
        with pytest.raises(DeliveryError, match="tolerate_degraded"):
            decide(report, tolerate_degraded=bad)
    assert decide(report, tolerate_degraded=False).should_rollback
    assert not decide(report, tolerate_degraded=True).should_rollback


def test_rollback_refuses_unknown_or_contradictory_health_evidence():
    for report in (
        HealthReport("unknown", (), ()),
        HealthReport("healthy", (), ("readiness",)),
        HealthReport("", (), ()),
        HealthReport("healthy", (), ["not-a-tuple"]),
        None,
    ):
        with pytest.raises(DeliveryError, match="health report evidence"):
            decide(report)
    assert decide(HealthReport("healthy", (), ())).should_rollback is False
    assert decide(HealthReport("unhealthy", (), ("readiness",))).should_rollback is True
    history = ReleaseHistory("staging")
    with pytest.raises(DeliveryError, match="rollback trigger"):
        plan_rollback(history, trigger=[])
