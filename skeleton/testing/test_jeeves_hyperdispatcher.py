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

def test_fenced_swarm_stale_attempt_and_unknown_effect():
    from skeleton.automation.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState, LeaseError

    tick = [1.0]
    runtime = SwarmRuntime(fenced=True, clock=lambda: tick[0], default_lease_seconds=2)
    runtime.register_worker("w", capacity=1)
    runtime.submit(SwarmTask("task", {}))
    first = runtime.lease("w")[0]
    assert first.lease_token
    with pytest.raises(LeaseError):
        runtime.succeed("w", "task")
    tick[0] = 3
    with pytest.raises(LeaseError):
        runtime.succeed("w", "task", lease_token=first.lease_token)
    assert runtime.reap_expired() == 1
    assert runtime.task("task").effect_uncertain
    assert runtime.worker("w").available == 0
    assert not runtime.lease("w")
    with pytest.raises(LeaseError):
        runtime.revive("task")
    with pytest.raises(LeaseError):
        runtime.unregister_worker("w")
    with pytest.raises(LeaseError):
        runtime.reconcile_uncertain("task", lease_token="wrong", outcome="stopped-no-effect", evidence_sha256="a"*64)
    runtime.reconcile_uncertain("task", lease_token=first.lease_token,
                                outcome="stopped-no-effect", evidence_sha256="a"*64)
    second = runtime.lease("w")[0]
    assert second.lease_token != first.lease_token
    with pytest.raises(LeaseError):
        runtime.succeed("w", "task", lease_token=first.lease_token)
    assert runtime.succeed("w", "task", lease_token=second.lease_token).state is TaskState.SUCCEEDED


def test_fenced_swarm_checkpoint_preserves_uncertainty():
    from skeleton.automation.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState, LeaseError

    runtime = SwarmRuntime(fenced=True, clock=lambda: 10)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}))
    leased = runtime.lease("w")[0]
    restored = SwarmRuntime.from_state(runtime.export_state(), clock=lambda: 1)
    assert restored.task("a").state is TaskState.FAILED
    assert restored.task("a").effect_uncertain and restored.worker("w").available == 0
    with pytest.raises(LeaseError):
        restored.cancel("a")
    restored.reconcile_uncertain("a", lease_token=leased.lease_token,
                                 outcome="committed", evidence_sha256="c"*64)
    assert restored.task("a").state is TaskState.SUCCEEDED
    assert restored.worker("w").available == 1


def test_swarm_graph_dependency_barrier_and_cycle():
    from skeleton.automation.agents.swarm_runtime import SwarmRuntime, SwarmTask, AdmissionError

    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=3)
    with pytest.raises(AdmissionError):
        runtime.submit_graph((SwarmTask("a", {}, dependencies=("b",)),
                              SwarmTask("b", {}, dependencies=("a",))))
    assert not runtime.tasks()
    runtime.submit_graph((SwarmTask("b", {}, priority=0, dependencies=("a",)),
                          SwarmTask("a", {}, priority=100)))
    assert runtime.blocked_dependencies("b") == ("a",)
    assert [t.id for t in runtime.lease("w")] == ["a"]
    runtime.succeed("w", "a")
    assert [t.id for t in runtime.lease("w")] == ["b"]


def test_swarm_terminal_dependency_propagation_and_stale_heap():
    from skeleton.automation.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState

    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit_graph((SwarmTask("parent", {}, max_attempts=1),
                          SwarmTask("child", {}, dependencies=("parent",))))
    runtime.lease("w")
    runtime.fail("w", "parent", "fail")
    assert runtime.cancel_failed_dependents() == ("child",)
    assert runtime.task("child").state is TaskState.CANCELLED
    runtime.submit(SwarmTask("requeued", {}))
    for _ in range(1100):
        runtime.cancel("requeued")
        runtime.revive("requeued")
    assert len(runtime._queue) <= 1024
    assert [t.id for t in runtime.lease("w")] == ["requeued"]


def test_fenced_swarm_worker_failure_without_no_effect_confirmation_holds():
    from skeleton.automation.agents.swarm_runtime import SwarmRuntime, SwarmTask

    runtime = SwarmRuntime(fenced=True)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}))
    lease = runtime.lease("w")[0]
    held = runtime.fail("w", "a", "opaque external failure", lease_token=lease.lease_token)
    assert held.effect_uncertain and runtime.worker("w").available == 0
    assert "opaque external failure" not in (held.last_error or "")

def test_durable_group_receipt_survives_restart_and_rejects_terminal_replay(tmp_path):
    state = ledger(tmp_path)
    a = state.enqueue("jeeves", "a", "a", priority=5, now=1)
    b = state.enqueue("jeeves", "b", "b", priority=5, now=1)
    group = state.promote_group("jeeves", "worker", authorized_tickets=(a, b), now=2, request_id="group")
    restarted = SqliteSharedPressureLedger(state.path)
    assert restarted.promote_group("jeeves", "worker", authorized_tickets=(b, a), now=3, request_id="group") == group
    with pytest.raises(SharedPressureConflict, match="identity"):
        restarted.promote_group("jeeves", "other", authorized_tickets=(a, b), now=3, request_id="group")
    with pytest.raises(SharedPressureConflict, match="identity"):
        restarted.promote_ranked("jeeves", "worker", authorized_tickets=(a, b), now=3, request_id="group")
    restarted.release(group[0].lease_id, "worker")
    with pytest.raises(SharedPressureConflict, match="no longer fully live"):
        restarted.promote_group("jeeves", "worker", authorized_tickets=(a, b), now=3, request_id="group")


def test_ranked_receipt_two_connections_same_request(tmp_path):
    state = ledger(tmp_path, concurrency=1, tenant=1)
    ticket = state.enqueue("jeeves", "a", "a", priority=5, now=1)
    other = SqliteSharedPressureLedger(state.path)
    def promote(db):
        return db.promote_ranked("jeeves", "w", authorized_tickets=(ticket,), now=2, request_id="request")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(promote, (state, other)))
    assert results[0] == results[1] and results[0] is not None
    assert other.snapshot("jeeves", now=2).active == 1


def test_legacy_lease_and_ticket_reuse_fenced_even_same_clock(tmp_path):
    state = ledger(tmp_path)
    first = state.acquire("jeeves", "a", "a", "w", priority=5, now=1)
    state.release(first.lease_id, "w")
    second = state.acquire("jeeves", "a", "a", "w", priority=5, now=1)
    assert second.lease_id != first.lease_id
    with pytest.raises(SharedPressureError):
        state.release(first.lease_id, "w")
    ticket = state.enqueue("jeeves", "b", "b", priority=5, now=1)
    state.dequeue(ticket.ticket_id)
    new_ticket = state.enqueue("jeeves", "b", "b", priority=5, now=1)
    assert new_ticket.ticket_id != ticket.ticket_id
    with pytest.raises(SharedPressureError):
        state.promote(ticket.ticket_id, "w", now=2)


def test_full_queue_can_drain_already_admitted_normal_work(tmp_path):
    state = SqliteSharedPressureLedger(tmp_path / "pressure.sqlite")
    state.configure(SharedPressurePolicy("jeeves", 4, 4, 4, 4, 0.5))
    normal = state.enqueue("jeeves", "a", "normal", priority=100, now=1)
    state.enqueue("jeeves", "a", "urgent1", priority=5, now=1)
    state.enqueue("jeeves", "a", "urgent2", priority=5, now=1)
    state.enqueue("jeeves", "a", "urgent3", priority=5, now=1)
    assert not state.decide("jeeves", "a", priority=100, now=2).admitted
    assert state.promote_ranked("jeeves", "w", authorized_tickets=(normal,), now=2) is not None


def test_replacement_pressure_policy_preserves_existing_tenant_cap(tmp_path):
    state = ledger(tmp_path)
    state.acquire("jeeves", "a", "a", "w", priority=5)
    state.acquire("jeeves", "a", "b", "w", priority=5)
    with pytest.raises(SharedPressureConflict, match="tenant pressure"):
        state.configure(SharedPressurePolicy("jeeves", 4, 32, 1, 16, 1.0), replace=True)

def test_hardened_restore_preserves_queue_generations():
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}))
    restored = HardenedSwarmRuntime.from_state(runtime.export_state())
    assert [t.id for t in restored.lease("w")] == ["a"]


