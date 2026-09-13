from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_quota import Quota, QuotaExceeded


def test_ingress_tracks_queue_lease_and_completion() -> None:
    governor = SwarmIngressGovernor(rate_capacity=10, rate_refill_per_second=1)
    decision = governor.admit("tenant", "task", {"x": 1})
    assert decision.accepted is True
    assert governor.status()["quota"]["tenant"]["queued"] == 1

    governor.mark_leased("tenant", "task")
    status = governor.status()
    assert status["quota"]["tenant"]["queued"] == 0
    assert status["quota"]["tenant"]["leased"] == 1

    governor.complete("tenant", "task")
    status = governor.status()
    assert status["quota"]["tenant"]["leased"] == 0
    assert status["quota"]["tenant"]["payload_bytes"] == 0
    assert status["accounted_tasks"] == 0


def test_ingress_rejects_payload_over_tenant_quota() -> None:
    governor = SwarmIngressGovernor()
    governor.configure_tenant("tiny", quota=Quota(max_queued=2, max_leased=2, max_payload_bytes=4))
    decision = governor.admit("tiny", "task", {"payload": "too-large"})
    assert decision.accepted is False
    assert decision.reason == "payload quota exceeded"
    assert governor.status()["accounted_tasks"] == 0


def test_ingress_rejects_duplicate_task_accounting() -> None:
    governor = SwarmIngressGovernor()
    assert governor.admit("tenant", "same", {}).accepted is True
    duplicate = governor.admit("tenant", "same", {})
    assert duplicate.accepted is False
    assert duplicate.reason == "task already accounted"


def test_ingress_fair_share_prefers_lower_virtual_load() -> None:
    governor = SwarmIngressGovernor()
    governor.configure_tenant("gold", weight=4)
    governor.configure_tenant("bronze", weight=1)
    governor.admit("gold", "g", {})
    governor.admit("bronze", "b", {})
    assert governor.preferred_tenant(["bronze", "gold"]) == "gold"


def test_ingress_completion_requires_accounted_task() -> None:
    governor = SwarmIngressGovernor()
    with pytest.raises(ValueError):
        governor.complete("tenant", "missing")


def test_quota_failure_refunds_rate_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    governor = SwarmIngressGovernor(rate_capacity=1, rate_refill_per_second=0.000001)

    def fail_reserve(*args: object, **kwargs: object) -> object:
        raise QuotaExceeded("synthetic quota race")

    monkeypatch.setattr(governor.quota, "reserve", fail_reserve)
    decision = governor.admit("tenant", "task", {})

    assert decision.accepted is False
    assert decision.reason == "synthetic quota race"
    assert governor.rate.remaining("tenant") == pytest.approx(1.0)
    assert governor.status()["accounted_tasks"] == 0


def test_fairness_failure_rolls_back_quota_and_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    governor = SwarmIngressGovernor(rate_capacity=1, rate_refill_per_second=0.000001)

    def fail_fairness(*args: object, **kwargs: object) -> object:
        raise RuntimeError("synthetic fairness failure")

    monkeypatch.setattr(governor.fairness, "admit", fail_fairness)
    with pytest.raises(RuntimeError, match="synthetic fairness failure"):
        governor.admit("tenant", "task", {})

    status = governor.status()
    assert status["quota"]["tenant"] == {"queued": 0, "leased": 0, "payload_bytes": 0}
    assert governor.rate.remaining("tenant") == pytest.approx(1.0)
    assert status["accounted_tasks"] == 0


def test_completion_fairness_failure_leaves_quota_and_task_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    governor = SwarmIngressGovernor()
    assert governor.admit("tenant", "task", {"x": 1}).accepted is True
    before = governor.status()

    def fail_complete(*args: object, **kwargs: object) -> object:
        raise RuntimeError("synthetic fairness completion failure")

    monkeypatch.setattr(governor.fairness, "complete", fail_complete)
    with pytest.raises(RuntimeError, match="synthetic fairness completion failure"):
        governor.complete("tenant", "task")

    after = governor.status()
    assert after["quota"] == before["quota"]
    assert after["accounted_tasks"] == 1
    assert governor.phase("tenant", "task") == "queued"


def test_completion_quota_failure_rolls_back_fairness(monkeypatch: pytest.MonkeyPatch) -> None:
    governor = SwarmIngressGovernor()
    assert governor.admit("tenant", "task", {"x": 1}).accepted is True
    before = governor.status()

    def fail_release(*args: object, **kwargs: object) -> object:
        raise QuotaExceeded("synthetic completion quota failure")

    monkeypatch.setattr(governor.quota, "release", fail_release)
    with pytest.raises(QuotaExceeded, match="synthetic completion quota failure"):
        governor.complete("tenant", "task")

    after = governor.status()
    assert after["quota"] == before["quota"]
    assert after["fairness"] == before["fairness"]
    assert after["accounted_tasks"] == 1
    assert governor.phase("tenant", "task") == "queued"


def test_concurrent_ingress_never_exceeds_queue_quota() -> None:
    governor = SwarmIngressGovernor(rate_capacity=1000, rate_refill_per_second=1000)
    governor.configure_tenant("tenant", quota=Quota(max_queued=8, max_leased=8, max_payload_bytes=1_000_000))

    def submit(index: int) -> bool:
        return governor.admit("tenant", f"task-{index}", {"i": index}).accepted

    with ThreadPoolExecutor(max_workers=32) as pool:
        accepted = list(pool.map(submit, range(128)))

    assert sum(accepted) == 8
    assert governor.status()["quota"]["tenant"]["queued"] == 8
    assert governor.status()["accounted_tasks"] == 8


def test_empty_fork_preserves_policy_without_live_accounting() -> None:
    governor = SwarmIngressGovernor(
        rate_capacity=17,
        rate_refill_per_second=3,
        default_quota=Quota(max_queued=50, max_leased=20, max_payload_bytes=5000),
    )
    governor.configure_tenant(
        "gold",
        quota=Quota(max_queued=7, max_leased=4, max_payload_bytes=700),
        weight=5,
    )
    governor.admit("gold", "live", {"payload": "x"})

    clone = governor.fork_empty()

    assert clone.rate.capacity == 17
    assert clone.rate.refill_per_second == 3
    assert clone.quota.default == governor.quota.default
    assert clone.quota.limit("gold") == governor.quota.limit("gold")
    assert clone.fairness.snapshot()["gold"]["weight"] == 5
    assert clone.status()["accounted_tasks"] == 0
    assert clone.status()["quota"] == {}
    assert clone.status()["rate"] == {}


def test_empty_fork_does_not_alias_policy_mutations() -> None:
    governor = SwarmIngressGovernor()
    governor.configure_tenant("gold", weight=4)
    clone = governor.fork_empty()
    clone.configure_tenant("gold", weight=9)

    assert governor.fairness.snapshot()["gold"]["weight"] == 4
    assert clone.fairness.snapshot()["gold"]["weight"] == 9
