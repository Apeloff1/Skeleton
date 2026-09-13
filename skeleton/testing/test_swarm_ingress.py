from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_quota import Quota


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