def test_hardened_fenced_checkpoint_and_exact_lease():
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, LeaseError
    from skeleton.automation.agents.swarm_exact_lease import lease_exact
    from skeleton.automation.agents.swarm_fencing import fence_for, fenced_renew, fenced_succeed
    from skeleton.automation.agents.swarm_checkpoint import CheckpointStore
    from skeleton.automation.agents.swarm_invariants import audit
    runtime = HardenedSwarmRuntime(fenced=True, clock=lambda: 10.0)
    runtime.register_worker("w", capacity=2)
    runtime.submit_many((SwarmTask("child", {}, dependencies=("parent",)), SwarmTask("parent", {})))
    with pytest.raises(LeaseError):
        lease_exact(runtime, "w", "child")
    fence = fence_for(lease_exact(runtime, "w", "parent"))
    fenced_renew(runtime, fence)
    assert audit(runtime).ok
    checkpoint = CheckpointStore().capture(runtime)
    restored = HardenedSwarmRuntime.from_state(checkpoint.state, clock=lambda: 1.0)
    assert restored.task("parent").effect_uncertain and restored.worker("w").available == 1
    assert not restored.lease("w")
    assert audit(restored).ok
    restored.reconcile_uncertain("parent", lease_token=fence.lease_token,
                                 outcome="committed", evidence_sha256="a"*64)
    assert restored.task("parent").reconciliation_sha256 == "a"*64
    fenced_succeed(restored, fence_for(lease_exact(restored, "w", "child")))
    assert audit(restored).ok


def test_fenced_broker_and_rollback_fail_closed():
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, LeaseError
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_lease_rollback import rollback_exact_lease
    runtime = HardenedSwarmRuntime(fenced=True)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}))
    runtime.lease("w")
    with pytest.raises(LeaseError):
        SwarmBroker(runtime)
    with pytest.raises(LeaseError):
        rollback_exact_lease(runtime, "w", "a")


def test_hardened_retention_cannot_forget_dependency_or_uncertain():
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, AdmissionError
    runtime = HardenedSwarmRuntime(fenced=True)
    runtime.register_worker("w")
    runtime.submit_many((SwarmTask("parent", {}), SwarmTask("child", {}, dependencies=("parent",))))
    lease = runtime.lease("w")[0]
    runtime.fail("w", "parent", "error", lease_token=lease.lease_token)
    with pytest.raises(AdmissionError):
        runtime.forget("parent")
    runtime.reconcile_uncertain("parent", lease_token=lease.lease_token,
                                outcome="committed", evidence_sha256="a"*64)
    with pytest.raises(AdmissionError):
        runtime.forget("parent")
    runtime.cancel("child")
    assert runtime.forget("child") and runtime.forget("parent")

def test_verified_broker_exact_dispatch_and_reconciliation():
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, LeaseError, TaskState
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    from skeleton.automation.agents.swarm_runtime import AdmissionError

    runtime = HardenedSwarmRuntime(fenced=True, clock=lambda: 10.0)
    runtime.register_worker("worker")
    authorized = set()
    def verify(worker, task, token, action, digest):
        return (worker, task, token, action, digest) in authorized
    broker = SwarmBroker(runtime, verify_worker=verify)
    with pytest.raises(AdmissionError):
        TenantSwarmBroker(broker)
    broker.submit_queued(SwarmTask("unrelated", {}, priority=0))
    broker.submit_queued(SwarmTask("target", {}, priority=10))
    lease = broker.lease_authorized("target")
    assert lease.id == "target"
    assert runtime.task("unrelated").state is TaskState.QUEUED
    with pytest.raises(LeaseError):
        broker.record_success("worker", "target")
    with pytest.raises(LeaseError):
        broker.record_verified("worker", "target", lease_token=lease.lease_token,
                               outcome="success", evidence_sha256="a"*64)
    authorized.add(("worker", "target", lease.lease_token, "uncertain", "b"*64))
    result = broker.record_verified("worker", "target", lease_token=lease.lease_token,
                                    outcome="uncertain", evidence_sha256="b"*64)
    assert result.task.effect_uncertain and runtime.worker("worker").available == 0
    authorized.add(("worker", "target", lease.lease_token, "reconcile:committed", "c"*64))
    resolved = broker.reconcile_verified("worker", "target", lease_token=lease.lease_token,
                                         outcome="committed", evidence_sha256="c"*64)
    assert resolved.task.state is TaskState.SUCCEEDED
    assert resolved.task.reconciliation_sha256 == "c"*64
    assert runtime.worker("worker").available == 1


def test_control_plane_leases_requested_task_not_other_priority_head():
    from skeleton.automation.agents.swarm_control import SwarmControlPlane
    from skeleton.automation.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState

    runtime = SwarmRuntime()
    runtime.register_worker("w")
    control = SwarmControlPlane(runtime)
    control.submit(SwarmTask("urgent", {}, priority=0))
    control.submit(SwarmTask("specific", {}, priority=100))
    assert control.lease_best("specific").id == "specific"
    assert runtime.task("urgent").state is TaskState.QUEUED

def test_batch_planning_isolates_model_tenant_phase_and_protected_work():
    from skeleton.intelligence.dispatch_hardware import BatchIdentity, BatchDemand, BatchLimits, plan_batches
    ident = BatchIdentity("t", "a"*64, "b"*64, "c"*64, "d"*64, "q4", "decode")
    demand = BatchDemand("a", ident, 0, 100, 50, 4, 10, 8, 10)
    bounds = BatchLimits(2, 8, 30, 20, 10, 40)
    rows = [demand, replace(demand, task_id="b"), replace(demand, task_id="c", identity=replace(ident, tenant_id="other")),
            replace(demand, task_id="d", identity=replace(ident, phase="prefill")),
            replace(demand, task_id="e", priority=0)]
    plan = plan_batches(rows, bounds, now_ms=1)
    assert plan == plan_batches(list(reversed(rows)), bounds, now_ms=1)
    assert plan.batches[0].tasks == ("e",)
    assert plan.batches[0].dispatch_now
    pairs = [p for p in plan.batches if len(p.tasks) == 2]
    assert len(pairs) == 1 and pairs[0].tasks == ("a", "b") and pairs[0].dispatch_now
    assert all(not p.dispatch_now for p in plan.batches if p.tasks in {("c",), ("d",)})


def test_batch_planning_memory_padding_and_deadline_bounds():
    from skeleton.intelligence.dispatch_hardware import BatchIdentity, BatchDemand, BatchLimits, plan_batches
    ident = BatchIdentity("t", "a"*64, "b"*64, "c"*64, "d"*64, "q4", "prefill")
    a = BatchDemand("a", ident, 0, 40, 30, 2, 10, 15, 9)
    bounds = BatchLimits(8, 20, 100, 20, 30, 40)
    b = replace(a, task_id="b", context_tokens=4)
    c = replace(a, task_id="c", deadline_ms=5)
    d = replace(a, task_id="d", tokens=21)
    plan = plan_batches([a, b, c, d], bounds, now_ms=1)
    assert plan.rejected == (("c", "deadline_or_service_budget"), ("d", "oversize"))
    assert len(plan.batches) == 2 and all(p.padded_tokens <= 20 for p in plan.batches)
    assert plan_batches([a], bounds, now_ms=30).batches[0].dispatch_now


def test_device_ranking_filters_resource_pressure_topology_thermal_and_age():
    from skeleton.intelligence.dispatch_hardware import DeviceObservation, DeviceDemand, rank_devices
    node = DeviceObservation("n", "gpu0", "numa0", "cuda", frozenset({"fp16"}),
                             1, 10, 100, 100, 100, 100, 100, 100, 100, 50000,
                             frozenset({"a"*64}))
    demand = DeviceDemand("task", "a"*64, frozenset({"cuda"}), frozenset({"fp16"}),
                          50, 50, 0, 20, 20, 10, 200, 70000, "numa0", 1000)
    devices = [replace(node, device_id="gpu1", cached_models=frozenset()),
               node, replace(node, device_id="hot", thermal_millic=71000),
               replace(node, device_id="oom", free_device_bytes=51),
               replace(node, device_id="wrong", accelerator="metal")]
    result = rank_devices(demand, devices, now_ms=11)
    assert [d.device_id for d in result] == ["gpu0", "gpu1"]
    assert result[0].energy_estimate_mj == 100
    assert not rank_devices(demand, devices, now_ms=5011)


