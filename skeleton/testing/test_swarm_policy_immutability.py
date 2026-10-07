from dataclasses import FrozenInstanceError

import pytest

from skeleton.agents.swarm_fairness import FairShareLedger
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_quota import QuotaLedger


def test_quota_usage_is_immutable_snapshot() -> None:
    ledger = QuotaLedger()
    usage = ledger.reserve("tenant", queued=1)
    with pytest.raises(FrozenInstanceError):
        usage.queued = 999
    assert ledger.usage("tenant").queued == 1


def test_fair_share_result_is_immutable_snapshot() -> None:
    ledger = FairShareLedger()
    share = ledger.admit("tenant")
    with pytest.raises(FrozenInstanceError):
        share.inflight = 999
    assert ledger.snapshot()["tenant"]["inflight"] == 1


def test_restore_task_does_not_consume_rate_tokens() -> None:
    governor = SwarmIngressGovernor(rate_capacity=2, rate_refill_per_second=0.000001)
    before = governor.rate.remaining("tenant")
    governor.restore_task("tenant", "task", {"x": 1}, phase="queued")
    after = governor.rate.remaining("tenant")
    assert after == pytest.approx(before)
    assert governor.phase("tenant", "task") == "queued"


def test_restore_task_is_idempotent_for_same_phase() -> None:
    governor = SwarmIngressGovernor()
    governor.restore_task("tenant", "task", {}, phase="leased")
    governor.restore_task("tenant", "task", {}, phase="leased")
    status = governor.status()
    assert status["quota"]["tenant"]["leased"] == 1
    assert status["fairness"]["tenant"]["inflight"] == 1
