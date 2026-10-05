from skeleton.frontier.gameforge_parity import AdaptiveGate, ChaosGovernor, ChaosState, TieredCache, Verdict


def test_tiered_cache_promotes_after_two_l2_hits():
    c = TieredCache(l1_cap=1, l2_cap=2, l1_ttl=10, l2_ttl=100)
    c.put("a", 42, now=0)
    assert c.get("a", now=1) == 42
    assert c.get("a", now=2) == 42
    assert c.stats()["l1_entries"] == 1


def test_tiered_cache_is_bounded_and_expires():
    c = TieredCache(l1_cap=1, l2_cap=1, l1_ttl=1, l2_ttl=2)
    c.put("a", 1, now=0)
    c.put("b", 2, now=0)
    assert c.stats()["l2_entries"] == 1
    assert c.get("a", now=3) is None
    assert c.stats()["misses"] == 1


def test_adaptive_gate_sheds_bulk_when_empty():
    g = AdaptiveGate(capacity=1, refill_per_sec=0)
    assert g.admit(priority=1) is Verdict.ADMITTED
    assert g.admit(priority=1) is Verdict.SHED
    assert g.stats()["shed"] == 1


def test_adaptive_gate_refills_without_exceeding_capacity():
    g = AdaptiveGate(capacity=2, refill_per_sec=10)
    assert g.admit(priority=1, now=0) is Verdict.ADMITTED
    assert g.admit(priority=1, now=0) is Verdict.ADMITTED
    assert g.admit(priority=1, now=1) is Verdict.ADMITTED
    assert g.tokens <= g.capacity


def test_chaos_governor_walks_to_read_only_and_back():
    g = ChaosGovernor()
    for _ in range(4):
        g.degrade()
    assert g.state is ChaosState.EMERGENCY_READ_ONLY
    assert g.read_only
    assert not g.allow_background
    g.recover()
    assert g.state is ChaosState.STALE_READS