def test_negative_capability_invalidation_and_two_choice():
    from skeleton.intelligence.dispatch_hardware import CapabilityMiss, should_requeue, two_choice_indices
    miss = CapabilityMiss("t", frozenset({"cuda"}), 5, 100)
    args = dict(tenant_id="t", requirements=frozenset({"cuda"}), now_ms=50, generation=6)
    assert not should_requeue(miss, changed_capabilities=frozenset({"metal"}), **args)
    assert should_requeue(miss, changed_capabilities=frozenset({"cuda"}), **args)
    assert should_requeue(miss, changed_capabilities=frozenset(), **(args | {"now_ms":100}))
    assert should_requeue(miss, changed_capabilities=frozenset(), **(args | {"tenant_id":"other"}))
    assert len(set(two_choice_indices("task", 4, 2))) == 2
    assert two_choice_indices("task", 4, 1) == (0,)

def test_verified_tenant_quota_retains_uncertain_effect_through_restore():
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, AdmissionError, TaskState
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    from skeleton.automation.agents.swarm_tenant_checkpoint import TenantCheckpointStore
    from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor
    from skeleton.automation.agents.swarm_quota import Quota, QuotaExceeded
    runtime = HardenedSwarmRuntime(fenced=True, clock=lambda: 10.0)
    runtime.register_worker("w", capacity=2)
    verified = set()
    def verify(worker, task, token, action, digest):
        return (worker, task, token, action, digest) in verified
    governor = SwarmIngressGovernor(default_quota=Quota(max_queued=2, max_leased=1))
    broker = TenantSwarmBroker(SwarmBroker(runtime, verify_worker=verify), governor, verified_mode=True)
    assert broker.submit_verified_queued("t", SwarmTask("a", {})).admitted
    assert broker.submit_verified_queued("t", SwarmTask("b", {})).admitted
    with pytest.raises(AdmissionError):
        broker.lease_verified("other", "a")
    attempt = broker.lease_verified("t", "a")
    assert attempt.lease_token
    verified.add(("w", "a", attempt.lease_token, "uncertain", "a"*64))
    result = broker.record_verified("t", "w", "a", lease_token=attempt.lease_token,
                                    outcome="uncertain", evidence_sha256="a"*64)
    assert result.task.effect_uncertain
    assert governor.quota.usage("t").leased == 1
    assert broker.repair().terminalized == 0
    with pytest.raises(QuotaExceeded):
        broker.lease_verified("t", "b")
    store = TenantCheckpointStore()
    checkpoint = store.capture(1, broker)
    restored = HardenedSwarmRuntime.from_state(runtime.export_state(), clock=lambda: 1.0)
    restored_governor = governor.fork_empty()
    restored_broker = TenantSwarmBroker(SwarmBroker(restored, verify_worker=verify), restored_governor,
                                        verified_mode=True)
    store.restore(restored_broker, checkpoint.sequence)
    assert restored_governor.quota.usage("t").leased == 1
    assert restored.task("a").effect_uncertain
    verified.add(("w", "a", attempt.lease_token, "reconcile:committed", "b"*64))
    outcome = restored_broker.reconcile_verified("t", "w", "a", lease_token=attempt.lease_token,
                                                  outcome="committed", evidence_sha256="b"*64)
    assert outcome.task.state is TaskState.SUCCEEDED
    assert restored_governor.quota.usage("t").leased == 0
    assert restored_broker.lease_verified("t", "b").id == "b"


def test_verified_tenant_retry_reserves_queue_quota_before_reconciliation():
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, LeaseError
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor
    from skeleton.automation.agents.swarm_quota import Quota, QuotaExceeded
    runtime = HardenedSwarmRuntime(fenced=True)
    runtime.register_worker("w")
    governor = SwarmIngressGovernor(default_quota=Quota(max_queued=1, max_leased=1))
    permitted = set()
    def verify(worker, task, token, action, digest):
        return (worker, task, token, action, digest) in permitted
    broker = TenantSwarmBroker(SwarmBroker(runtime, verify_worker=verify), governor, verified_mode=True)
    broker.submit_verified_queued("t", SwarmTask("a", {}))
    first = broker.lease_verified("t", "a")
    permitted.add(("w", "a", first.lease_token, "uncertain", "a"*64))
    broker.record_verified("t", "w", "a", lease_token=first.lease_token,
                           outcome="uncertain", evidence_sha256="a"*64)
    with pytest.raises(LeaseError):
        broker.reconcile_verified("t", "w", "a", lease_token=first.lease_token,
                                  outcome="stopped-no-effect", evidence_sha256="b"*64)
    assert governor.quota.usage("t").leased == 1
    assert governor.quota.usage("t").queued == 0
    broker.submit_verified_queued("t", SwarmTask("b", {}))
    permitted.add(("w", "a", first.lease_token, "reconcile:stopped-no-effect", "b"*64))
    with pytest.raises(QuotaExceeded):
        broker.reconcile_verified("t", "w", "a", lease_token=first.lease_token,
                                  outcome="stopped-no-effect", evidence_sha256="b"*64)
    assert runtime.task("a").effect_uncertain and governor.quota.usage("t").leased == 1
    runtime.cancel("b")
    broker.repair()
    broker.reconcile_verified("t", "w", "a", lease_token=first.lease_token,
                              outcome="stopped-no-effect", evidence_sha256="b"*64)
    assert governor.quota.usage("t").queued == 1
    second = broker.lease_verified("t", "a")
    assert second.lease_token != first.lease_token


def test_verified_tenant_replay_and_cross_tenant_dependencies():
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, AdmissionError
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    runtime = HardenedSwarmRuntime(fenced=True)
    broker = TenantSwarmBroker(SwarmBroker(runtime, verify_worker=lambda *args: False),
                               verified_mode=True, max_terminal_records=2)
    task = SwarmTask("a", {"x": 1})
    assert broker.submit_verified_queued("t", task).admitted
    assert broker.submit_verified_queued("t", task).duplicate
    with pytest.raises(AdmissionError):
        broker.submit_verified_queued("other", task)
    with pytest.raises(AdmissionError):
        broker.submit_verified_queued("t", replace(task, priority=4))
    with pytest.raises(AdmissionError):
        broker.submit_verified_queued("other", SwarmTask("b", {}, dependencies=("a",)))
    assert broker.submit_verified_queued("t", SwarmTask("b", {}, dependencies=("a",))).admitted
    with pytest.raises(AdmissionError):
        broker.submit_verified_queued("t", SwarmTask("c", {}))

def test_cognitive_specialists_are_policy_and_evidence_bound():
    from skeleton.intelligence.dispatch_cognitive import CognitiveDemand, SpecialistObservation, choose_specialists
    d = CognitiveDemand("task", "t", "a"*64, "b"*64, "code", frozenset({"code"}),
                        frozenset({"c"*64, "d"*64}), 10, 10, 2, 1, 900000, 100, 20)
    a = SpecialistObservation("a", "t", "c"*64, "family-a", "node-a", "a"*64, "code",
                               frozenset({"code"}), "e"*64, "b"*64, 1, 1, 20, 10, 5, 10000, 9, 10, True, True)
    b = replace(a, worker_id="b", model_sha256="d"*64, family_id="family-b", failure_domain="node-b",
                capabilities=frozenset({"code", "verify"}), source_sha256="f"*64)
    plan = choose_specialists(d, [a, b], now_ms=2)
    assert plan.disposition == "independent_review" and plan.workers == ("a", "b")
    assert plan.reserved_tokens == 40 and plan.reserved_cost == 10
    assert choose_specialists(d, [b, a], now_ms=2) == plan
    for bad in (replace(b, tenant_id="wrong"), replace(b, family_id="family-a"),
                replace(b, failure_domain="node-a"), replace(b, local=False),
                replace(b, policy_sha256="0"*64), replace(b, observed_ms=3),
                replace(b, cost_microunits=16), replace(b, verified_successes=0)):
        assert choose_specialists(d, [a, bad], now_ms=2).disposition == "hold_review_unavailable"
    one = choose_specialists(replace(d, uncertainty_ppm=0), [a], now_ms=2)
    assert one.disposition == "single" and one.plan_sha256 != plan.plan_sha256


def test_hypothesis_aggregation_requires_independent_evidence():
    from skeleton.intelligence.dispatch_cognitive import HypothesisObservation, review_hypotheses
    a = HypothesisObservation("a", "a"*64, "family-a", "node-a", "c"*64, "d"*64, "e"*64, "supports")
    b = replace(a, hypothesis_id="b", model_sha256="b"*64, family_id="family-b",
                failure_domain="node-b", evidence_sha256="f"*64)
    assert review_hypotheses("c"*64, [a, b]).disposition == "candidate_for_external_verification"
    assert review_hypotheses("c"*64, [a, replace(b, evidence_sha256=a.evidence_sha256)]).disposition == "hold_insufficient_independence"
    assert review_hypotheses("c"*64, [a, replace(b, verdict="contradicts")]).disposition == "hold_conflict"
    assert review_hypotheses("c"*64, [a, replace(b, result_sha256="0"*64)]).disposition == "hold_disagreement"

