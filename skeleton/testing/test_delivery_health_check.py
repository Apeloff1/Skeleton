import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.health_check import ProbeObservation as O
from skeleton.build.delivery.health_check import ProbeSpec, evaluate, specs_from_config

LIVE = ProbeSpec("liveness", "/healthz", max_latency_ms=500)
EXTRA = ProbeSpec("cache", "/cache", required=False)
REPLICAS = ("r1", "r2")


def test_all_pass_is_healthy():
    report = evaluate([LIVE], [O("liveness", r, 200, 10) for r in REPLICAS], replicas=REPLICAS)
    assert report.healthy and report.failing_probes == ()


def test_required_failure_is_unhealthy():
    obs = [O("liveness", "r1", 200, 10), O("liveness", "r2", 503, 10)]
    report = evaluate([LIVE], obs, replicas=REPLICAS)
    assert report.verdict == "unhealthy"
    assert any(r.reason == "status:503" for r in report.results)


def test_quorum_and_optional_probe():
    obs = [O("liveness", "r1", 200, 10), O("liveness", "r2", 200, 900), O("cache", "r1", 500, 1)]
    report = evaluate([LIVE, EXTRA], obs, replicas=REPLICAS, quorum=0.5)
    assert report.verdict == "degraded" and report.failing_probes == ("cache",)


def test_latest_observation_wins_and_missing_counts_as_fail():
    obs = [O("liveness", "r1", 500, 1), O("liveness", "r1", 200, 1)]
    report = evaluate([LIVE], obs, replicas=("r1",))
    assert report.healthy
    assert evaluate([LIVE], [], replicas=("r1",)).verdict == "unhealthy"


def test_body_marker_and_errors():
    spec = ProbeSpec("v", "/v", body_marker='"ok":true')
    assert not evaluate([spec], [O("v", "r", 200, 1, body="{}")], replicas=("r",)).healthy
    assert not evaluate([spec], [O("v", "r", None, None, error="timeout")], replicas=("r",)).healthy


def test_bad_specs():
    with pytest.raises(DeliveryError):
        ProbeSpec("x", "nope")
    with pytest.raises(DeliveryError):
        evaluate([LIVE, LIVE], [], replicas=REPLICAS)
    with pytest.raises(DeliveryError):
        evaluate([LIVE], [O("ghost", "r1", 200, 1)], replicas=REPLICAS)


def test_specs_from_config():
    specs = specs_from_config({"path": "/healthz", "probes": [{"id": "ready", "path": "/readyz", "required": False}]})
    assert [s.probe_id for s in specs] == ["liveness", "ready"]
    assert specs[1].required is False


def test_quorum_cannot_be_rounded_down_or_count_duplicate_replicas():
    good = [O("liveness", "r1", 200, 1)]
    assert evaluate([LIVE], good, replicas=REPLICAS, quorum=0.5).healthy
    assert evaluate([LIVE], good, replicas=REPLICAS, quorum=0.5001).verdict == "unhealthy"
    for replicas in (("r1", "r1"), ("r1", "")):
        with pytest.raises(DeliveryError, match="distinct nonempty"):
            evaluate([LIVE], good, replicas=replicas)


def test_quorum_rejects_untrusted_nonfinite_and_boolean_values():
    for quorum in (True, False, float("nan"), float("inf"), -0.1, 0, 1.01, "1"):
        with pytest.raises(DeliveryError, match="finite fraction"):
            evaluate([LIVE], [], replicas=REPLICAS, quorum=quorum)


def test_latency_and_status_evidence_must_be_bounded_integers():
    for latency in (float("nan"), float("inf"), -1, True, "0", 501):
        report = evaluate([LIVE], [O("liveness", "r1", 200, latency)], replicas=("r1",))
        assert report.verdict == "unhealthy"
    for status in (True, 200.0, "200", 600):
        report = evaluate([LIVE], [O("liveness", "r1", status, 1)], replicas=("r1",))
        assert report.verdict == "unhealthy"

def test_health_observation_and_inventory_limits_fail_closed():
    from itertools import repeat
    from skeleton.build.delivery.health_check import (
        MAX_HEALTH_OBSERVATIONS, MAX_HEALTH_PROBES, MAX_HEALTH_REPLICAS,
        MAX_OBSERVATION_BODY_CHARS,
    )

    with pytest.raises(DeliveryError, match="observation count exceeds"):
        evaluate([LIVE], repeat(O("liveness", "r1", 200, 1),
                                MAX_HEALTH_OBSERVATIONS + 1), replicas=("r1",))
    with pytest.raises(DeliveryError, match="invalid health observation"):
        evaluate([LIVE], [object()], replicas=("r1",))
    with pytest.raises(DeliveryError, match="body exceeds bound"):
        evaluate([LIVE], [O("liveness", "r1", 200, 1,
                            body="x" * (MAX_OBSERVATION_BODY_CHARS + 1))],
                 replicas=("r1",))
    with pytest.raises(DeliveryError, match="probe count exceeds"):
        evaluate([ProbeSpec(f"p{i}", "/health") for i in range(MAX_HEALTH_PROBES + 1)],
                 [], replicas=("r1",))
    with pytest.raises(DeliveryError, match="replica count exceeds"):
        evaluate([LIVE], [], replicas=tuple(
            f"r{i}" for i in range(MAX_HEALTH_REPLICAS + 1)))


def test_probe_spec_and_config_reject_coerced_security_evidence():
    from skeleton.ai.build.core.delivery import health_check as mirrored

    for module in (None, mirrored):
        spec = ProbeSpec if module is None else module.ProbeSpec
        parse = specs_from_config if module is None else module.specs_from_config
        for bad in ("//other-host/health", "/../admin", "/health?token=x", "/health#ok"):
            with pytest.raises(DeliveryError, match="unsafe probe path"):
                spec("probe", bad)
        for bad in (True, 200.0, "200"):
            with pytest.raises(DeliveryError, match="expect_status"):
                spec("probe", "/health", expect_status=(bad,))
        for bad in (True, "100", 100.0):
            with pytest.raises(DeliveryError, match="max_latency"):
                parse({"path": "/health", "max_latency_ms": bad})
        with pytest.raises(DeliveryError, match="required probe flag"):
            parse({"path": "/health", "probes": [
                {"id": "ready", "path": "/ready", "required": "false"}
            ]})
        with pytest.raises(DeliveryError, match="inventory exceeds"):
            parse({"path": "/health", "probes": [
                {"id": f"p{i}", "path": "/health"} for i in range(256)
            ]})


def test_health_adapter_error_is_redacted_from_release_evidence():
    from skeleton.ai.build.core.delivery import health_check as mirrored

    for module in (None, mirrored):
        evaluate_fn = evaluate if module is None else module.evaluate
        obs_type = O if module is None else module.ProbeObservation
        spec_type = ProbeSpec if module is None else module.ProbeSpec
        secret = "private-adapter-credential"
        report = evaluate_fn(
            [spec_type("liveness", "/health")],
            [obs_type("liveness", "r1", None, None, error=secret)],
            replicas=("r1",),
        )
        assert report.verdict == "unhealthy"
        assert report.results[0].reason == "probe-error"
        assert secret not in repr(report)
