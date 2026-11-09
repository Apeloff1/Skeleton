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