def test_workflow_graph_reduction_never_merges_effectful_or_cross_context_work():
    from skeleton.intelligence.dispatch_workflow import WorkflowNode, reduce_pure_graph
    a = WorkflowNode("a", "tenant", "compile", "a"*64, "b"*64, "c"*64, "d"*64, (), 10, 1, "pure")
    b = replace(a, task_id="b")
    c = replace(a, task_id="c", dependencies=("a",))
    d = replace(c, task_id="d", dependencies=("b",))
    e = replace(a, task_id="e", effect="write")
    f = replace(a, task_id="f", context_sha256="e"*64)
    rows = [a, b, c, d, e, f]
    result = reduce_pure_graph(rows)
    assert result.aliases == (("b", "a"), ("d", "c"))
    assert result.estimated_saved_ms == 20 and set(result.order) == {"a", "c", "e", "f"}
    assert reduce_pure_graph(list(reversed(rows))) == result
    with pytest.raises(DispatchPolicyError):
        reduce_pure_graph([a, replace(c, tenant_id="other")])


def test_semantic_similarity_is_review_only_and_bounded():
    from skeleton.intelligence.dispatch_workflow import WorkflowNode, semantic_review_pairs, reduce_pure_graph
    a = WorkflowNode("a", "tenant", "compile", "a"*64, "b"*64, "c"*64, "d"*64, (), 10, 1,
                     "pure", frozenset({"code", "compile"}))
    b = replace(a, task_id="b", input_sha256="e"*64)
    c = replace(a, task_id="c", tenant_id="other")
    assert [(p.left, p.right) for p in semantic_review_pairs([a, b, c])] == [("a", "b")]
    assert not reduce_pure_graph([a, b, c]).aliases
    with pytest.raises(DispatchPolicyError):
        semantic_review_pairs([a, b, c], pair_budget=1)


def test_compensation_order_and_unknown_barrier():
    from skeleton.intelligence.dispatch_workflow import WorkflowNode, EffectObservation, plan_recovery
    a = WorkflowNode("a", "t", "mutate", "a"*64, "b"*64, "c"*64, "d"*64, (), 10, 1,
                     "write", compensation_id="undo-a")
    b = replace(a, task_id="b", dependencies=("a",), compensation_id="undo-b")
    receipts = [EffectObservation("a", "committed", "e"*64), EffectObservation("b", "committed", "f"*64)]
    allowed = frozenset({"undo-a", "undo-b"})
    assert plan_recovery([a, b], receipts, approved_compensations=allowed).compensation_order == (
        ("b", "undo-b", "f"*64), ("a", "undo-a", "e"*64))
    p = plan_recovery([a, b], receipts[:1], approved_compensations=allowed)
    assert p.hold_tasks == ("b",) and not p.compensation_order
    assert not plan_recovery([a,b], receipts, approved_compensations=frozenset()).compensation_order


def test_wait_graph_detects_components_and_rejects_stale_snapshots():
    from skeleton.intelligence.dispatch_workflow import WaitEdge, wait_cycles
    rows = [WaitEdge("a", "b", "gpu", 1), WaitEdge("b", "a", "ram", 1),
            WaitEdge("c", "a", "disk", 1), WaitEdge("d", "d", "lock", 1)]
    assert wait_cycles(rows, generation=1) == (("a", "b"), ("d",))
    with pytest.raises(DispatchPolicyError):
        wait_cycles(rows, generation=2)


def test_speculative_hedge_rejects_effectful_and_unbudgeted_work():
    from skeleton.intelligence.dispatch_workflow import HedgeObservation, propose_hedge
    o = HedgeObservation("t", "pure", 100, 500, 50, 10, 100, 2, 3, "a", "b")
    assert propose_hedge(o)
    assert not propose_hedge(replace(o, effect="write"))
    assert not propose_hedge(replace(o, spare_units=1))
    assert not propose_hedge(replace(o, alternative_domain="a"))
    assert not propose_hedge(replace(o, deadline_remaining_ms=59))

def _verified_dispatch_fixture():
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    runtime = HardenedSwarmRuntime(fenced=True, clock=lambda: 10.0)
    runtime.register_worker("w", capacity=2)
    broker = TenantSwarmBroker(SwarmBroker(runtime, verify_worker=lambda *args: False), verified_mode=True)
    broker.submit_verified_queued("a", SwarmTask("a", {}, priority=100))
    broker.submit_verified_queued("b", SwarmTask("b", {}, priority=0))
    return runtime, broker


def test_ranked_verified_dispatch_preserves_authorized_set_and_priority():
    from skeleton.automation.agents.swarm_runtime import AdmissionError, TaskState
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    runtime, broker = _verified_dispatch_fixture()
    a = DispatchCandidate("a", "a", 100, 0)
    b = DispatchCandidate("b", "b", 0, 0)
    with pytest.raises(AdmissionError):
        broker.lease_ranked_verified((replace(a, priority=0),), now_ms=10_000)
    with pytest.raises(AdmissionError):
        broker.lease_ranked_verified((replace(a, tenant_id="b"),), now_ms=10_000)
    tenant, task = broker.lease_ranked_verified((a, b), now_ms=10_000)
    assert tenant == "b" and task.id == "b"
    assert runtime.task("a").state is TaskState.QUEUED
    assert broker.lease_ranked_verified((b,), now_ms=10_000) is None


class _DispatcherCheckpointFixture:
    """Instrumented store double: not physical SQLite qualification."""
    def __init__(self):
        self.latest = None
        self.fail = False

    def checkpoint(self, run_id, state, *, worker_id, after_step_id=None, state_version=1):
        from types import SimpleNamespace
        import json
        if self.fail:
            raise OSError("deliberate fixture storage failure")
        self.latest = SimpleNamespace(state=json.loads(json.dumps(state)), state_version=state_version)
        return self.latest

    def resume_state(self, run_id):
        from types import SimpleNamespace
        return SimpleNamespace(checkpoint=self.latest)


def test_verified_dispatch_token_return_requires_durable_readback():
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    runtime, broker = _verified_dispatch_fixture()
    store = _DispatcherCheckpointFixture()
    manager = SwarmRecoveryManager(max_checkpoints=1)
    bridge = SwarmDurableBridge(store)
    tenant, lease, capture = bridge.lease_and_capture_verified(
        "run", "owner", manager, broker, (DispatchCandidate("a", "a", 100, 0),), now_ms=10_000)
    assert tenant == "a" and lease.lease_token
    assert capture.checkpoint is store.latest
    restored = SwarmRecoveryManager.from_archive(store.latest.state).restore_latest()
    assert restored.task("a").effect_uncertain
    assert restored.task("a").lease_token == lease.lease_token


def test_failed_durable_dispatch_holds_capacity_and_preserves_full_ring():
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge, DurableSwarmError
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import AdmissionError
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    runtime, broker = _verified_dispatch_fixture()
    store = _DispatcherCheckpointFixture()
    manager = SwarmRecoveryManager(max_checkpoints=1)
    bridge = SwarmDurableBridge(store)
    initial = bridge.capture("run", "owner", manager, runtime, tenant_broker=broker)
    store.fail = True
    with pytest.raises(DurableSwarmError):
        bridge.lease_and_capture_verified("run", "owner", manager, broker,
            (DispatchCandidate("a", "a", 100, 0),), now_ms=10_000)
    assert manager.store.sequences() == (initial.swarm_sequence,)
    assert manager.tenant_store.sequences() == (initial.swarm_sequence,)
    assert runtime.task("a").effect_uncertain and broker.is_retired()
    assert broker.ingress.quota.usage("a").leased == 1
    with pytest.raises(AdmissionError):
        broker.lease_verified("b", "b")

