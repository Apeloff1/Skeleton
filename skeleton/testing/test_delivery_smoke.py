import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.smoke import SmokeOutcome, evaluate, load_suite

SUITE = [{"id": "health", "path": "/healthz"}, {"id": "ver", "path": "/version", "expect_json_keys": ["version"]}]


def test_evaluate():
    cases = load_suite(SUITE)
    ok = evaluate(cases, [SmokeOutcome("health", 200), SmokeOutcome("ver", 200, ("version", "sha"))])
    assert ok.ok and ok.passed == ("health", "ver")
    bad = evaluate(cases, [SmokeOutcome("health", 500), SmokeOutcome("ver", 200)])
    assert bad.failed == (("health", "status:500"), ("ver", "missing-keys:version"))
    assert evaluate(cases, []).failed[0] == ("health", "not-run")


def test_rejects_mutating_methods_and_duplicates():
    with pytest.raises(DeliveryError):
        load_suite([{"id": "x", "method": "POST", "path": "/x"}])
    with pytest.raises(DeliveryError):
        load_suite([SUITE[0], SUITE[0]])

def test_smoke_evidence_rejects_duplicates_and_status_coercion():
    cases = load_suite(SUITE)
    with pytest.raises(DeliveryError, match="duplicate smoke outcome"):
        evaluate(cases, [SmokeOutcome("health", 503), SmokeOutcome("health", 200)])
    with pytest.raises(DeliveryError, match="unknown or malformed"):
        evaluate(cases, [SmokeOutcome("forged", 200)])
    for status in (True, 200.0, "200"):
        with pytest.raises(DeliveryError, match="invalid smoke outcome"):
            evaluate(cases, [SmokeOutcome("health", status)])
        with pytest.raises(DeliveryError, match="expected status"):
            load_suite([{"id": "x", "path": "/x", "expect_status": status}])


def test_smoke_suite_and_outcome_bounds(monkeypatch):
    from itertools import repeat
    from skeleton.build.delivery import smoke as module

    monkeypatch.setattr(module, "MAX_SMOKE_CASES", 1)
    with pytest.raises(DeliveryError, match="suite count exceeds"):
        load_suite(SUITE)
    monkeypatch.setattr(module, "MAX_SMOKE_CASES", 256)
    monkeypatch.setattr(module, "MAX_SMOKE_OUTCOMES", 2)
    with pytest.raises(DeliveryError, match="outcome count exceeds"):
        evaluate(load_suite(SUITE), repeat(SmokeOutcome("health", 200), 3))
    with pytest.raises(DeliveryError, match="nonzero"):
        evaluate([], [])
