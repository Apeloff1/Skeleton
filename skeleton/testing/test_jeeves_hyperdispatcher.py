"""Focused regression tests for the existing pressure owner's dispatcher."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from skeleton.intelligence.dispatch_policy import (
    DispatchCandidate, DispatchPolicyError, PlacementNode, PlacementRequest,
    ResourceVector, critical_paths, place_gang, rank_candidates, safe_backfill,
)
from skeleton.intelligence.shared_pressure import (
    SharedPressureConflict, SharedPressureError, SharedPressureExceeded,
    SharedPressurePolicy, SqliteSharedPressureLedger,
)


def ledger(tmp_path, *, concurrency=4, tenant=2):
    result = SqliteSharedPressureLedger(tmp_path / "pressure.sqlite")
    result.configure(SharedPressurePolicy("jeeves", concurrency, 32, tenant, 16, 1.0))
    return result


def test_protected_aging_and_determinism():
    rows = [
        DispatchCandidate("old", "a", 100, 0),
        DispatchCandidate("new", "b", 30, 100_000),
        DispatchCandidate("protected", "c", 10, 100_000),
    ]
    kwargs = dict(now_ms=100_000, tenant_active={}, aging_interval_ms=1000)
    order = rank_candidates(rows, **kwargs)
    assert [x.ticket_id for x in order] == ["protected", "old", "new"]
    assert order == rank_candidates(list(reversed(rows)), **kwargs)
    assert order[1].effective_priority == 11


def test_deadline_share_and_future():
    rows = [DispatchCandidate("a", "a", 20, 0), DispatchCandidate("b", "b", 20, 0)]
    assert rank_candidates(rows, now_ms=1, tenant_active={"a": 2, "b": 0})[0].ticket_id == "b"
    rows[0] = replace(rows[0], deadline_ms=3)
    assert rank_candidates(rows, now_ms=1, tenant_active={"a": 2})[0].ticket_id == "a"
    with pytest.raises(DispatchPolicyError):
        rank_candidates(rows, now_ms=1, tenant_active={}, tenant_weights={"a": 0})
    with pytest.raises(DispatchPolicyError):
        rank_candidates(rows + [rows[0]], now_ms=1, tenant_active={})
    with pytest.raises(DispatchPolicyError):
        rank_candidates([replace(rows[0], enqueued_ms=2)], now_ms=1, tenant_active={})


def test_resource_gang_and_locality():
    gpu = ResourceVector((("gpu", 1), ("ram", 8)))
    demand = ResourceVector((("gpu", 1), ("ram", 4)))
    nodes = [
        PlacementNode("n1", gpu, frozenset({"cuda"}), frozenset({"model"}), "rack1"),
        PlacementNode("n2", gpu, frozenset({"cuda"}), failure_domain="rack2"),
    ]
    req = PlacementRequest("a", demand, frozenset({"cuda"}), frozenset({"model"}))
    assert place_gang([req], nodes) == (("a", "n1"),)
    assert place_gang([req, replace(req, task_id="b")], nodes) == (("a", "n1"), ("b", "n2"))
    assert place_gang([req, replace(req, task_id="b"), replace(req, task_id="c")], nodes) is None
    assert place_gang([replace(req, required=frozenset({"metal"}))], nodes) is None
    assert nodes[0].capacity == gpu
    with pytest.raises(DispatchPolicyError):
        place_gang([req, replace(req, task_id="b")], nodes, search_budget=1)


def test_critical_paths_and_backfill():
    assert critical_paths({"a": 2, "b": 5, "c": 3}, {"a": (), "b": ("a",), "c": ("a",)}) == {
        "a": 7, "b": 5, "c": 3,
    }
    with pytest.raises(DispatchPolicyError):
        critical_paths({"a": 1, "b": 1}, {"a": ("b",), "b": ("a",)})
    assert safe_backfill(now_ms=10, reservation_ms=20, estimated_ms=8, uncertainty_ms=2)
    assert not safe_backfill(now_ms=10, reservation_ms=20, estimated_ms=8, uncertainty_ms=3)


def test_ranked_is_atomic_and_scope_bound(tmp_path):
    left = ledger(tmp_path, concurrency=1, tenant=1)
    right = SqliteSharedPressureLedger(left.path)
    low = left.enqueue("jeeves", "a", "low", priority=40, now=1)
    high = left.enqueue("jeeves", "b", "high", priority=5, now=2)
    with pytest.raises(SharedPressureConflict):
        left.promote_ranked("jeeves", "worker", authorized_tickets=(replace(high, tenant_id="x"),), now=3)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: item[0].promote_ranked(
            "jeeves", item[1], authorized_tickets=(low, high), now=3
        ), [(left, "w1"), (right, "w2")]))
    admitted = [row for row in results if row is not None]
    assert len(admitted) == 1 and admitted[0].operation_id == "high"
    assert right.snapshot("jeeves", now=3).queued == 1


def test_expired_attempt_cannot_release_new_attempt(tmp_path):
    state = ledger(tmp_path)
    ticket = state.enqueue("jeeves", "a", "task", priority=5, now=1)
    first = state.promote_ranked("jeeves", "worker", authorized_tickets=(ticket,), now=2, lease_seconds=1)
    assert first is not None
    newer = state.enqueue("jeeves", "a", "task", priority=5, now=4)
    second = state.promote_ranked("jeeves", "worker", authorized_tickets=(newer,), now=5)
    assert second is not None and second.lease_id != first.lease_id
    with pytest.raises(SharedPressureError):
        state.release(first.lease_id, "worker")
    assert state.lease_for_operation("jeeves", "task", now=5) == second


def test_group_rolls_back_on_tenant_capacity_and_stale_ticket(tmp_path):
    state = ledger(tmp_path, concurrency=3, tenant=1)
    a = state.enqueue("jeeves", "a", "a", priority=5, now=1)
    b = state.enqueue("jeeves", "a", "b", priority=5, now=1)
    c = state.enqueue("jeeves", "b", "c", priority=5, now=1)
    with pytest.raises(SharedPressureExceeded):
        state.promote_group("jeeves", "w", authorized_tickets=(a, b), now=2)
    assert state.snapshot("jeeves", now=2).active == 0
    assert state.snapshot("jeeves", now=2).queued == 3
    with pytest.raises(SharedPressureConflict):
        state.promote_group("jeeves", "w", authorized_tickets=(a, replace(c, priority=6)), now=2)
    assert state.snapshot("jeeves", now=2).queued == 3
    leases = state.promote_group("jeeves", "w", authorized_tickets=(a, c), now=2)
    assert {item.operation_id for item in leases} == {"a", "c"}
    assert state.snapshot("jeeves", now=2).active == 2
    assert state.snapshot("jeeves", now=2).queued == 1


def test_unapproved_ticket_not_selected_and_capped_tenant_skipped(tmp_path):
    state = ledger(tmp_path, concurrency=3, tenant=1)
    state.acquire("jeeves", "a", "already", "w", priority=5, now=1)
    a = state.enqueue("jeeves", "a", "a", priority=0, now=1)
    b = state.enqueue("jeeves", "b", "b", priority=50, now=1)
    state.enqueue("jeeves", "c", "unapproved", priority=0, now=1)
    chosen = state.promote_ranked("jeeves", "w", authorized_tickets=(a, b), now=2)
    assert chosen is not None and chosen.operation_id == "b"


def test_no_unknown_resource_or_duplicate_dimension():
    with pytest.raises(DispatchPolicyError):
        ResourceVector((("gpu", 1), ("gpu", 2)))
    assert not ResourceVector((("gpu", 1),)).fits(ResourceVector((("cpu", 8),)))


def test_route_cache_pressure_and_identity():
    from skeleton.intelligence.dispatch_advisory import RouteDemand, RouteWorker, choose_route

    digest = "a" * 64
    tokens = "b" * 64
    demand = RouteDemand("tenant", digest, tokens, frozenset({"cuda"}), 80, 20)
    resident = RouteWorker("a", "tenant", digest, tokens, frozenset({"cuda"}), 100, 5, 80, 10, 1, True)
    idle = replace(resident, worker="b", queued_tokens=0, resident_prefix_tokens=0)
    assert choose_route(demand, [idle, resident], now_ms=11).worker == "a"
    assert choose_route(demand, [idle, replace(resident, queued_tokens=1000)], now_ms=11).worker == "b"
    assert choose_route(demand, [replace(resident, free_tokens=99)], now_ms=11) is None
    assert choose_route(demand, [replace(resident, tenant="other")], now_ms=11) is None
    assert choose_route(demand, [replace(resident, tokenizer_sha256="c" * 64)], now_ms=11) is None
    assert choose_route(demand, [resident], now_ms=5011) is None
    assert choose_route(demand, [resident], now_ms=9) is None


def test_steal_requires_unstarted_and_transfer_gain():
    from skeleton.intelligence.dispatch_advisory import StealObservation, propose_steal

    row = StealObservation("task", "a", "b", "tenant", 100, 20, 50, 10, 5, 1, 2, True, True)
    assert propose_steal([row]) == row
    assert propose_steal([replace(row, not_started=False)]) is None
    assert propose_steal([replace(row, compatible=False)]) is None
    assert propose_steal([replace(row, transfer_ms=90)]) is None


def test_retry_never_repeats_unknown_effect():
    from skeleton.intelligence.dispatch_advisory import retry_proposal

    args = dict(attempt=1, maximum_attempts=3, remaining_ms=30000)
    retry = retry_proposal("task", outcome="confirmed-no-effect", **args)
    assert retry == retry_proposal("task", outcome="confirmed-no-effect", **args)
    assert retry.disposition == "retry" and 1000 <= retry.delay_ms <= 1250
    assert retry_proposal("task", outcome="unknown-effect", **args).disposition == "reconcile"
    assert retry_proposal("task", outcome="permanent", **args).disposition == "quarantine"
    assert retry_proposal("task", outcome="confirmed-no-effect", **(args | {"remaining_ms": 1})).disposition == "deadline"


def test_duration_estimates_conservative_sparse_and_observed():
    from skeleton.intelligence.dispatch_advisory import estimate_duration

    assert estimate_duration([1, 100], fallback_ms=50).conservative_ms == 100
    e = estimate_duration(list(range(1, 101)), fallback_ms=25)
    assert e.samples == 100 and e.median_ms == 50 and e.conservative_ms == 95


def test_shadow_schedule_reproducible_and_protected():
    from skeleton.intelligence.dispatch_advisory import ShadowTask, shadow_schedule, choose_shadow

    rows = [ShadowTask("long", "a", 0, 50, 50),
            ShadowTask("short", "b", 0, 2, 50, 5),
            ShadowTask("critical", "c", 0, 1, 5)]
    baseline = shadow_schedule(rows, slots=1, policy="fifo")
    optimized = shadow_schedule(rows, slots=1, policy="deadline")
    assert baseline.timeline[0][0] == optimized.timeline[0][0] == "critical"
    assert baseline.deadline_misses == 1 and optimized.deadline_misses == 0
    assert optimized == shadow_schedule(list(reversed(rows)), slots=1, policy="deadline")
    assert len(choose_shadow(rows, slots=1)) == 5
    overlap = shadow_schedule(rows, slots=2, policy="deadline")
    assert overlap.timeline[1][1] == 0


def test_cross_plane_resource_group_is_atomic_and_replay_fenced():
    from skeleton.kernel.global_resource_scheduler import (
        GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy,
        ResourceVector, ResourceRequest, ResourceConflict,
    )

    owner = GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=100, memory_mb=100),
        (PlanePolicy("ai", 1, ResourceVector(cpu_millis=10)),
         PlanePolicy("forge", 1, ResourceVector(memory_mb=10))),
    ))
    a = ResourceRequest("a", "ai", "tenant", ResourceVector(cpu_millis=60, memory_mb=30))
    b = ResourceRequest("b", "forge", "tenant", ResourceVector(cpu_millis=30, memory_mb=60))
    c = ResourceRequest("c", "forge", "tenant", ResourceVector(cpu_millis=50, memory_mb=60))
    before = owner.snapshot()
    assert owner.reserve_group("group", (a, c)) is None
    assert owner.snapshot() == before and owner.queued() == ()
    grants = owner.reserve_group("group", (a, b))
    assert grants is not None and len(grants) == 2
    assert owner.reserve_group("group", (b, a)) == grants
    assert owner.usage("ai").cpu_millis == 60
    assert owner.usage("forge").memory_mb == 60
    with pytest.raises(ResourceConflict):
        owner.reserve_group("group", (a, c))
    owner.release(grants[0].grant_id)
    with pytest.raises(ResourceConflict):
        owner.reserve_group("group", (a, b))


def test_resource_group_respects_incumbent_and_tenant_boundary():
    from skeleton.kernel.global_resource_scheduler import (
        GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy,
        ResourceVector, ResourceRequest, ResourceConflict,
    )

    owner = GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=100),
        (PlanePolicy("ai", 1, ResourceVector(cpu_millis=20)),
         PlanePolicy("forge", 1, ResourceVector(cpu_millis=20))),
    ))
    urgent = ResourceRequest("urgent", "forge", "tenant", ResourceVector(cpu_millis=20), priority=0)
    owner.submit(urgent)
    a = ResourceRequest("a", "ai", "tenant", ResourceVector(cpu_millis=40))
    b = ResourceRequest("b", "ai", "tenant", ResourceVector(cpu_millis=40))
    before = owner.snapshot()
    assert owner.reserve_group("g", (a, b)) is None
    assert owner.snapshot() == before
    with pytest.raises(ResourceConflict):
        owner.reserve_group("g", (a, replace(b, tenant_id="other")))
    assert owner.admit_request("urgent") is not None
    assert owner.reserve_group("g", (a, b)) is not None
    assert owner.snapshot()["active"] == 3


def test_resource_group_contending_threads_cannot_overbook():
    from skeleton.kernel.global_resource_scheduler import (
        GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy,
        ResourceVector, ResourceRequest,
    )

    owner = GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=100),
        (PlanePolicy("ai", 1, ResourceVector()),),
    ))
    def reserve(index):
        return owner.reserve_group(f"group-{index}", tuple(
            ResourceRequest(f"{index}-{member}", "ai", "t", ResourceVector(cpu_millis=40))
            for member in range(2)
        ))
    with ThreadPoolExecutor(max_workers=2) as pool:
        grants = list(pool.map(reserve, range(2)))
    assert sum(g is not None for g in grants) == 1
    assert owner.usage("ai").cpu_millis == 80