def test_hierarchical_tenant_limit_applies_across_planes_and_atomic_groups():
    from skeleton.kernel.global_resource_scheduler import (
        GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy,
        ResourceVector, ResourceRequest, TenantResourcePolicy,
    )
    owner = GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=100),
        (PlanePolicy("a", 1, ResourceVector()), PlanePolicy("b", 1, ResourceVector())),
        tenant_limits=(TenantResourcePolicy("t", ResourceVector(cpu_millis=60)),),
    ))
    a = ResourceRequest("a", "a", "t", ResourceVector(cpu_millis=40))
    b = ResourceRequest("b", "b", "t", ResourceVector(cpu_millis=30))
    assert owner.reserve_group("ab", (a, b)) is None
    assert not owner.active_grants() and not owner.queued()
    owner.submit(a)
    grant = owner.admit_request("a")
    owner.submit(b)
    assert owner.admit_request("b") is None
    assert owner.snapshot()["tenant_limits"]["t"]["usage"]["cpu_millis"] == 40
    owner.release(grant.grant_id)
    assert owner.admit_request("b") is not None


def test_deadline_revocation_is_idempotent_and_two_phase():
    from skeleton.kernel.global_resource_scheduler import (
        GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy, ResourceVector, ResourceRequest,
    )
    owner = GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=100), (PlanePolicy("a", 1, ResourceVector()),)))
    owner.submit(ResourceRequest("old", "a", "tenant", ResourceVector(cpu_millis=60), priority=5))
    old = owner.admit_next()
    owner.submit(ResourceRequest("other", "a", "tenant", ResourceVector(cpu_millis=40), priority=5))
    other = owner.admit_next()
    owner.submit(ResourceRequest("urgent", "a", "tenant", ResourceVector(cpu_millis=40),
                                 priority=5, deadline_tick=100, estimated_ticks=2))
    revoking = owner.begin_preemption("urgent")
    assert len(revoking) == 1
    assert owner.begin_preemption("urgent") == revoking
    assert owner.usage("a").cpu_millis == 100
    assert owner.admit_request("urgent") is None
    owner.ack_preempted(revoking[0].grant_id)
    assert owner.admit_request("urgent") is not None
    assert len(owner.active_grants()) == 2


def test_deadline_does_not_admit_expired_work_or_preempt_protected_work():
    from skeleton.kernel.global_resource_scheduler import (
        GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy, ResourceVector, ResourceRequest,
    )
    owner = GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=100), (PlanePolicy("a", 1, ResourceVector()),)))
    owner.submit(ResourceRequest("protected", "a", "t", ResourceVector(cpu_millis=100), priority=0))
    protected = owner.admit_next()
    owner.submit(ResourceRequest("urgent", "a", "t", ResourceVector(cpu_millis=100),
                                 priority=5, deadline_tick=12, estimated_ticks=2))
    assert not owner.begin_preemption("urgent")
    owner.advance(20)
    owner.release(protected.grant_id)
    assert owner.admit_next() is None
    assert owner.snapshot()["deadline_blocked"] == 1

def test_classification_abstains_on_ties_and_rejects_prohibited_labels():
    from skeleton.intelligence.dispatch_expansion import TaskTaxon, classify_labels
    a = TaskTaxon("a", frozenset({"code"}), frozenset({"python"}), frozenset({"write"}))
    b = TaskTaxon("b", frozenset({"code"}), frozenset({"rust"}), frozenset())
    kwargs = dict(policy_sha256="a"*64, evidence_sha256="b"*64)
    assert classify_labels(frozenset({"code"}), [a,b], **kwargs).status == "hold_ambiguous"
    assert classify_labels(frozenset({"code","python"}), [b,a], **kwargs).task_class == "a"
    assert classify_labels(frozenset({"code","python","write"}), [a,b], **kwargs).task_class == "b"
    assert classify_labels(frozenset({"unknown"}), [a,b], **kwargs).status == "hold_unknown"


def test_model_worker_choice_cannot_forge_eligibility_or_observation():
    from skeleton.intelligence.dispatch_expansion import WorkerChoice, validate_model_choice
    from skeleton.intelligence.dispatch_cognitive import binding
    a = WorkerChoice("w", 1, "t", "a"*64, "b"*64, "c"*64)
    pin = binding("eligible-workers-v1", [("w", 1, "t", "a"*64, "b"*64, "c"*64)])
    assert validate_model_choice(a, [a], authorized_set_sha256=pin) == a
    assert validate_model_choice(replace(a, generation=2), [a], authorized_set_sha256=pin) is None
    with pytest.raises(DispatchPolicyError):
        validate_model_choice(a, [replace(a, tenant_id="other")], authorized_set_sha256=pin)


def test_nested_decomposition_preserves_budget_and_rejects_effects():
    from skeleton.intelligence.dispatch_expansion import DecompositionNode, validate_expansion
    root = DecompositionNode("root", None, "plan", "a"*64, "pure", 100, 100, 100)
    a = DecompositionNode("a", "root", "plan", "b"*64, "pure", 60, 60, 60)
    b = DecompositionNode("b", "root", "execute", "c"*64, "pure", 40, 40, 40)
    c = DecompositionNode("c", "a", "execute", "d"*64, "pure", 60, 60, 60, ("b",))
    kwargs = dict(root_id="root", tenant_id="t", policy_sha256="a"*64,
                  approved_operations=frozenset({"plan","execute"}))
    plan = validate_expansion([root,a,b,c], **kwargs)
    assert plan.execution_order == ("b","c") and plan.maximum_depth == 2
    assert plan.token_reservation == 100
    assert validate_expansion([c,b,a,root], **kwargs) == plan
    for change in (replace(c, effect="write"), replace(c, tokens=61),
                   replace(c, dependencies=("a",)), replace(c, parent_id="c")):
        with pytest.raises(DispatchPolicyError):
            validate_expansion([root,a,b,change], **kwargs)


def test_tool_fusion_is_pure_linear_and_policy_bound():
    from skeleton.intelligence.dispatch_expansion import propose_fusion
    from skeleton.intelligence.dispatch_workflow import WorkflowNode
    a = WorkflowNode("a","t","parse","a"*64,"b"*64,"c"*64,"d"*64,(),10,8,"pure")
    b = replace(a, task_id="b", operation="transform", dependencies=("a",))
    c = replace(b, task_id="c", dependencies=("b",))
    kw = dict(eligible_operations=frozenset({"parse","transform"}))
    assert propose_fusion([a,b,c], **kw)[0].tasks == ("a","b","c")
    assert not propose_fusion([a,replace(b,effect="write")], **kw)
    assert not propose_fusion([a,replace(b,policy_sha256="0"*64)], **kw)
    assert not propose_fusion([a,b,replace(c,dependencies=("a",))], **kw)

def test_topology_respects_direction_and_transfer_cost():
    from skeleton.intelligence.dispatch_fabric import FabricLink, transfer_path
    links = [FabricLink("a","b",1,2,1000,"peer",True),
             FabricLink("b","c",1,2,1000,"peer",True),
             FabricLink("a","c",1,1,100,"host",True)]
    kw = dict(bytes_to_copy=1000,generation=1,allowed_transports=frozenset({"peer","host"}))
    path = transfer_path("a","c",links,**kw)
    assert path.endpoints == ("a","b","c") and path.conservative_us == 2_000_004
    assert transfer_path("c","a",links,**kw) is None
    with pytest.raises(DispatchPolicyError):
        transfer_path("a","c",links,**(kw|{"generation":2}))


def test_migration_requires_stop_abi_budget_and_dual_custody():
    from skeleton.intelligence.dispatch_fabric import FabricLink, MigrationSnapshot, propose_migration
    s = MigrationSnapshot("task","t","a","b",1,2,"a"*64,"b"*64,"b"*64,"c"*64,
                          "d"*64,"e"*64,100,200,20,10000,100000,100,True,True)
    link = FabricLink("a","b",1,5,1_000_000,"peer",True)
    kw = dict(topology_generation=1,allowed_transports=frozenset({"peer"}))
    p = propose_migration(s,[link],**kw)
    assert p.target_reservation_bytes == 120
    assert p.required_phases[-1] == "ack-source-release"
    for bad in (replace(s,verified_stop=False),replace(s,target_receipt_verified=False),
                replace(s,target_abi_sha256="0"*64),replace(s,target_free_bytes=119)):
        assert propose_migration(bad,[link],**kw) is None


def test_preload_forecasts_never_borrow_other_tenant_capacity():
    from skeleton.intelligence.dispatch_fabric import PreloadDemand, plan_preloads
    d = PreloadDemand("t","a"*64,"gpu",1,10,"b"*64,900000,5,100,25,60,True)
    rows = [d,replace(d,model_sha256="c"*64,bytes_required=70),
            replace(d,tenant_id="other"),replace(d,model_sha256="d"*64,authorized=False)]
    result = plan_preloads(rows,tenant_id="t",device_id="gpu",generation=1,now_ms=11,
                           spare_bytes=100,spare_io_ms=100)
    assert result == (d,)


