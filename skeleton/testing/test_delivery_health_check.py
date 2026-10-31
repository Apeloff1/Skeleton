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
