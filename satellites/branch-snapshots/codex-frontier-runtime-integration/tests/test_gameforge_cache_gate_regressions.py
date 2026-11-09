import pytest

from skeleton.frontier.gameforge_parity import AdaptiveGate, TieredCache, Verdict


def test_upsert_invalidates_promoted_value():
    cache = TieredCache()
    cache.put("key", "old", now=0)
    cache.get("key", now=1)
    cache.get("key", now=2)
    cache.put("key", "new", now=3)
    assert cache.get("key", now=4) == "new"


def test_refill_keeps_fractional_credit_and_rejects_clock_rollback():
    gate = AdaptiveGate(2, 2)
    gate.admit(now=0)
    gate.admit(now=0)
    assert gate.admit(now=0.75) is Verdict.ADMITTED
    assert gate.admit(now=1) is Verdict.ADMITTED
    gate.admit(now=1.4)
    with pytest.raises(ValueError, match="monotonic"):
        gate.admit(now=1.3)


@pytest.mark.parametrize("now", [True, float("nan"), float("inf"), "1"])
def test_gate_rejects_invalid_clock_values_before_mutation(now):
    gate = AdaptiveGate(1, 1)
    with pytest.raises(ValueError):
        gate.admit(now=now)
    assert gate.tokens == 1