def test_pressure_forecast_hysteresis_and_generation():
    from skeleton.intelligence.dispatch_fabric import HealthSample, forecast_pressure
    rows = [HealthSample(0,1,500000,0),HealthSample(10,1,600000,0),HealthSample(20,1,700000,0)]
    assert forecast_pressure(rows,generation=1,horizon_ms=20).state == "throttle"
    flat = [replace(row,pressure_ppm=700000) for row in rows]
    assert forecast_pressure(flat,generation=1,horizon_ms=1,previously_throttled=True).state == "recovering"
    assert forecast_pressure(flat,generation=1,horizon_ms=1).state == "normal"
    with pytest.raises(DispatchPolicyError):
        forecast_pressure(rows,generation=2,horizon_ms=1)

def test_virtual_workers_partition_physical_slots_and_restore_lineage():
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, AdmissionError, LeaseError
    from skeleton.automation.agents.swarm_exact_lease import lease_exact
    from skeleton.automation.agents.swarm_invariants import audit
    runtime = HardenedSwarmRuntime(fenced=True, clock=lambda: 10.0)
    runtime.register_worker("root", capabilities={"code","verify"}, capacity=4)
    runtime.register_virtual_worker("child","root",capabilities={"code"},capacity=3)
    runtime.register_virtual_worker("leaf","child",capabilities={"code"},capacity=2)
    assert runtime.snapshot().available_slots == 4
    assert runtime.worker_lineage("leaf") == ("leaf","child","root")
    with pytest.raises(AdmissionError):
        runtime.register_virtual_worker("over","root",capabilities={"code"},capacity=2)
    with pytest.raises(AdmissionError):
        runtime.register_virtual_worker("wrong","child",capabilities={"verify"},capacity=1)
    runtime.submit(SwarmTask("a", {}, required_capabilities=frozenset({"code"})))
    lease = lease_exact(runtime,"leaf","a")
    assert runtime.snapshot().available_slots == 3 and audit(runtime).ok
    with pytest.raises(LeaseError):
        runtime.unregister_worker("root")
    restored = HardenedSwarmRuntime.from_state(runtime.export_state(),clock=lambda: 1.0)
    assert restored.snapshot().available_slots == 3 and audit(restored).ok
    assert restored.task("a").effect_uncertain
    restored.reconcile_uncertain("a",lease_token=lease.lease_token,outcome="committed",evidence_sha256="a"*64)
    restored.unregister_worker("leaf")
    assert restored.worker("child").available == 3
    restored.unregister_worker("child")
    assert restored.worker("root").available == 4


def test_virtual_worker_quarantine_inherits_parent_boundary():
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    from skeleton.automation.agents.swarm_supervisor import SwarmSupervisor
    runtime = HardenedSwarmRuntime(fenced=True)
    runtime.register_worker("root",capabilities={"code"},capacity=2)
    runtime.register_virtual_worker("child","root",capabilities={"code"},capacity=2)
    task=runtime.submit(SwarmTask("a",{},required_capabilities=frozenset({"code"})))
    supervisor=SwarmSupervisor()
    assert supervisor.dispatch(runtime,task).worker_id=="child"
    supervisor.quarantine_worker("root",reason="host unhealthy")
    assert not supervisor.dispatch(runtime,task).accepted


def test_virtual_worker_restore_rejects_forged_capacity_and_cycles():
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from copy import deepcopy
    runtime=HardenedSwarmRuntime(fenced=True)
    runtime.register_worker("root",capabilities={"code"},capacity=2)
    runtime.register_virtual_worker("child","root",capabilities={"code"},capacity=2)
    state=runtime.export_state()
    over=deepcopy(state)
    next(w for w in over["workers"] if w["id"]=="child")["capacity"]=3
    with pytest.raises(ValueError):
        HardenedSwarmRuntime.from_state(over)
    cycle=deepcopy(state)
    next(w for w in cycle["workers"] if w["id"]=="root")["parent_id"]="child"
    with pytest.raises(ValueError):
        HardenedSwarmRuntime.from_state(cycle)

def test_partitioned_delta_archive_replays_exact_states_and_compacts_anchor():
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    runtime, broker = _verified_dispatch_fixture()
    manager = SwarmRecoveryManager(max_checkpoints=2, delta_archive=True)
    storage = _DispatcherCheckpointFixture()
    bridge = SwarmDurableBridge(storage)
    first = bridge.capture("run","owner",manager,runtime,tenant_broker=broker)
    _, attempt, second = bridge.lease_and_capture_verified(
        "run","owner",manager,broker,(DispatchCandidate("a","a",100,0),),now_ms=10000)
    archive = manager.export_archive()
    assert archive["version"] == 2
    assert [p["tenant"] for p in archive["runtime"][0]["task_partitions"]] == ["a","b"]
    assert [p["tenant"] for p in archive["runtime"][1]["task_partitions"]] == ["a"]
    assert archive["runtime"][1]["previous_sha256"] == archive["runtime"][0]["event_sha256"]
    loaded = bridge.load("run")
    assert loaded.manager.delta_archive
    assert loaded.manager.export_archive_bytes() == manager.export_archive_bytes()
    assert loaded.restore_runtime().task("a").effect_uncertain
    assert loaded.restore_runtime().task("a").lease_token == attempt.lease_token
    bridge.capture("run","owner",manager,runtime,tenant_broker=broker)
    compacted = manager.export_archive()
    assert len(compacted["runtime"]) == 2
    assert compacted["runtime"][0]["sequence"] == second.swarm_sequence
    assert compacted["runtime"][0]["previous_sha256"] == "0"*64
    assert first.swarm_sequence not in manager.store.sequences()
    assert SwarmRecoveryManager.from_archive(compacted).restore_latest().task("a").effect_uncertain


def test_partitioned_journal_rejects_resealed_cross_tenant_patch():
    from copy import deepcopy
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_delta import _digest
    runtime, broker = _verified_dispatch_fixture()
    manager = SwarmRecoveryManager(delta_archive=True)
    manager.checkpoint(runtime,broker)
    attack = deepcopy(manager.export_archive())
    event = attack["runtime"][0]
    event["task_partitions"][0]["tenant"]="foreign"
    event["event_sha256"]=_digest({k:v for k,v in event.items() if k!="event_sha256"})
    attack["archive_checksum"]=manager._archive_checksum({k:v for k,v in attack.items() if k!="archive_checksum"})
    with pytest.raises(ValueError,match="cross-tenant"):
        SwarmRecoveryManager.from_archive(attack)


def test_delta_archive_persists_through_existing_sqlite_run_store(tmp_path):
    # Reuse the existing durable bridge's run-store contract and the existing
    # qualification fixture rather than introducing a second database owner.
    from skeleton.testing.test_durable_run_store import make_store
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    runtime,broker = _verified_dispatch_fixture()
    store=make_store(tmp_path)
    store.create_run("run")
    store.claim_run("run","owner",lease_seconds=60)
    manager=SwarmRecoveryManager(max_checkpoints=2,delta_archive=True)
    bridge=SwarmDurableBridge(store)
    bridge.capture("run","owner",manager,runtime,tenant_broker=broker)
    _,attempt,_=bridge.lease_and_capture_verified("run","owner",manager,broker,
        (DispatchCandidate("a","a",100,0),),now_ms=10000)
    reopened=SwarmDurableBridge(make_store(tmp_path))
    result=reopened.load("run")
    assert result.checkpoint.state_version==2
    recovered=result.restore_runtime()
    assert recovered.task("a").lease_token==attempt.lease_token
    assert recovered.task("a").effect_uncertain

def test_alternative_shared_quota_atomic_overlap_and_reconfiguration():
    from skeleton.automation.agents.swarm_quota import Quota, QuotaLedger, QuotaExceeded, SharedQuota
    ledger = QuotaLedger()
    ledger.configure_shared(SharedQuota("all", Quota(max_queued=4, max_leased=2)))
    ledger.configure_shared(SharedQuota("service", Quota(max_queued=3, max_leased=1), frozenset({"a","b"})))
    ledger.reserve("a", queued=1)
    ledger.reserve("b", queued=1)
    ledger.reserve("c", queued=1)
    ledger.reserve("a", queued=-1, leased=1)
    before = (ledger.snapshot(),ledger.shared_snapshot())
    with pytest.raises(QuotaExceeded):
        ledger.reserve("b", queued=-1, leased=1)
    assert (ledger.snapshot(),ledger.shared_snapshot()) == before
    ledger.reserve("c", queued=-1, leased=1)
    with pytest.raises(QuotaExceeded):
        ledger.configure_shared(SharedQuota("all", Quota(max_leased=1)))
    assert ledger.shared_snapshot()["all"]["leased"]==2
    ledger.release("a",leased=1)
    ledger.reserve("b",queued=-1,leased=1)
    assert ledger.shared_snapshot()["service"]["leased"]==1


