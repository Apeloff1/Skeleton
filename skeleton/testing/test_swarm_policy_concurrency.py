from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.agents.swarm_fairness import FairShareLedger
from skeleton.agents.swarm_quota import Quota, QuotaExceeded, QuotaLedger
from skeleton.agents.swarm_rate_limit import TokenBucketLimiter


def test_rate_limiter_concurrent_consumption_is_bounded() -> None:
    limiter = TokenBucketLimiter(capacity=25, refill_per_second=0.000001)
    with ThreadPoolExecutor(max_workers=32) as pool:
        allowed = list(pool.map(lambda _: limiter.allow("tenant"), range(200)))
    assert sum(allowed) == 25
    assert 0 <= limiter.remaining("tenant") < 1


def test_quota_ledger_concurrent_reservation_is_bounded() -> None:
    ledger = QuotaLedger(Quota(max_queued=20, max_leased=20, max_payload_bytes=100_000))

    def reserve(_: int) -> bool:
        try:
            ledger.reserve("tenant", queued=1)
            return True
        except QuotaExceeded:
            return False

    with ThreadPoolExecutor(max_workers=32) as pool:
        accepted = list(pool.map(reserve, range(200)))
    assert sum(accepted) == 20
    assert ledger.snapshot()["tenant"]["queued"] == 20


def test_fair_share_concurrent_admit_complete_balances() -> None:
    ledger = FairShareLedger()
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(lambda _: ledger.admit("tenant"), range(100)))
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(lambda _: ledger.complete("tenant"), range(100)))
    snapshot = ledger.snapshot()["tenant"]
    assert snapshot["admitted"] == 100
    assert snapshot["completed"] == 100
    assert snapshot["inflight"] == 0


def test_fair_share_rejects_completion_underflow() -> None:
    ledger = FairShareLedger()
    with pytest.raises(ValueError):
        ledger.complete("tenant")