def test_alternative_shared_quota_preserved_on_ingress_restore():
    from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor
    from skeleton.automation.agents.swarm_quota import Quota, SharedQuota, QuotaExceeded
    ingress=SwarmIngressGovernor()
    ingress.configure_shared(SharedQuota("all",Quota(max_leased=1)))
    ingress.restore_task("a","x",{},phase="leased")
    empty=ingress.fork_empty()
    assert empty.quota.configured_shared()==ingress.quota.configured_shared()
    empty.restore_task("a","x",{},phase="leased")
    with pytest.raises(QuotaExceeded):
        empty.restore_task("b","y",{},phase="leased")
    assert empty.phase("b","y") is None
    assert empty.quota.shared_snapshot()["all"]["leased"]==1


def test_alternative_shared_quota_serializes_competing_tenants():
    from concurrent.futures import ThreadPoolExecutor
    from skeleton.automation.agents.swarm_quota import Quota, QuotaLedger, SharedQuota, QuotaExceeded
    ledger=QuotaLedger()
    ledger.configure_shared(SharedQuota("all",Quota(max_leased=3)))
    def reserve(index):
        try:
            ledger.reserve(str(index),leased=1)
            return True
        except QuotaExceeded:
            return False
    with ThreadPoolExecutor(max_workers=16) as pool:
        result=list(pool.map(reserve,range(64)))
    assert sum(result)==3
    assert ledger.shared_snapshot()["all"]["leased"]==3

def test_alternative_scaler_holds_stale_and_warming_capacity():
    from skeleton.automation.agents.swarm_autoscale import ElasticPolicy, ScaleTelemetry
    policy=ElasticPolicy(zero_ready_verified=True,warm_retention_ms=100,down_cooldown_ms=50,maximum_step=2)
    t=ScaleTelemetry(1,1000,0,0,0,10,0,2,0)
    assert policy.recommend(t,now_ms=1000,generation=1).desired_slots==0
    assert policy.recommend(t,now_ms=1000,generation=2).desired_slots==2
    assert policy.recommend(t,now_ms=7000,generation=1).desired_slots==2
    assert policy.recommend(replace(t,warming_slots=1),now_ms=1000,generation=1).desired_slots==3
    assert policy.recommend(replace(t,last_demand_ms=950),now_ms=1000,generation=1).desired_slots==1
    assert policy.recommend(replace(t,backlog=100),now_ms=1000,generation=1).desired_slots==4
    assert policy.recommend(replace(t,occupied_slots=2),now_ms=1000,generation=1).desired_slots==2


def test_alternative_idle_retirement_is_fenced_against_registration_reuse():
    from skeleton.automation.agents.swarm_autoscale import propose_idle_retirements, retire_idle_verified
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    now=[1.0]
    runtime=HardenedSwarmRuntime(fenced=True,clock=lambda:now[0])
    runtime.register_worker("w",capacity=2)
    now[0]=20.0
    proposal=propose_idle_retirements(runtime,desired_slots=0,idle_seconds=5)[0]
    kw=dict(verify_stop=lambda *args: True,stop_receipt_sha256="a"*64,desired_slots=0,idle_seconds=5)
    runtime.unregister_worker("w")
    now[0]=1.0
    runtime.register_worker("w",capacity=2)
    now[0]=20.0
    assert not retire_idle_verified(runtime,proposal,**kw)
    fresh=propose_idle_retirements(runtime,desired_slots=0,idle_seconds=5)[0]
    assert retire_idle_verified(runtime,fresh,**kw)
    assert not runtime.workers()


def test_alternative_uncertain_capacity_cannot_be_scaled_away():
    from skeleton.automation.agents.swarm_autoscale import AutoscalePolicy, propose_idle_retirements
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    now=[1.0]
    runtime=HardenedSwarmRuntime(fenced=True,clock=lambda:now[0])
    runtime.register_worker("w",capacity=1)
    runtime.submit(SwarmTask("a",{}))
    attempt=runtime.lease("w")[0]
    runtime.fail("w","a","uncertain",lease_token=attempt.lease_token)
    now[0]=100.0
    rec=AutoscalePolicy(min_slots=0,max_slots=5).recommend(runtime)
    assert rec.current_slots==1 and rec.desired_slots==1
    assert not propose_idle_retirements(runtime,desired_slots=0,idle_seconds=5)

def test_alternative_dequeue_throttle_never_discards_waiting_tasks():
    from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor, DispatchRatePolicy
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    now=[1.0]
    runtime=HardenedSwarmRuntime(fenced=True,clock=lambda:now[0])
    runtime.register_worker("w",capacity=2)
    ingress=SwarmIngressGovernor(dispatch_rate=DispatchRatePolicy(1,1),dispatch_clock=lambda:now[0])
    broker=TenantSwarmBroker(SwarmBroker(runtime,verify_worker=lambda *args:False),ingress,verified_mode=True)
    broker.submit_verified_queued("t",SwarmTask("a",{}))
    broker.submit_verified_queued("t",SwarmTask("b",{}))
    assert broker.lease_verified("t","a") is None
    now[0]=2.0
    assert broker.lease_verified("t","a").id=="a"
    assert broker.lease_verified("t","b") is None
    assert runtime.task("b").state is TaskState.QUEUED
    assert ingress.phase("t","b")=="queued"
    now[0]=3.0
    assert broker.lease_verified("t","b").id=="b"
    clone=ingress.fork_empty()
    assert not clone.try_start("t")
    now[0]=2.0
    assert not clone.try_start("t")


def test_alternative_event_windows_have_hard_wait_and_tenant_isolation():
    from skeleton.intelligence.dispatch_events import EventRecord, WindowPolicy, coalesce_events
    a=EventRecord("a","t","s","k","a"*64,"b"*64,0,1)
    rows=[a,replace(a,event_id="b",arrival_ms=4),replace(a,event_id="c",arrival_ms=8),
          replace(a,event_id="d",arrival_ms=12),replace(a,tenant_id="other")]
    plan=coalesce_events(rows,WindowPolicy(5,10,10,100),now_ms=12)
    t=[p for p in plan if p.scope[0]=="t"]
    assert t[0].event_ids==("a","b","c") and t[0].ready_ms==10 and t[0].ready
    assert t[1].event_ids==("d",) and not t[1].ready
    assert coalesce_events(rows+[a],WindowPolicy(5,10,10,100),now_ms=12)==plan
    with pytest.raises(DispatchPolicyError):
        coalesce_events(rows+[replace(a,payload_sha256="c"*64)],WindowPolicy(5,10,10,100),now_ms=12)


def test_alternative_singleton_holds_uncertain_ownership():
    from skeleton.intelligence.dispatch_events import EventRecord, WindowPolicy, coalesce_events, SingletonObservation, singleton_eligible
    a=EventRecord("a","t","s","k","a"*64,"b"*64,0,1)
    window=coalesce_events([a],WindowPolicy(1,2,10,100),now_ms=3)[0]
    held=SingletonObservation("t","k","a"*64,"previous",1,"uncertain")
    assert not singleton_eligible(window,[held],generation=1)
    assert singleton_eligible(window,[replace(held,phase="released")],generation=1)
    assert singleton_eligible(window,[replace(held,tenant_id="other")],generation=1)
    with pytest.raises(DispatchPolicyError):
        singleton_eligible(window,[held],generation=2)


def test_alternative_event_wait_correlation_preserves_timeout_and_scope():
    from skeleton.intelligence.dispatch_events import EventRecord, WaitIntent, correlate_waits
    a=EventRecord("a","t","s","k","a"*64,"b"*64,5,1)
    wait=WaitIntent("task","t","s","k","a"*64,1,2,10)
    assert correlate_waits([wait],[a],generation=1,now_ms=12)[0].disposition=="event"
    assert correlate_waits([wait],[replace(a,arrival_ms=10)],generation=1,now_ms=12)[0].disposition=="timeout"
    assert correlate_waits([wait],[replace(a,tenant_id="other")],generation=1,now_ms=9)[0].disposition=="waiting"
    with pytest.raises(DispatchPolicyError):
        correlate_waits([wait],[a],generation=2,now_ms=12)

def test_alternative_affinity_round_preserves_headroom_and_cooldown():
    from skeleton.intelligence.dispatch_affinity import Activation, HostRoom, CommunicationEdge, plan_affinity_round
    a=Activation("a","t","left",1,"a"*64,"b"*64,10,True,True,0,2)
    b=replace(a,activation_id="b",host_id="right",state_sha256="c"*64,movable=False)
    hosts=[HostRoom("left","t",1,100,10,10,1),HostRoom("right","t",1,100,10,10,1)]
    kw=dict(tenant_id="t",policy_sha256="a"*64,generation=1,now_ms=100000,minimum_gain_us=1)
    rows=[CommunicationEdge("a","b",100)]
    p=plan_affinity_round([a,b],hosts,rows,**kw)
    assert len(p)==1 and p[0].activation_id=="a" and p[0].target=="right" and p[0].benefit_us==98
    assert not plan_affinity_round([replace(a,last_move_ms=99999),b],hosts,rows,**kw)
    assert not plan_affinity_round([a,b],[hosts[0],replace(hosts[1],usable_bytes=20)],rows,**kw)
    assert not plan_affinity_round([replace(a,idle=False),b],hosts,rows,**kw)


def test_alternative_artifact_plan_dedupes_transfer_but_holds_execution():
    from skeleton.intelligence.dispatch_affinity import ArtifactRef, ArtifactDemand, ArtifactResident, plan_artifacts
    ref=ArtifactRef("t","a"*64,"b"*64,"c"*64,100)
    other=replace(ref,environment_sha256="d"*64)
    demands=[ArtifactDemand("a","gpu",ref,1),ArtifactDemand("b","gpu",ref,2),
             ArtifactDemand("c","gpu",other,3)]
    residents=[ArtifactResident("disk",ref,1,True),ArtifactResident("gpu",other,1,False)]
    kw=dict(generation=1,tenant_id="t",destination_room={"gpu":100},source_bandwidth={"disk":1000},
            total_transfer_bytes=100)
    p=plan_artifacts(demands,residents,**kw)
    assert not p.ready_tasks and p.held_tasks==("a","b","c")
    assert len(p.transfers)==1 and p.transfers[0].tasks==("a","b")
    assert p.transfers[0].reservation_bytes==100
    p2=plan_artifacts(demands,residents+[ArtifactResident("gpu",ref,1,True)],**kw)
    assert p2.ready_tasks==("a","b") and p2.held_tasks==("c",)
    assert not p2.transfers

def test_alternative_nested_subleases_cannot_mint_capacity_or_release_parent():
    from skeleton.kernel.global_resource_scheduler import (
        GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy, ResourceVector,
        ResourceRequest, ResourceConflict,
    )
    scheduler=GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=100), (PlanePolicy("a",1,ResourceVector()),)))
    scheduler.submit(ResourceRequest("root","a","t",ResourceVector(cpu_millis=100)))
    root=scheduler.admit_next()
    child=scheduler.reserve_sublease(root.grant_id,"child","t",ResourceVector(cpu_millis=60))
    leaf=scheduler.reserve_sublease("child","leaf","t",ResourceVector(cpu_millis=40),parent_token=child.token)
    assert scheduler.usage("a").cpu_millis==100
    assert scheduler.allocation_remaining("child").cpu_millis==20
    assert scheduler.reserve_sublease(root.grant_id,"over","t",ResourceVector(cpu_millis=41)) is None
    with pytest.raises(ResourceConflict):
        scheduler.reserve_sublease("child","bad","t",ResourceVector(cpu_millis=1),parent_token="stale")
    with pytest.raises(ResourceConflict):
        scheduler.release(root.grant_id)
    assert [r.sublease_id for r in scheduler.begin_sublease_reclamation("child",token=child.token)]==["leaf","child"]
    kw=dict(evidence_sha256="a"*64,verify_stop=lambda *args:True)
    with pytest.raises(ResourceConflict):
        scheduler.acknowledge_sublease_stop("child",token=child.token,**kw)
    scheduler.acknowledge_sublease_stop("leaf",token=leaf.token,**kw)
    scheduler.acknowledge_sublease_stop("child",token=child.token,**kw)
    assert scheduler.reserve_sublease(root.grant_id,"child","t",ResourceVector(cpu_millis=60)) is None
    assert scheduler.release(root.grant_id).state=="completed"


def test_alternative_root_preemption_drains_nested_allocations_leaf_first():
    from skeleton.kernel.global_resource_scheduler import (
        GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy, ResourceVector,
        ResourceRequest, ResourceConflict,
    )
    owner=GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=10),(PlanePolicy("a",1,ResourceVector()),)))
    owner.submit(ResourceRequest("old","a","t",ResourceVector(cpu_millis=10),priority=9))
    root=owner.admit_next()
    child=owner.reserve_sublease(root.grant_id,"child","t",ResourceVector(cpu_millis=5))
    owner.submit(ResourceRequest("new","a","t",ResourceVector(cpu_millis=10),priority=0))
    assert owner.begin_preemption("new")[0].grant_id==root.grant_id
    assert owner.subleases(root.grant_id)[0].state=="revoking"
    assert owner.usage("a").cpu_millis==10
    with pytest.raises(ResourceConflict):
        owner.ack_preempted(root.grant_id)
    owner.acknowledge_sublease_stop("child",token=child.token,evidence_sha256="a"*64,
                                    verify_stop=lambda *args:True)
    owner.ack_preempted(root.grant_id)
    assert owner.admit_next().request_id=="new"

def test_alternative_durable_unique_job_replays_same_resident():
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    runtime,broker=_verified_dispatch_fixture()
    manager=SwarmRecoveryManager(delta_archive=True)
    bridge=SwarmDurableBridge(_DispatcherCheckpointFixture())
    task=SwarmTask("unique",{"job":1})
    assert bridge.submit_unique_verified("run","owner",manager,broker,"a",task)
    assert bridge.submit_unique_verified("run","owner",manager,broker,"a",task)
    restored=bridge.load("run").restore_runtime()
    assert len([t for t in restored.tasks() if t.id=="unique"])==1
    assert broker.ingress.quota.usage("a").queued==2


def test_alternative_durable_outcome_and_followups_are_one_archive():
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge, DurableSwarmError
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    runtime,broker=_verified_dispatch_fixture()
    broker.broker._verify_worker=lambda *args:True
    attempt=broker.lease_verified("a","a")
    broker.record_verified("a","w","a",lease_token=attempt.lease_token,
                           outcome="uncertain",evidence_sha256="a"*64)
    manager=SwarmRecoveryManager(delta_archive=True)
    store=_DispatcherCheckpointFixture()
    bridge=SwarmDurableBridge(store)
    bridge.capture("run","owner",manager,runtime,tenant_broker=broker)
    bridge.reconcile_and_enqueue_verified("run","owner",manager,broker,"a","a","w",
        lease_token=attempt.lease_token,evidence_sha256="b"*64,
        followups=(SwarmTask("next",{},dependencies=("a",)),))
    restored=bridge.load("run").restore_runtime()
    assert restored.task("a").state is TaskState.SUCCEEDED
    assert restored.task("next").state is TaskState.QUEUED
    assert not restored.blocked_dependencies("next")


def test_alternative_failed_continuation_publication_retires_owner():
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge, DurableSwarmError
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    runtime,broker=_verified_dispatch_fixture()
    broker.broker._verify_worker=lambda *args:True
    attempt=broker.lease_verified("a","a")
    broker.record_verified("a","w","a",lease_token=attempt.lease_token,
                           outcome="uncertain",evidence_sha256="a"*64)
    manager=SwarmRecoveryManager(delta_archive=True)
    store=_DispatcherCheckpointFixture()
    bridge=SwarmDurableBridge(store)
    bridge.capture("run","owner",manager,runtime,tenant_broker=broker)
    store.fail=True
    with pytest.raises(DurableSwarmError):
        bridge.reconcile_and_enqueue_verified("run","owner",manager,broker,"a","a","w",
            lease_token=attempt.lease_token,evidence_sha256="b"*64,
            followups=(SwarmTask("next",{},dependencies=("a",)),))
    assert broker.is_retired()
    recovered=bridge.load("run").restore_runtime()
    assert recovered.task("a").effect_uncertain and recovered.task("next") is None
