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

def _verified_dispatch_fixture(*, verify_worker=None):
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    runtime = HardenedSwarmRuntime(fenced=True, clock=lambda: 10.0)
    runtime.register_worker("w", capacity=2)
    broker = TenantSwarmBroker(SwarmBroker(runtime, verify_worker=verify_worker if verify_worker is not None else lambda *args: False), verified_mode=True)
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

def test_alternative_weighted_shard_ownership_is_stable_and_capacity_bounded():
    from skeleton.automation.agents.swarm_sharding import ShardMember, ResidentShard, weighted_owners, plan_resident_rebalance
    a=ShardMember("a",1,1,1000,50,False)
    b=ShardMember("b",1,2,100,50)
    c=ShardMember("c",1,5,100,50)
    members=(a,b,c)
    shards=tuple(ResidentShard(str(i),"t","a","a"*64,10,1,i!=0) for i in range(5))
    assert weighted_owners("key",members,generation=1,replicas=3)==weighted_owners("key",tuple(reversed(members)),generation=1,replicas=3)
    counts={key:0 for key in ("b","c")}
    for i in range(1000):
        counts[weighted_owners(str(i),members,generation=1)[0]]+=1
    assert counts["c"]>counts["b"]
    p=plan_resident_rebalance(shards,members,tenant_id="t",generation=1,max_moves=2,max_bytes=20)
    assert len(p.moves)==2 and p.reserved_bytes==20 and "0" in p.held
    assert p==plan_resident_rebalance(tuple(reversed(shards)),tuple(reversed(members)),tenant_id="t",generation=1,max_moves=2,max_bytes=20)
    assert all(m.source=="a" and m.target in {"b","c"} for m in p.moves)
    with pytest.raises(ValueError):
        plan_resident_rebalance(shards,members,tenant_id="wrong",generation=1)


def test_alternative_passivation_ranks_memory_with_generation_and_slot_floor():
    from skeleton.automation.agents.swarm_autoscale import WorkerMemoryObservation, _retirement_identity, propose_memory_passivation
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    now=[1.0]
    runtime=HardenedSwarmRuntime(fenced=True,clock=lambda:now[0])
    for key in ("a","b","c"):
        runtime.register_worker(key,capacity=1)
    now[0]=100.0
    rows=tuple(WorkerMemoryObservation(key,_retirement_identity(runtime.worker(key)),100.0,size,10)
               for key,size in (("a",5),("b",100),("c",50)))
    result=propose_memory_passivation(runtime,rows,reclaim_bytes=100,desired_slots=2,idle_seconds=5)
    assert [r.worker_id for r in result]==["b"]
    stale=tuple(replace(row,observed_seconds=1.0) for row in rows)
    assert not propose_memory_passivation(runtime,stale,reclaim_bytes=100,desired_slots=0,idle_seconds=5)
    assert not propose_memory_passivation(runtime,rows,reclaim_bytes=100,desired_slots=3,idle_seconds=5)


def test_alternative_copy_compute_overlap_respects_staging_and_deadlines():
    from skeleton.intelligence.dispatch_affinity import PipelineJob, plan_compute_transfer_overlap
    jobs=[PipelineJob("a",10,100,10,1000,5),PipelineJob("b",10,100,10,1000,5)]
    parallel=plan_compute_transfer_overlap(jobs,staging_bytes=20,dedicated_copy_verified=True,horizon_us=1000)
    serial=plan_compute_transfer_overlap(jobs,staging_bytes=20,dedicated_copy_verified=False,horizon_us=1000)
    limited=plan_compute_transfer_overlap(jobs,staging_bytes=10,dedicated_copy_verified=True,horizon_us=1000)
    assert parallel.makespan_us==210 and parallel.peak_staging_bytes==20
    assert serial.makespan_us==limited.makespan_us==220
    assert parallel.intervals[1].transfer_start_us==10
    assert not plan_compute_transfer_overlap(jobs,staging_bytes=0,dedicated_copy_verified=True,horizon_us=1000).intervals
    assert plan_compute_transfer_overlap(jobs,staging_bytes=20,dedicated_copy_verified=True,horizon_us=110).held==("b",)

def test_alternative_measured_policy_comparison_reports_real_compute_samples():
    from skeleton.intelligence.dispatch_advisory import ShadowTask, measure_shadow_policies
    from dataclasses import asdict
    import json
    rows=tuple(ShadowTask(str(i),str(i%7),i//4,1+i%31,0 if i%13==0 else 50,
                          i//4+80) for i in range(128))
    results=measure_shadow_policies(rows,slots=8,repetitions=3)
    assert len(results)==5 and len({r.workload_sha256 for r in results})==1
    assert all(len(r.samples_ns)==3 and 0<=r.median_ns<=r.p95_ns for r in results)
    assert all(len(r.timeline_sha256)==64 for r in results)
    print("DISPATCH_INTERNAL_MICROBENCHMARK "+json.dumps([asdict(r) for r in results],sort_keys=True))


def test_alternative_mixed_workload_recovery_with_real_sqlite_and_shared_quota(tmp_path):
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor
    from skeleton.automation.agents.swarm_quota import SharedQuota, Quota
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge
    from skeleton.testing.test_durable_run_store import make_store
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    runtime=HardenedSwarmRuntime(fenced=True,clock=lambda:10.0)
    runtime.register_worker("root",capabilities={"code"},capacity=3)
    runtime.register_virtual_worker("child","root",capabilities={"code"},capacity=2)
    governor=SwarmIngressGovernor()
    governor.configure_shared(SharedQuota("all",Quota(max_queued=8,max_leased=1)))
    broker=TenantSwarmBroker(SwarmBroker(runtime,verify_worker=lambda *args: True),governor,verified_mode=True)
    store=make_store(tmp_path)
    store.create_run("mixed")
    store.claim_run("mixed","owner",lease_seconds=60)
    manager=SwarmRecoveryManager(max_checkpoints=4,delta_archive=True)
    bridge=SwarmDurableBridge(store)
    for tenant,task in (("t",SwarmTask("urgent",{},priority=0,required_capabilities=frozenset({"code"}))),
                        ("u",SwarmTask("normal",{},priority=100))):
        assert bridge.submit_unique_verified("mixed","owner",manager,broker,tenant,task)
    tenant,attempt,_=bridge.lease_and_capture_verified("mixed","owner",manager,broker,
        (DispatchCandidate("normal","u",100,0),DispatchCandidate("urgent","t",0,0)),now_ms=10000)
    assert tenant=="t" and attempt.id=="urgent"
    assert bridge.lease_and_capture_verified("mixed","owner",manager,broker,
        (DispatchCandidate("normal","u",100,0),),now_ms=10000) is None
    loaded=SwarmDurableBridge(make_store(tmp_path)).load("mixed")
    recovered=loaded.restore_runtime()
    restored_governor=governor.fork_empty()
    replacement=TenantSwarmBroker(SwarmBroker(recovered,verify_worker=lambda *args:True),
                                  restored_governor,verified_mode=True)
    loaded.manager.restore_tenants(replacement)
    assert recovered.task("urgent").effect_uncertain
    assert restored_governor.quota.shared_snapshot()["all"]["leased"]==1
    resumed=SwarmDurableBridge(make_store(tmp_path))
    resumed.reconcile_and_enqueue_verified("mixed","owner",loaded.manager,replacement,"t","urgent",attempt.leased_to,
        lease_token=attempt.lease_token,evidence_sha256="a"*64,
        followups=(SwarmTask("followup",{},dependencies=("urgent",)),))
    final=resumed.load("mixed").restore_runtime()
    assert final.task("urgent").state is TaskState.SUCCEEDED
    assert final.task("followup").state is TaskState.QUEUED and not final.blocked_dependencies("followup")
    assert final.task("normal").state is TaskState.QUEUED


def test_alternative_wait_is_enforced_by_both_lease_paths_and_restore():
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, LeaseError, AdmissionError
    from skeleton.automation.agents.swarm_exact_lease import lease_exact
    from skeleton.automation.agents.swarm_invariants import audit
    runtime=HardenedSwarmRuntime(fenced=True,clock=lambda:10.0)
    runtime.register_worker("w",capacity=2)
    task=SwarmTask("wait",{},wait_intent_sha256="a"*64)
    runtime.submit(task)
    assert not runtime.lease("w")
    with pytest.raises(LeaseError):
        lease_exact(runtime,"w","wait")
    with pytest.raises(AdmissionError):
        runtime.open_wait("wait",intent_sha256="b"*64,receipt_sha256="c"*64)
    state=runtime.export_state()
    assert state["version"]==3
    with pytest.raises(ValueError):
        HardenedSwarmRuntime.from_state(dict(state,version=2))
    restored=HardenedSwarmRuntime.from_state(state,clock=lambda:10.0)
    assert restored.dispatch_blocked("wait")
    restored.open_wait("wait",intent_sha256="a"*64,receipt_sha256="b"*64)
    assert not restored.dispatch_blocked("wait")
    assert lease_exact(restored,"w","wait").wake_receipt_sha256=="b"*64
    assert audit(restored).ok


def test_alternative_singleton_remains_occupied_after_uncertain_restart():
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_runtime import SwarmTask, AdmissionError
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_invariants import audit
    runtime=HardenedSwarmRuntime(fenced=True,clock=lambda:10.0)
    runtime.register_worker("w",capacity=3)
    broker=TenantSwarmBroker(SwarmBroker(runtime,verify_worker=lambda *args:True),verified_mode=True)
    for tenant,task_id in (("t","a"),("t","b"),("u","c")):
        assert broker.submit_verified_queued(tenant,SwarmTask(task_id,{}),singleton_key="same").admitted
    assert broker.submit_verified_queued("t",SwarmTask("a",{}),singleton_key="same").duplicate
    with pytest.raises(AdmissionError):
        broker.submit_verified_queued("t",SwarmTask("a",{}),singleton_key="different")
    a=broker.lease_verified("t","a")
    assert broker.lease_verified("t","b") is None
    assert broker.lease_verified("u","c").id=="c"
    manager=SwarmRecoveryManager(delta_archive=True)
    manager.checkpoint(runtime,broker)
    loaded=SwarmRecoveryManager.from_archive(manager.export_archive())
    recovered=loaded.restore_latest()
    restored=TenantSwarmBroker(SwarmBroker(recovered,verify_worker=lambda *args:True),
                               broker.ingress.fork_empty(),verified_mode=True)
    loaded.restore_tenants(restored)
    assert recovered.task("a").effect_uncertain and recovered.dispatch_blocked("b")
    assert restored.lease_verified("t","b") is None
    restored.reconcile_verified("t","w","a",lease_token=a.lease_token,
                                 outcome="committed",evidence_sha256="a"*64)
    assert restored.lease_verified("t","b").id=="b"
    assert audit(recovered).ok


def test_alternative_wake_commits_before_lease_and_survives_sqlite_reopen(tmp_path):
    from skeleton.testing.test_durable_run_store import make_store
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge, DurableSwarmError
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    runtime,broker=_verified_dispatch_fixture()
    store=make_store(tmp_path)
    store.create_run("wait")
    store.claim_run("wait","owner",lease_seconds=60)
    manager=SwarmRecoveryManager(delta_archive=True)
    bridge=SwarmDurableBridge(store)
    assert bridge.submit_unique_verified("wait","owner",manager,broker,"a",
                                        SwarmTask("deferred",{},wait_intent_sha256="a"*64))
    candidate=(DispatchCandidate("deferred","a",100,0),)
    assert bridge.lease_and_capture_verified("wait","owner",manager,broker,candidate,now_ms=10000) is None
    with pytest.raises(DurableSwarmError):
        bridge.wake_and_capture_verified("wait","owner",manager,broker,"a","deferred",
                intent_sha256="a"*64,receipt_sha256="b"*64,verify_wake=lambda *args:False)
    assert runtime.dispatch_blocked("deferred")
    bridge.wake_and_capture_verified("wait","owner",manager,broker,"a","deferred",
                intent_sha256="a"*64,receipt_sha256="b"*64,verify_wake=lambda *args:True)
    restored=SwarmDurableBridge(make_store(tmp_path)).load("wait").restore_runtime()
    assert not restored.dispatch_blocked("deferred")
    assert restored.task("deferred").wake_receipt_sha256=="b"*64
    assert bridge.lease_and_capture_verified("wait","owner",manager,broker,candidate,now_ms=10000)[1].id=="deferred"


def test_alternative_ambiguous_wake_retires_generation_without_durable_open():
    from skeleton.automation.agents.swarm_runtime import SwarmTask, AdmissionError
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge, DurableSwarmError
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    runtime,broker=_verified_dispatch_fixture()
    store=_DispatcherCheckpointFixture()
    bridge=SwarmDurableBridge(store)
    manager=SwarmRecoveryManager(delta_archive=True)
    bridge.submit_unique_verified("run","owner",manager,broker,"a",
                                   SwarmTask("wait",{},wait_intent_sha256="a"*64))
    store.fail=True
    with pytest.raises(DurableSwarmError):
        bridge.wake_and_capture_verified("run","owner",manager,broker,"a","wait",
            intent_sha256="a"*64,receipt_sha256="b"*64,verify_wake=lambda *args:True)
    assert broker.is_retired()
    assert bridge.load("run").restore_runtime().dispatch_blocked("wait")
    with pytest.raises(AdmissionError):
        broker.lease_verified("a","wait")


def test_alternative_policy_seal_is_stable_across_accounting_and_forks():
    from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor, DispatchRatePolicy
    from skeleton.automation.agents.swarm_quota import SharedQuota, Quota
    governor=SwarmIngressGovernor(dispatch_rate=DispatchRatePolicy(2,3))
    governor.configure_shared(SharedQuota("service",Quota(max_leased=2),frozenset({"a","b"})))
    governor.configure_tenant("a",weight=2)
    seal=governor.policy_sha256()
    assert governor.admit("a","one",{}).accepted
    assert governor.admit("b","two",{}).accepted
    assert governor.policy_sha256()==seal
    assert governor.fork_empty().policy_sha256()==seal
    governor.configure_tenant("b",weight=3)
    assert governor.policy_sha256()!=seal


def test_alternative_restore_refuses_relaxed_quota_without_mutation():
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor
    from skeleton.automation.agents.swarm_quota import SharedQuota, Quota
    runtime,broker=_verified_dispatch_fixture()
    broker.ingress.configure_shared(SharedQuota("all",Quota(max_leased=1)))
    manager=SwarmRecoveryManager(delta_archive=True)
    manager.checkpoint(runtime,broker)
    archive=manager.export_archive()
    assert archive["tenant"][0]["policy_sha256"]==broker.ingress.policy_sha256()
    loaded=SwarmRecoveryManager.from_archive(archive)
    recovered=loaded.restore_latest()
    relaxed=TenantSwarmBroker(SwarmBroker(recovered,verify_worker=lambda *args:True),
                               SwarmIngressGovernor(),verified_mode=True)
    with pytest.raises(ValueError,match="policy"):
        loaded.restore_tenants(relaxed)
    assert relaxed.status()["tracked_tasks"]==0
    assert relaxed.status()["ingress"]["accounted_tasks"]==0
    exact=TenantSwarmBroker(SwarmBroker(recovered,verify_worker=lambda *args:True),
                             broker.ingress.fork_empty(),verified_mode=True)
    loaded.restore_tenants(exact)
    assert exact.status()["tracked_tasks"]==2
    assert exact.ingress.policy_sha256()==broker.ingress.policy_sha256()


def test_alternative_policy_seal_is_covered_by_tenant_checksum():
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from copy import deepcopy
    runtime,broker=_verified_dispatch_fixture()
    manager=SwarmRecoveryManager()
    manager.checkpoint(runtime,broker)
    archive=deepcopy(manager.export_archive())
    archive["tenant"][0]["policy_sha256"]="0"*64
    archive["archive_checksum"]=manager._archive_checksum({k:v for k,v in archive.items() if k!="archive_checksum"})
    with pytest.raises(ValueError,match="checksum"):
        SwarmRecoveryManager.from_archive(archive)


def _host_wait_driver_fixture(tmp_path, *, clock, key=b"k" * 32):
    from skeleton.testing.test_durable_run_store import make_store
    from skeleton.automation.agents.swarm_durable import HostWaitDriver, SwarmDurableBridge
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    runtime, broker = _verified_dispatch_fixture(verify_worker=lambda *args: True)
    store = make_store(tmp_path)
    store.create_run("host-wait")
    store.claim_run("host-wait", "owner", lease_seconds=60)
    bridge = SwarmDurableBridge(store)
    manager = SwarmRecoveryManager(delta_archive=True)
    driver = HostWaitDriver(bridge, "host-wait", "owner", manager, broker,
                            source_keys={("a", "source"): key}, clock_ms=clock)
    return runtime, broker, bridge, manager, driver


def test_host_timer_restarts_and_releases_only_due_exact_tasks(tmp_path):
    from skeleton.testing.test_durable_run_store import make_store
    from skeleton.automation.agents.swarm_durable import HostWaitDriver, HostWaitIntent, SwarmDurableBridge
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    now = [10]
    runtime, broker, bridge, manager, driver = _host_wait_driver_fixture(tmp_path, clock=lambda: now[0])
    for name, deadline in (("late", 30), ("a-early", 20), ("b-early", 20)):
        intent = HostWaitIntent("host-wait", "a", name, "timer", "host-clock", "deadline", deadline)
        assert driver.submit(intent, SwarmTask(name, {}))
    assert driver.poll_due_timers() == ()
    reloaded_bridge = SwarmDurableBridge(make_store(tmp_path))
    loaded = reloaded_bridge.load("host-wait")
    recovered = loaded.restore_runtime()
    replacement = TenantSwarmBroker(SwarmBroker(recovered, verify_worker=lambda *args: True),
                                   broker.ingress.fork_empty(), verified_mode=True)
    loaded.manager.restore_tenants(replacement)
    restarted = HostWaitDriver(reloaded_bridge, "host-wait", "owner", loaded.manager,
                               replacement, source_keys={}, clock_ms=lambda: now[0])
    now[0] = 20
    assert restarted.poll_due_timers(limit=1) == ("a-early",)
    assert restarted.poll_due_timers(limit=1) == ("b-early",)
    assert restarted.poll_due_timers() == ()
    now[0] = 30
    assert restarted.poll_due_timers() == ("late",)
    final = reloaded_bridge.load("host-wait").restore_runtime()
    for name in ("late", "a-early", "b-early"):
        assert not final.dispatch_blocked(name)
        assert final.task(name).wake_receipt_sha256


def test_host_event_rejects_forgery_cross_scope_future_and_conflicting_receipt(tmp_path):
    from dataclasses import replace
    from skeleton.automation.agents.swarm_durable import HostEventReceipt, HostWaitIntent, DurableSwarmError
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    runtime, broker, bridge, manager, driver = _host_wait_driver_fixture(tmp_path, clock=lambda: 50)
    intent = HostWaitIntent("host-wait", "a", "event", "event", "source", "finished", 20, 60)
    other = replace(intent, task_id="other")
    for wait in (intent, other):
        assert driver.submit(wait, SwarmTask(wait.task_id, {}))
    with pytest.raises(DurableSwarmError):
        driver.submit(replace(intent, tenant="b", task_id="outside"), SwarmTask("outside", {}))
    receipt = HostEventReceipt.issue(intent, event_id="one", evidence_sha256="a" * 64,
                                     observed_ms=40, source_key=b"k" * 32)
    forged = HostEventReceipt.issue(intent, event_id="one", evidence_sha256="a" * 64,
                                    observed_ms=40, source_key=b"x" * 32)
    future = HostEventReceipt.issue(intent, event_id="two", evidence_sha256="a" * 64,
                                    observed_ms=55, source_key=b"k" * 32)
    old = HostEventReceipt.issue(intent, event_id="old", evidence_sha256="a" * 64,
                                 observed_ms=19, source_key=b"k" * 32)
    for invalid in (forged, future, old, replace(receipt, evidence_sha256="b" * 64)):
        with pytest.raises(DurableSwarmError):
            driver.deliver_event("a", "event", invalid)
    with pytest.raises(DurableSwarmError):
        driver.deliver_event("a", "other", receipt)
    assert runtime.dispatch_blocked("event")
    driver.deliver_event("a", "event", receipt)
    driver.deliver_event("a", "event", receipt)
    assert not runtime.dispatch_blocked("event")
    assert runtime.dispatch_blocked("other")
    conflicting = HostEventReceipt.issue(intent, event_id="different", evidence_sha256="a" * 64,
                                         observed_ms=40, source_key=b"k" * 32)
    with pytest.raises(DurableSwarmError):
        driver.deliver_event("a", "event", conflicting)
    assert bridge.load("host-wait").restore_runtime().task("event").wake_receipt_sha256 == receipt.digest


def test_host_timer_refuses_unbound_or_forged_envelope(tmp_path):
    from skeleton.automation.agents.swarm_durable import HostWaitIntent, DurableSwarmError
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    runtime, broker, bridge, manager, driver = _host_wait_driver_fixture(tmp_path, clock=lambda: 50)
    intent = HostWaitIntent("host-wait", "a", "forged", "timer", "host-clock", "deadline", 20)
    assert bridge.submit_unique_verified(
        "host-wait", "owner", manager, broker, "a",
        SwarmTask("forged", {"_jeeves_host_wait_v1": intent.record()}, wait_intent_sha256="a" * 64),
    )
    with pytest.raises(DurableSwarmError, match="identity"):
        driver.poll_due_timers()
    assert runtime.dispatch_blocked("forged")


def test_verified_normal_completion_persists_before_success_ack(tmp_path):
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    runtime, broker, bridge, manager, driver = _host_wait_driver_fixture(tmp_path, clock=lambda: 50)
    bridge.submit_unique_verified("host-wait", "owner", manager, broker, "a", SwarmTask("normal", {}))
    _, task, _ = bridge.lease_and_capture_verified(
        "host-wait", "owner", manager, broker,
        (DispatchCandidate("normal", "a", 100, 0),), now_ms=10000,
    )
    result, _ = bridge.finish_and_capture_verified(
        "host-wait", "owner", manager, broker, "a", "normal",
        worker_id=task.leased_to, lease_token=task.lease_token, outcome="success",
        evidence_sha256="a" * 64,
    )
    assert result.state is TaskState.SUCCEEDED
    assert bridge.load("host-wait").restore_runtime().task("normal").state is TaskState.SUCCEEDED


def test_verified_completion_ambiguous_write_retires_and_restores_attempt():
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge, DurableSwarmError
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    runtime, broker = _verified_dispatch_fixture(verify_worker=lambda *args: True)
    store = _DispatcherCheckpointFixture()
    bridge = SwarmDurableBridge(store)
    manager = SwarmRecoveryManager(delta_archive=True)
    bridge.submit_unique_verified("run", "owner", manager, broker, "a", SwarmTask("normal", {}))
    _, task, _ = bridge.lease_and_capture_verified(
        "run", "owner", manager, broker, (DispatchCandidate("normal", "a", 100, 0),), now_ms=10000,
    )
    store.fail = True
    with pytest.raises(DurableSwarmError, match="restore"):
        bridge.finish_and_capture_verified(
            "run", "owner", manager, broker, "a", "normal", worker_id=task.leased_to,
            lease_token=task.lease_token, outcome="success", evidence_sha256="a" * 64,
        )
    assert broker.is_retired()
    assert bridge.load("run").restore_runtime().task("normal").effect_uncertain


def test_verified_uncertain_reconciliation_durable_retry(tmp_path):
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    runtime, broker, bridge, manager, driver = _host_wait_driver_fixture(tmp_path, clock=lambda: 50)
    bridge.submit_unique_verified("host-wait", "owner", manager, broker, "a", SwarmTask("retry", {}))
    _, task, _ = bridge.lease_and_capture_verified(
        "host-wait", "owner", manager, broker, (DispatchCandidate("retry", "a", 100, 0),), now_ms=10000,
    )
    uncertain, _ = bridge.finish_and_capture_verified(
        "host-wait", "owner", manager, broker, "a", "retry", worker_id=task.leased_to,
        lease_token=task.lease_token, outcome="uncertain", evidence_sha256="a" * 64,
    )
    assert uncertain.effect_uncertain
    retry, _ = bridge.reconcile_and_capture_verified(
        "host-wait", "owner", manager, broker, "a", "retry", worker_id=task.leased_to,
        lease_token=task.lease_token, outcome="stopped-no-effect", evidence_sha256="b" * 64,
    )
    assert retry.state is TaskState.QUEUED and not retry.effect_uncertain
    assert bridge.load("host-wait").restore_runtime().task("retry").state is TaskState.QUEUED


def test_host_worker_authority_uses_pinned_bytes_and_separate_action_grants():
    from dataclasses import replace
    from hashlib import sha256
    from skeleton.automation.agents.swarm_durable import HostWorkerAuthority, HostWorkerReceipt, DurableSwarmError
    artifact = b"verified external evidence"
    pin = sha256(artifact).hexdigest()
    worker_key, reconcile_key = b"w" * 32, b"r" * 32
    bundles = {}
    verifier = HostWorkerAuthority(
        "run", grants={
            ("worker", "w"): (worker_key, frozenset({"success", "uncertain"})),
            ("inspector", "w"): (reconcile_key, frozenset({"reconcile:committed"})),
        }, resolve=bundles.get, validate_evidence=lambda receipt, raw: raw == artifact,
    )
    def issue(issuer, action, key, **changes):
        fields = dict(run_id="run", issuer=issuer, worker_id="w", task_id="t",
                      lease_token="a" * 32, action=action, artifact_sha256=pin, issuer_key=key)
        fields.update(changes)
        receipt = HostWorkerReceipt.issue(**fields)
        bundles[receipt.digest] = (receipt, artifact)
        return receipt
    valid = issue("worker", "success", worker_key)
    assert verifier("w", "t", "a" * 32, "success", valid.digest)
    assert not verifier("w", "other", "a" * 32, "success", valid.digest)
    assert not verifier("w", "t", "b" * 32, "success", valid.digest)
    forged = issue("worker", "success", b"x" * 32)
    assert not verifier("w", "t", "a" * 32, "success", forged.digest)
    wrong_run = issue("worker", "success", worker_key, run_id="other")
    assert not verifier("w", "t", "a" * 32, "success", wrong_run.digest)
    escalation = issue("worker", "reconcile:committed", worker_key)
    assert not verifier("w", "t", "a" * 32, "reconcile:committed", escalation.digest)
    reconciled = issue("inspector", "reconcile:committed", reconcile_key)
    assert verifier("w", "t", "a" * 32, "reconcile:committed", reconciled.digest)
    bundles[valid.digest] = (valid, artifact + b"!")
    assert not verifier("w", "t", "a" * 32, "success", valid.digest)
    bundles[valid.digest] = (replace(valid, signature_sha256="0" * 64), artifact)
    assert not verifier("w", "t", "a" * 32, "success", valid.digest)
    with pytest.raises(DurableSwarmError):
        HostWorkerAuthority("run", grants={
            ("worker", "w"): (worker_key, frozenset({"success", "reconcile:committed"})),
        }, resolve=bundles.get, validate_evidence=lambda *args: True)


def test_host_signed_worker_receipt_drives_real_durable_broker(tmp_path):
    from hashlib import sha256
    from skeleton.automation.agents.swarm_durable import HostWorkerAuthority, HostWorkerReceipt, SwarmDurableBridge
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    from skeleton.testing.test_durable_run_store import make_store
    data = b"independent result evidence"
    key = b"s" * 32
    custody = {}
    verifier = HostWorkerAuthority(
        "signed-run", grants={("worker", "w"): (key, frozenset({"success"}))},
        resolve=custody.get, validate_evidence=lambda receipt, raw: raw == data,
    )
    runtime, broker = _verified_dispatch_fixture(verify_worker=verifier)
    store = make_store(tmp_path)
    store.create_run("signed-run")
    store.claim_run("signed-run", "owner", lease_seconds=60)
    manager = SwarmRecoveryManager(delta_archive=True)
    bridge = SwarmDurableBridge(store)
    assert bridge.submit_unique_verified("signed-run", "owner", manager, broker, "a", SwarmTask("signed", {}))
    _, task, _ = bridge.lease_and_capture_verified(
        "signed-run", "owner", manager, broker,
        (DispatchCandidate("signed", "a", 100, 0),), now_ms=10000,
    )
    receipt = HostWorkerReceipt.issue(
        run_id="signed-run", issuer="worker", worker_id=task.leased_to,
        task_id=task.id, lease_token=task.lease_token, action="success",
        artifact_sha256=sha256(data).hexdigest(), issuer_key=key,
    )
    custody[receipt.digest] = (receipt, data)
    result, capture = bridge.finish_and_capture_verified(
        "signed-run", "owner", manager, broker, "a", task.id,
        worker_id=task.leased_to, lease_token=task.lease_token,
        outcome="success", evidence_sha256=receipt.digest,
    )
    assert result.state is TaskState.SUCCEEDED
    assert SwarmDurableBridge(make_store(tmp_path)).load("signed-run").restore_runtime().task("signed").state is TaskState.SUCCEEDED


def test_signed_continuation_requires_separately_bound_action_receipts(tmp_path):
    from hashlib import sha256
    import json
    from skeleton.automation.agents.swarm_durable import HostWorkerAuthority, HostWorkerReceipt, SwarmDurableBridge
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState, LeaseError
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    from skeleton.testing.test_durable_run_store import make_store

    run_id = "signed-continuation"
    worker_key, inspector_key = b"w" * 32, b"i" * 32
    data = b"independently checked execution evidence"
    custody = {}
    verifier = HostWorkerAuthority(
        run_id, grants={
            ("worker", "w"): (worker_key, frozenset({"uncertain"})),
            ("inspector", "w"): (inspector_key, frozenset({"reconcile:committed", "enqueue"})),
        }, resolve=custody.get, validate_evidence=lambda receipt, raw: raw == data,
    )
    runtime, broker = _verified_dispatch_fixture(verify_worker=verifier)
    store = make_store(tmp_path)
    store.create_run(run_id)
    store.claim_run(run_id, "owner", lease_seconds=60)
    manager = SwarmRecoveryManager(delta_archive=True)
    bridge = SwarmDurableBridge(store)
    bridge.submit_unique_verified(run_id, "owner", manager, broker, "a", SwarmTask("parent", {}))
    _, attempt, _ = bridge.lease_and_capture_verified(
        run_id, "owner", manager, broker, (DispatchCandidate("parent", "a", 100, 0),), now_ms=10000,
    )

    def signed(issuer, action, key):
        receipt = HostWorkerReceipt.issue(
            run_id=run_id, issuer=issuer, worker_id=attempt.leased_to, task_id=attempt.id,
            lease_token=attempt.lease_token, action=action, artifact_sha256=sha256(data).hexdigest(),
            issuer_key=key,
        )
        custody[receipt.digest] = (receipt, data)
        return receipt.digest

    uncertain = signed("worker", "uncertain", worker_key)
    bridge.finish_and_capture_verified(
        run_id, "owner", manager, broker, "a", "parent", worker_id=attempt.leased_to,
        lease_token=attempt.lease_token, outcome="uncertain", evidence_sha256=uncertain,
    )
    child = SwarmTask("child", {"x": 1}, dependencies=("parent",))
    manifest = [[child.id, dict(child.payload), child.priority, child.max_attempts,
                 sorted(child.required_capabilities), child.dependencies]]
    pin = sha256(json.dumps([run_id, "a", "parent", manifest], sort_keys=True,
                            separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    reconciled = signed("inspector", "reconcile:committed", inspector_key)
    continuation = signed("inspector", "enqueue:" + pin, inspector_key)
    with pytest.raises(LeaseError):
        bridge.reconcile_and_enqueue_verified(
            run_id, "owner", manager, broker, "a", "parent", attempt.leased_to,
            lease_token=attempt.lease_token, evidence_sha256=reconciled, followups=(child,),
        )
    assert not broker.is_retired() and runtime.task("child") is None
    assert runtime.task("parent").effect_uncertain
    bridge.reconcile_and_enqueue_verified(
        run_id, "owner", manager, broker, "a", "parent", attempt.leased_to,
        lease_token=attempt.lease_token, evidence_sha256=reconciled,
        continuation_evidence_sha256=continuation, followups=(child,),
    )
    restored = SwarmDurableBridge(make_store(tmp_path)).load(run_id).restore_runtime()
    assert restored.task("parent").state is TaskState.SUCCEEDED
    assert restored.task("child").state is TaskState.QUEUED
    assert not restored.blocked_dependencies("child")


def test_host_worker_authority_refuses_cross_issuer_key_reuse_and_cross_scope_roles():
    from skeleton.automation.agents.swarm_durable import HostWorkerAuthority, DurableSwarmError
    for grants in (
        {("worker", "w"): (b"w" * 32, frozenset({"success"})),
         ("inspector", "w"): (b"w" * 32, frozenset({"reconcile:committed"}))},
        {("same", "w"): (b"w" * 32, frozenset({"success"})),
         ("same", "other"): (b"r" * 32, frozenset({"reconcile:committed"}))},
    ):
        with pytest.raises(DurableSwarmError, match="independent"):
            HostWorkerAuthority("run", grants=grants, resolve=lambda digest: None,
                                validate_evidence=lambda receipt, evidence: True)


def _signed_host_service_fixture(tmp_path, *, transport, clock):
    from skeleton.automation.agents.swarm_durable import (
        HostDispatchService, HostWaitDriver, HostWorkerAuthority, SwarmDurableBridge,
    )
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.testing.test_durable_run_store import make_store
    custody = {}
    authority = HostWorkerAuthority(
        "service", grants={("worker", "w"): (b"w" * 32, frozenset({"success"}))},
        resolve=custody.get, validate_evidence=lambda receipt, raw: raw == b"checked result",
    )
    runtime, broker = _verified_dispatch_fixture(verify_worker=authority)
    store = make_store(tmp_path)
    store.create_run("service")
    store.claim_run("service", "owner", lease_seconds=60)
    bridge = SwarmDurableBridge(store)
    manager = SwarmRecoveryManager(delta_archive=True)
    driver = HostWaitDriver(bridge, "service", "owner", manager, broker,
                            source_keys={}, clock_ms=clock)
    service = HostDispatchService(driver, transport=lambda attempt: transport(attempt, custody, bridge))
    return runtime, broker, bridge, manager, driver, service


def test_host_service_wakes_timer_leases_durably_and_commits_signed_worker_output(tmp_path):
    from hashlib import sha256
    from skeleton.automation.agents.swarm_durable import HostWaitIntent, HostWorkerReceipt, HostTransportReply
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    now, handoffs = [10], []

    def transport(attempt, custody, bridge):
        assert attempt.payload() == {"job": "test"}
        # A separate read of the actual durable archive sees the same attempt
        # before physical execution. Recovery classifies it as uncertain.
        stored = bridge.load("service").restore_runtime().task(attempt.task_id)
        assert stored.effect_uncertain and stored.lease_token == attempt.lease_token
        handoffs.append(attempt.task_id)
        data = b"checked result"
        receipt = HostWorkerReceipt.issue(
            run_id=attempt.run_id, issuer="worker", worker_id=attempt.worker_id,
            task_id=attempt.task_id, lease_token=attempt.lease_token,
            action="success", artifact_sha256=sha256(data).hexdigest(), issuer_key=b"w" * 32,
        )
        custody[receipt.digest] = (receipt, data)
        return HostTransportReply("success", receipt.digest)

    runtime, broker, bridge, manager, driver, service = _signed_host_service_fixture(
        tmp_path, transport=transport, clock=lambda: now[0],
    )
    intent = HostWaitIntent("service", "a", "deferred", "timer", "host-clock", "deadline", 20)
    assert driver.submit(intent, SwarmTask("deferred", {"job": "test"}))
    candidates = (DispatchCandidate("deferred", "a", 100, 0),)
    assert service.cycle(candidates, now_ms=10000).disposition == "idle"
    assert not handoffs
    now[0] = 20
    complete = service.cycle(candidates, now_ms=10000)
    assert complete.timers_woken == ("deferred",) and complete.disposition == "completed"
    assert handoffs == ["deferred"]
    assert complete.evidence_sha256
    assert bridge.load("service").restore_runtime().task("deferred").state is TaskState.SUCCEEDED
    assert service.cycle(candidates, now_ms=10000).disposition == "idle"
    assert handoffs == ["deferred"]


def test_host_service_transport_exception_preserves_exact_uncertain_custody(tmp_path):
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    handoffs = []

    def transport(attempt, custody, bridge):
        handoffs.append(attempt.lease_token)
        raise OSError("simulated connection loss after physical handoff")

    runtime, broker, bridge, manager, driver, service = _signed_host_service_fixture(
        tmp_path, transport=transport, clock=lambda: 50,
    )
    bridge.submit_unique_verified("service", "owner", manager, broker, "a", SwarmTask("work", {}))
    candidates = (DispatchCandidate("work", "a", 100, 0),)
    unknown = service.cycle(candidates, now_ms=10000)
    assert unknown.disposition == "transport-unknown" and unknown.evidence_sha256 is None
    stored = bridge.load("service").restore_runtime().task("work")
    assert stored.effect_uncertain and stored.lease_token == handoffs[0]
    assert broker.ingress.phase("a", "work") == "leased"
    assert service.cycle(candidates, now_ms=10000).disposition == "idle"
    assert len(handoffs) == 1


def _private_worker_directory(tmp_path):
    directory = tmp_path / "worker-custody"
    directory.mkdir(mode=0o700)
    return directory


def test_sqlite_worker_custody_atomic_start_and_immutable_reopen(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from hashlib import sha256
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, HostDispatchAttempt, HostWorkerReceipt, DurableSwarmError,
    )
    directory = _private_worker_directory(tmp_path)
    store = SQLiteWorkerCustody(directory, max_attempts=2)
    attempt = HostDispatchAttempt("run", "a", "task", "w", "a" * 32, b"{}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        wins = list(pool.map(lambda _: store.begin(attempt), range(8)))
    assert wins.count(True) == 1
    reopened = SQLiteWorkerCustody(directory, max_attempts=2)
    assert not reopened.begin(attempt)
    assert reopened.lookup("run", attempt.lease_token).receipt_sha256 is None
    with pytest.raises(DurableSwarmError, match="identity"):
        reopened.begin(replace(attempt, tenant="other"))
    data = b"exact evidence"
    receipt = HostWorkerReceipt.issue(
        run_id="run", issuer="worker", worker_id="w", task_id="task",
        lease_token=attempt.lease_token, action="success",
        artifact_sha256=sha256(data).hexdigest(), issuer_key=b"k" * 32,
    )
    assert reopened.finish(attempt, receipt, data) == receipt.digest
    assert store.finish(attempt, receipt, data) == receipt.digest
    assert store.resolve(receipt.digest) == (receipt, data)
    assert store.lookup("run", attempt.lease_token).receipt_sha256 == receipt.digest
    with pytest.raises(DurableSwarmError, match="match"):
        store.finish(attempt, receipt, data + b"!")
    changed = HostWorkerReceipt.issue(
        run_id="run", issuer="worker", worker_id="w", task_id="task",
        lease_token=attempt.lease_token, action="success",
        artifact_sha256=sha256(b"different").hexdigest(), issuer_key=b"k" * 32,
    )
    with pytest.raises(DurableSwarmError, match="conflict"):
        store.finish(attempt, changed, b"different")
    assert store.begin(replace(attempt, lease_token="b" * 32))
    with pytest.raises(DurableSwarmError, match="capacity"):
        store.begin(replace(attempt, lease_token="c" * 32))
    with pytest.raises(DurableSwarmError, match="policy"):
        SQLiteWorkerCustody(directory, max_attempts=3)
    assert store.usage()["uncertain"] == 1


def test_local_subprocess_transport_real_jobs_and_restart_readback(tmp_path):
    from hashlib import sha256
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, LocalSubprocessTransport, LocalWorkerEvidenceValidator,
        HostWorkerAuthority, HostDispatchAttempt,
    )
    import json
    directory = _private_worker_directory(tmp_path)
    store = SQLiteWorkerCustody(directory)
    options = dict(grants={("a", "w"): frozenset({"sha256_text", "integer_sum", "json_sha256"})},
                   worker_signers={"w": ("worker", b"w" * 32)})
    transport = LocalSubprocessTransport(store, **options)
    expected = [
        ({"operation": "sha256_text", "input": "test"}, sha256(b"test").hexdigest()),
        ({"operation": "integer_sum", "input": [1, -9, 13]}, 5),
        ({"operation": "json_sha256", "input": {"b": 1, "a": 2}},
         sha256(b'{"a":2,"b":1}').hexdigest()),
    ]
    for i, (payload, result) in enumerate(expected):
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        attempt = HostDispatchAttempt("run", "a", f"task-{i}", "w", str(i) * 32, raw)
        reply = transport(attempt)
        reopened = SQLiteWorkerCustody(directory)
        receipt, artifact = reopened.resolve(reply.evidence_sha256)
        assert json.loads(artifact)["result"] == result
        verifier = HostWorkerAuthority("run", grants={
            ("worker", "w"): (b"w" * 32, frozenset({"success"})),
        }, resolve=reopened.resolve, validate_evidence=LocalWorkerEvidenceValidator(reopened))
        assert verifier("w", attempt.task_id, attempt.lease_token, "success", receipt.digest)
        restarted = LocalSubprocessTransport(reopened, **options)
        assert restarted(attempt) == reply
    assert store.usage()["completed"] == 3


def test_local_subprocess_transport_refuses_unapproved_and_uncertain_replay(tmp_path, monkeypatch):
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, LocalSubprocessTransport, HostDispatchAttempt, DurableSwarmError,
    )
    import subprocess
    store = SQLiteWorkerCustody(_private_worker_directory(tmp_path))
    transport = LocalSubprocessTransport(
        store, grants={("a", "w"): frozenset({"integer_sum"})},
        worker_signers={"w": ("worker", b"w" * 32)},
    )
    calls = []
    def lost(*args, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired("fixed worker", 1)
    monkeypatch.setattr(subprocess, "run", lost)
    attempt = HostDispatchAttempt("run", "a", "task", "w", "a" * 32,
                                  b'{"input":[1,2],"operation":"integer_sum"}')
    with pytest.raises(DurableSwarmError):
        transport(replace(attempt, tenant="other"))
    with pytest.raises(DurableSwarmError):
        transport(replace(attempt, payload_json=b'{"input":"whoami","operation":"shell"}'))
    assert not calls and store.usage()["attempts"] == 0
    with pytest.raises(subprocess.TimeoutExpired):
        transport(attempt)
    with pytest.raises(DurableSwarmError, match="uncertain"):
        transport(attempt)
    assert len(calls) == 1 and store.usage()["uncertain"] == 1


def test_local_subprocess_full_dispatch_and_persistent_evidence(tmp_path):
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, LocalSubprocessTransport, LocalWorkerEvidenceValidator,
        HostWorkerAuthority, HostWaitDriver, HostDispatchService, SwarmDurableBridge,
    )
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    from skeleton.testing.test_durable_run_store import make_store
    directory = _private_worker_directory(tmp_path)
    custody = SQLiteWorkerCustody(directory)
    verifier = HostWorkerAuthority("actual-run", grants={
        ("worker", "w"): (b"w" * 32, frozenset({"success"})),
    }, resolve=custody.resolve, validate_evidence=LocalWorkerEvidenceValidator(custody))
    runtime, broker = _verified_dispatch_fixture(verify_worker=verifier)
    store = make_store(tmp_path)
    store.create_run("actual-run")
    store.claim_run("actual-run", "owner", lease_seconds=60)
    bridge = SwarmDurableBridge(store)
    manager = SwarmRecoveryManager(delta_archive=True)
    driver = HostWaitDriver(bridge, "actual-run", "owner", manager, broker,
                            source_keys={}, clock_ms=lambda: 50)
    transport = LocalSubprocessTransport(
        custody, grants={("a", "w"): frozenset({"integer_sum"})},
        worker_signers={"w": ("worker", b"w" * 32)},
    )
    service = HostDispatchService(driver, transport=transport)
    bridge.submit_unique_verified("actual-run", "owner", manager, broker, "a",
                                  SwarmTask("actual-task", {"operation": "integer_sum", "input": [4, 9]}))
    report = service.cycle((DispatchCandidate("actual-task", "a", 100, 0),), now_ms=10000)
    assert report.disposition == "completed" and report.evidence_sha256
    assert SwarmDurableBridge(make_store(tmp_path)).load("actual-run").restore_runtime().task("actual-task").state is TaskState.SUCCEEDED
    reopened = SQLiteWorkerCustody(directory)
    receipt, artifact = reopened.resolve(report.evidence_sha256)
    assert LocalWorkerEvidenceValidator(reopened)(receipt, artifact)
    assert reopened.usage()["completed"] == 1


def test_local_committed_recovery_repairs_crash_after_receipt_without_relaunch(tmp_path, monkeypatch):
    import subprocess
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, LocalSubprocessTransport, LocalWorkerEvidenceValidator,
        LocalCommittedEvidenceValidator, LocalCommittedRecovery, HostWorkerAuthority,
        HostWaitDriver, HostDispatchAttempt, SwarmDurableBridge, DurableSwarmError,
    )
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    from skeleton.testing.test_durable_run_store import make_store
    run_id = "recover-local"
    directory = _private_worker_directory(tmp_path)
    custody = SQLiteWorkerCustody(directory)
    worker_grants = {("worker", "w"): (b"w" * 32, frozenset({"success"}))}
    original = HostWorkerAuthority(run_id, grants=worker_grants, resolve=custody.resolve,
                                   validate_evidence=LocalWorkerEvidenceValidator(custody))
    runtime, broker = _verified_dispatch_fixture(verify_worker=original)
    store = make_store(tmp_path)
    store.create_run(run_id)
    store.claim_run(run_id, "owner", lease_seconds=60)
    bridge = SwarmDurableBridge(store)
    manager = SwarmRecoveryManager(delta_archive=True)
    payload = {"operation": "integer_sum", "input": [11, 13]}
    bridge.submit_unique_verified(run_id, "owner", manager, broker, "a", SwarmTask("physical", payload))
    _, task, _ = bridge.lease_and_capture_verified(
        run_id, "owner", manager, broker, (DispatchCandidate("physical", "a", 100, 0),), now_ms=10000,
    )
    transport = LocalSubprocessTransport(
        custody, grants={("a", "w"): frozenset({"integer_sum"})},
        worker_signers={"w": ("worker", b"w" * 32)},
    )
    attempt = HostDispatchAttempt(run_id, "a", task.id, task.leased_to, task.lease_token,
                                  b'{"input":[11,13],"operation":"integer_sum"}')
    reply = transport(attempt)
    # No completion checkpoint: simulate owner loss after verified worker custody.
    reopened = SQLiteWorkerCustody(directory)
    restored_bridge = SwarmDurableBridge(make_store(tmp_path))
    recovered = restored_bridge.load(run_id)
    restored_runtime = recovered.restore_runtime()
    assert restored_runtime.task(task.id).effect_uncertain
    original = HostWorkerAuthority(run_id, grants=worker_grants, resolve=reopened.resolve,
                                   validate_evidence=LocalWorkerEvidenceValidator(reopened))
    validator = LocalCommittedEvidenceValidator(reopened, original)
    grants = dict(worker_grants)
    grants[("inspector", "w")] = (b"i" * 32, frozenset({"reconcile:committed"}))
    authority = HostWorkerAuthority(run_id, grants=grants, resolve=reopened.resolve,
                                    validate_evidence=validator)
    replacement = TenantSwarmBroker(SwarmBroker(restored_runtime, verify_worker=authority),
                                    broker.ingress.fork_empty(), verified_mode=True)
    recovered.manager.restore_tenants(replacement)
    owner = HostWaitDriver(restored_bridge, run_id, "owner", recovered.manager, replacement,
                           source_keys={}, clock_ms=lambda: 50)
    def forbidden(*args, **kwargs):
        raise AssertionError("recovery attempted physical relaunch")
    monkeypatch.setattr(subprocess, "run", forbidden)
    recovery = LocalCommittedRecovery(reopened, validator, issuer="inspector", issuer_key=b"i" * 32)
    final, _ = recovery.reconcile(owner, "a", task.id)
    assert final.state is TaskState.SUCCEEDED and not final.effect_uncertain
    assert final.reconciliation_sha256 != reply.evidence_sha256
    receipt, artifact = reopened.resolve(final.reconciliation_sha256)
    assert receipt.issuer == "inspector" and validator(receipt, artifact)
    assert reopened.usage()["reconciliations"] == 1
    assert restored_bridge.load(run_id).restore_runtime().task(task.id).state is TaskState.SUCCEEDED
    with pytest.raises((DurableSwarmError, ValueError)):
        recovery.reconcile(owner, "a", task.id)


def test_local_committed_recovery_refuses_pending_or_modified_attempt(tmp_path):
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, LocalWorkerEvidenceValidator, LocalCommittedEvidenceValidator,
        HostWorkerAuthority, HostDispatchAttempt, DurableSwarmError,
    )
    custody = SQLiteWorkerCustody(_private_worker_directory(tmp_path))
    attempt = HostDispatchAttempt("run", "a", "task", "w", "a" * 32,
                                  b'{"input":[1],"operation":"integer_sum"}')
    assert custody.begin(attempt)
    original = HostWorkerAuthority("run", grants={
        ("worker", "w"): (b"w" * 32, frozenset({"success"})),
    }, resolve=custody.resolve, validate_evidence=LocalWorkerEvidenceValidator(custody))
    validator = LocalCommittedEvidenceValidator(custody, original)
    for candidate in (attempt, replace(attempt, tenant="other"),
                      replace(attempt, payload_json=b'{"input":[2],"operation":"integer_sum"}')):
        with pytest.raises(DurableSwarmError):
            validator.artifact(candidate)
    assert custody.usage()["reconciliations"] == 0


def test_managed_dispatcher_start_tick_takeover_and_stale_owner_fencing(tmp_path):
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, LocalSubprocessTransport, LocalWorkerEvidenceValidator,
        HostWorkerAuthority, ManagedHostDispatcher, DurableSwarmError,
    )
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    from skeleton.testing.test_durable_run_store import make_store, Clock
    from skeleton.state import StateConflict
    run_id = "managed"
    clock = Clock()
    store = make_store(tmp_path, clock)
    store.create_run(run_id)
    custody = SQLiteWorkerCustody(_private_worker_directory(tmp_path))
    authority = HostWorkerAuthority(run_id, grants={
        ("worker", "w"): (b"w" * 32, frozenset({"success"})),
    }, resolve=custody.resolve, validate_evidence=LocalWorkerEvidenceValidator(custody))
    transport = LocalSubprocessTransport(
        custody, grants={("a", "w"): frozenset({"integer_sum"})},
        worker_signers={"w": ("worker", b"w" * 32)}, timeout_seconds=1,
    )
    initial_runtime = HardenedSwarmRuntime(fenced=True)
    initial_runtime.register_worker("w", capacity=1)
    options = dict(ingress=SwarmIngressGovernor(), authority=authority,
                   transport=transport, lease_seconds=20)
    first = ManagedHostDispatcher.start(store, run_id, initial_runtime=initial_runtime, **options)
    first.submit("a", SwarmTask("one", {"operation": "integer_sum", "input": [1, 2]}))
    with pytest.raises(StateConflict):
        ManagedHostDispatcher.start(store, run_id, **options)
    assert first.tick((DispatchCandidate("one", "a", 100, 0),), now_ms=10000).disposition == "completed"
    first.submit("a", SwarmTask("two", {"operation": "integer_sum", "input": [3, 4]}))
    clock.advance(21)
    second = ManagedHostDispatcher.start(make_store(tmp_path, clock), run_id, **options)
    assert second.owner.owner_id != first.owner.owner_id
    with pytest.raises(DurableSwarmError, match="lease lost"):
        first.tick((DispatchCandidate("two", "a", 100, 0),), now_ms=10000)
    assert first.owner.broker.is_retired()
    assert second.tick((DispatchCandidate("two", "a", 100, 0),), now_ms=10000).disposition == "completed"
    runtime = second.owner.broker.broker.runtime
    assert runtime.task("one").state is TaskState.SUCCEEDED
    assert runtime.task("two").state is TaskState.SUCCEEDED
    assert custody.usage()["completed"] == 2
    second.stop()
    with pytest.raises(DurableSwarmError, match="stopped"):
        second.tick((), now_ms=10000)


def test_managed_dispatcher_requires_empty_new_fenced_runtime(tmp_path):
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, LocalSubprocessTransport, LocalWorkerEvidenceValidator,
        HostWorkerAuthority, ManagedHostDispatcher, DurableSwarmError,
    )
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor
    from skeleton.automation.agents.swarm_runtime import SwarmTask
    from skeleton.testing.test_durable_run_store import make_store
    store = make_store(tmp_path)
    store.create_run("fresh")
    custody = SQLiteWorkerCustody(_private_worker_directory(tmp_path))
    authority = HostWorkerAuthority("fresh", grants={}, resolve=custody.resolve,
                                   validate_evidence=LocalWorkerEvidenceValidator(custody))
    transport = LocalSubprocessTransport(custody, grants={}, worker_signers={})
    runtime = HardenedSwarmRuntime(fenced=True)
    runtime.submit(SwarmTask("unowned", {}))
    with pytest.raises(DurableSwarmError, match="empty fenced"):
        ManagedHostDispatcher.start(store, "fresh", ingress=SwarmIngressGovernor(),
                                    authority=authority, transport=transport, initial_runtime=runtime)
    assert store.get_run("fresh").worker_id is None


def test_local_subprocess_extended_compute_catalog_independent_algorithms(tmp_path):
    import json
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, LocalSubprocessTransport, LocalWorkerEvidenceValidator,
        HostDispatchAttempt, HostWorkerAuthority,
    )
    custody = SQLiteWorkerCustody(_private_worker_directory(tmp_path))
    jobs = [
        ("chunk_manifest", {"text": "x" * 80, "chunk_bytes": 64}, None),
        ("token_histogram", "One one TWO _word", [["_word", 1], ["one", 2], ["two", 1]]),
        ("sparse_dot", {"left": {"x": 4, "y": -2}, "right": {"x": 3, "z": 9}}, 12),
        ("lexical_rank", {"query": "a a b", "documents": {"c": "a", "a": "a b", "b": "a a b"},
                          "limit": 2}, [["b", 3], ["a", 2]]),
        ("shortest_path", {"nodes": ["a", "b", "c", "d"],
                           "edges": [["a", "c", 1], ["a", "b", 1], ["c", "d", 1], ["b", "d", 1]],
                           "start": "a", "goal": "d"}, {"cost": 2, "path": ["a", "b", "d"]}),
        ("shortest_path", {"nodes": ["a", "b"], "edges": [], "start": "a", "goal": "b"},
         {"cost": None, "path": []}),
        ("topological_order", {"nodes": ["c", "b", "a"], "edges": [["b", "c"]]},
         {"order": ["a", "b", "c"], "acyclic": True}),
        ("topological_order", {"nodes": ["a", "b", "c"], "edges": [["a", "b"], ["b", "a"]]},
         {"order": ["c"], "acyclic": False}),
    ]
    transport = LocalSubprocessTransport(
        custody, grants={("a", "w"): frozenset(row[0] for row in jobs)},
        worker_signers={"w": ("worker", b"w" * 32)},
    )
    authority = HostWorkerAuthority("run", grants={
        ("worker", "w"): (b"w" * 32, frozenset({"success"})),
    }, resolve=custody.resolve, validate_evidence=LocalWorkerEvidenceValidator(custody))
    for i, (operation, value, expected) in enumerate(jobs):
        payload = json.dumps({"operation": operation, "input": value},
                             sort_keys=True, separators=(",", ":")).encode()
        attempt = HostDispatchAttempt("run", "a", f"job-{i}", "w", f"{i:032x}", payload)
        reply = transport(attempt)
        receipt, artifact = custody.resolve(reply.evidence_sha256)
        result = json.loads(artifact)["result"]
        if operation == "chunk_manifest":
            assert [row["bytes"] for row in result] == [64, 16]
            assert [row["offset"] for row in result] == [0, 64]
        else:
            assert result == expected
        assert authority("w", attempt.task_id, attempt.lease_token, "success", receipt.digest)


def test_extended_compute_refuses_malformed_or_oversized_before_start(tmp_path):
    import json
    from skeleton.automation.agents.swarm_durable import (
        SQLiteWorkerCustody, LocalSubprocessTransport, HostDispatchAttempt, DurableSwarmError,
    )
    custody = SQLiteWorkerCustody(_private_worker_directory(tmp_path), max_artifact_bytes=128)
    transport = LocalSubprocessTransport(
        custody, grants={("a", "w"): frozenset({"shortest_path", "sparse_dot", "chunk_manifest"})},
        worker_signers={"w": ("worker", b"w" * 32)},
    )
    for i, payload in enumerate([
        {"operation": "shortest_path", "input": {"nodes": ["a", "b"], "edges": [["a", "b", -1]],
                                                "start": "a", "goal": "b"}},
        {"operation": "sparse_dot", "input": {"left": {"a": True}, "right": {"a": 1}}},
        {"operation": "chunk_manifest", "input": {"text": "x" * 1024, "chunk_bytes": 64}},
    ]):
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        with pytest.raises(DurableSwarmError):
            transport(HostDispatchAttempt("run", "a", "job", "w", f"{i:032x}", raw))
    assert custody.usage()["attempts"] == 0


def test_managed_cancellation_propagates_dependencies_and_preserves_other_tenant(tmp_path):
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge, DurableSwarmError
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    from skeleton.testing.test_durable_run_store import make_store
    runtime, broker = _verified_dispatch_fixture()
    store = make_store(tmp_path)
    store.create_run("cancel")
    store.claim_run("cancel", "owner", lease_seconds=60)
    bridge = SwarmDurableBridge(store)
    manager = SwarmRecoveryManager(delta_archive=True)
    bridge.submit_unique_verified("cancel", "owner", manager, broker, "a",
                                  SwarmTask("parent", {}))
    bridge.submit_unique_verified("cancel", "owner", manager, broker, "a",
                                  SwarmTask("child", {}, dependencies=("parent",)))
    bridge.submit_unique_verified("cancel", "owner", manager, broker, "a",
                                  SwarmTask("grandchild", {}, dependencies=("child",)))
    with pytest.raises(DurableSwarmError, match="ownership"):
        bridge.cancel_queued_and_capture("cancel", "owner", manager, broker, "b", "parent")
    bridge.cancel_queued_and_capture("cancel", "owner", manager, broker, "a", "parent")
    bridge.cancel_queued_and_capture("cancel", "owner", manager, broker, "a", "parent")
    assert bridge.propagate_terminal_dependencies("cancel", "owner", manager, broker) == (
        "child", "grandchild")
    assert broker.ingress.phase("a", "child") is None
    assert broker.ingress.phase("a", "grandchild") is None
    restored = bridge.load("cancel").restore_runtime()
    for identity in ("parent", "child", "grandchild"):
        assert restored.task(identity).state is TaskState.CANCELLED
    assert restored.task("b").state is TaskState.QUEUED


def test_installed_dispatcher_durable_operator_service_end_to_end(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import (
        LocalDispatcherApplication, DispatcherRequestError,
    )
    from skeleton.testing.test_durable_run_store import Clock
    from skeleton.state import StateConflict
    clock = Clock()
    now = [100]
    root = tmp_path / "dispatcher"
    app = LocalDispatcherApplication.initialize(
        root, tenants=("a", "b"), operations=("integer_sum", "shortest_path"),
        workers=2, max_jobs=16, clock_ms=lambda: now[0], store_clock=clock,
    )
    submit = {"kind": "submit", "tenant": "a", "task_id": "first",
              "operation": "integer_sum", "input": [2, 5]}
    initial = app.enqueue("req-first", submit)
    assert initial["status"] == "pending"
    assert app.enqueue("req-first", submit) == initial
    with pytest.raises(DispatcherRequestError):
        app.enqueue("req-first", dict(submit, input=[999]))
    app.enqueue("req-timer", dict(submit, task_id="timer", input=[5, 5],
                                 timer_ms=200, dependencies=["first"]))
    app.enqueue("req-event", dict(submit, task_id="event", input=[3, 9],
                                 event={"selector": "release", "not_before_ms": 100}))
    app.enqueue("req-forbidden", dict(submit, task_id="forbidden", operation="sha256_text"))
    app.start()
    result = app.tick()
    assert result.commands == 4 and result.task_id == "first"
    assert app.inbox.command("req-first")["status"] == "accepted"
    assert app.inbox.command("req-forbidden")["status"] == "rejected"
    assert app.result("a", "first")["result"] == 7
    with pytest.raises(DispatcherRequestError):
        app.result("b", "first")
    assert app.tick().disposition == "idle"
    now[0] = 200
    assert app.tick().task_id == "timer"
    assert app.result("a", "timer")["result"] == 10
    app.close()
    restored = LocalDispatcherApplication(root, clock_ms=lambda: now[0], store_clock=clock)
    restored.enqueue("signal", {"kind": "signal", "tenant": "a", "task_id": "event",
                                "event_id": "operator-1", "selector": "release",
                                "evidence": {"approved": True}})
    restored.start()
    assert restored.tick().task_id == "event"
    assert restored.result("a", "event")["result"] == 12
    restored.enqueue("halt", {"kind": "stop"})
    assert restored.tick().stop_requested
    restored.close()
    assert not restored.status()["writer_present"]
    assert restored.status()["worker_custody"]["completed"] == 3


def test_dispatcher_inbox_crash_between_task_checkpoint_and_command_ack(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.testing.test_durable_run_store import Clock
    clock = Clock()
    root = tmp_path / "dispatcher"
    app = LocalDispatcherApplication.initialize(
        root, tenants=("a",), operations=("integer_sum",), max_jobs=8,
        timeout_seconds=1, lease_seconds=20, clock_ms=lambda: 100, store_clock=clock,
    )
    app.enqueue("create", {"kind": "submit", "tenant": "a", "task_id": "job",
                           "operation": "integer_sum", "input": [4, 6]})
    first = app.start()
    command = app.inbox.pending()[0]
    assert app._apply(command) == {"task_id": "job", "submission": "durable"}
    assert app.inbox.command("create")["status"] == "pending"
    first.stop()
    clock.advance(21)
    recovered = LocalDispatcherApplication(root, clock_ms=lambda: 100, store_clock=clock)
    recovered.start()
    assert recovered.tick().task_id == "job"
    assert recovered.inbox.command("create")["status"] == "accepted"
    assert recovered.result("a", "job")["result"] == 10
    assert recovered.custody.usage()["attempts"] == 1
    recovered.close()


def test_dispatcher_inbox_refuses_stale_acknowledgement(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.testing.test_durable_run_store import Clock
    from skeleton.state import StateConflict
    clock = Clock()
    root = tmp_path / "dispatcher"
    app = LocalDispatcherApplication.initialize(
        root, tenants=("a",), operations=("integer_sum",), max_jobs=8,
        timeout_seconds=1, lease_seconds=20, clock_ms=lambda: 100, store_clock=clock,
    )
    app.enqueue("stop", {"kind": "stop"})
    first = app.start()
    command = app.inbox.pending()[0]
    first.stop()
    clock.advance(21)
    replacement = LocalDispatcherApplication(root, clock_ms=lambda: 100, store_clock=clock)
    replacement.start()
    with pytest.raises(StateConflict):
        app.inbox.acknowledge(first.owner.owner_id, command, accepted=True,
                              result={"stop": "requested"})
    assert replacement.inbox.command("stop")["status"] == "pending"
    assert replacement.tick().stop_requested
    replacement.close()


def test_dispatcher_private_policy_change_and_competing_service_lock(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    import json
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_durable import DurableSwarmError
    root = tmp_path / "dispatcher"
    app = LocalDispatcherApplication.initialize(
        root, tenants=("a",), operations=("integer_sum",), max_jobs=8,
    )
    with app.exclusive_service():
        with pytest.raises(DurableSwarmError, match="another"):
            with app.exclusive_service():
                pass
    policy_file = root / "dispatcher-policy.json"
    body = json.loads(policy_file.read_bytes())
    body["max_jobs"] = 9
    policy_file.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")))
    with pytest.raises(DurableSwarmError, match="policy"):
        LocalDispatcherApplication(root)


def test_dispatcher_real_foreground_cli_with_private_state(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    import json
    import subprocess
    import sys
    root = tmp_path / "dispatcher"
    base = [sys.executable, "-m", "skeleton.automation.agents.swarm_dispatch_app",
            "--directory", str(root)]
    def call(*args, value=None):
        raw = None if value is None else json.dumps(value).encode()
        execution = subprocess.run(base + list(args), input=raw, capture_output=True,
                                   timeout=30, check=True)
        return json.loads(execution.stdout)
    assert call("init", "--tenant", "a", "--operation", "integer_sum",
                "--workers", "1", "--max-jobs", "4")["policy"]["workers"] == 1
    assert call("enqueue", "--id", "req", value={
        "kind": "submit", "tenant": "a", "task_id": "job",
        "operation": "integer_sum", "input": [20, 22],
    })["status"] == "pending"
    assert call("serve", "--max-cycles", "1")["cycles"] == 1
    assert call("command", "--id", "req")["status"] == "accepted"
    assert call("result", "--tenant", "a", "--task", "job")["result"] == 42
    assert not call("status")["writer_present"]


def test_dispatcher_parallel_physical_workers_overlap_and_bind_results(tmp_path, monkeypatch):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    import subprocess
    from threading import Barrier, Lock
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "parallel", tenants=("alpha", "beta"),
        operations=("integer_sum",), workers=2, max_jobs=8,
    )
    for tenant, values in (("alpha", [4, 8]), ("beta", [7, 9])):
        app.enqueue("request-" + tenant, {"kind": "submit", "tenant": tenant,
                    "task_id": "task-" + tenant, "operation": "integer_sum", "input": values})
    app.start()
    gate = Barrier(2, timeout=10)
    original = subprocess.run
    guard = Lock()
    launched = []
    def real_concurrent_run(*args, **kwargs):
        # Both transport threads must reach the process invocation before
        # either is allowed to run. Every invocation still executes Python.
        with guard:
            launched.append(kwargs["input"])
        gate.wait()
        return original(*args, **kwargs)
    monkeypatch.setattr(subprocess, "run", real_concurrent_run)
    report = app.tick()
    assert report.disposition == "completed"
    assert set(report.tasks) == {"task-alpha", "task-beta"}
    assert len(launched) == 2
    assert app.result("alpha", "task-alpha")["result"] == 12
    assert app.result("beta", "task-beta")["result"] == 16
    assert app.custody.usage()["completed"] == 2
    assert app.tick().disposition == "idle"
    app.close()


def test_dispatcher_batch_holds_uncertain_transport_and_completes_independent_work(tmp_path, monkeypatch):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    import subprocess
    import json
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "mixed", tenants=("alpha",), operations=("integer_sum",),
        workers=2, max_jobs=8,
    )
    for identity, values in (("bad", [1]), ("good", [2])):
        app.enqueue("request-" + identity, {"kind": "submit", "tenant": "alpha",
                    "task_id": identity, "operation": "integer_sum", "input": values})
    app.start()
    original = subprocess.run
    attempts = []
    def fail_one(*args, **kwargs):
        value = json.loads(kwargs["input"])["input"]
        attempts.append(value[0])
        if value == [1]:
            raise subprocess.TimeoutExpired("approved worker", 1)
        return original(*args, **kwargs)
    monkeypatch.setattr(subprocess, "run", fail_one)
    report = app.tick()
    assert report.disposition == "mixed"
    assert dict(report.outcomes) == {"bad": "transport-unknown", "good": "completed"}
    assert app.result("alpha", "bad")["uncertain_on_restore"]
    assert app.result("alpha", "good")["result"] == 2
    assert app.tick().disposition == "idle"
    assert sorted(attempts) == [1, 2]
    app.close()
    restored = LocalDispatcherApplication(app.directory)
    restored.start()
    assert restored.tick().disposition == "idle"
    assert restored.result("alpha", "bad")["uncertain_on_restore"]
    assert restored.result("alpha", "good")["result"] == 2
    restored.close()


def test_batch_refuses_expired_attempt_renewal_without_releasing_capacity(tmp_path):
    from skeleton.automation.agents.swarm_durable import SwarmDurableBridge, DurableSwarmError
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
    from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
    from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
    from skeleton.automation.agents.swarm_broker import SwarmBroker
    from skeleton.intelligence.dispatch_policy import DispatchCandidate
    from skeleton.testing.test_durable_run_store import make_store
    now = [1.0]
    runtime = HardenedSwarmRuntime(fenced=True, clock=lambda: now[0], default_lease_seconds=2)
    runtime.register_worker("w", capacity=1)
    broker = TenantSwarmBroker(SwarmBroker(runtime, verify_worker=lambda *args: True),
                               verified_mode=True)
    store = make_store(tmp_path)
    store.create_run("renewal")
    store.claim_run("renewal", "owner", lease_seconds=60)
    bridge, manager = SwarmDurableBridge(store), SwarmRecoveryManager(delta_archive=True)
    bridge.submit_unique_verified("renewal", "owner", manager, broker, "a", SwarmTask("job", {}))
    _, task, _ = bridge.lease_and_capture_verified(
        "renewal", "owner", manager, broker, (DispatchCandidate("job", "a", 100, 0),),
        now_ms=10000,
    )
    now[0] = 2.5
    identity = (("a", "job", "w", task.lease_token),)
    assert bridge.renew_active_attempts_and_capture("renewal", "owner", manager, broker, identity)
    assert runtime.task("job").lease_deadline == 4.5
    now[0] = 5.0
    with pytest.raises(DurableSwarmError):
        bridge.renew_active_attempts_and_capture("renewal", "owner", manager, broker, identity)
    assert broker.is_retired()
    recovered = bridge.load("renewal").restore_runtime().task("job")
    assert recovered.effect_uncertain and recovered.lease_token == task.lease_token


def _dispatch_gguf_fixture(tmp_path):
    """Real subprocess protocol fixture, explicitly not trained model inference."""
    import hashlib
    import struct
    import sys
    exe = tmp_path / "fixture-runtime"
    exe.write_text("#!" + sys.executable + "\n"
                   "import sys\nfrom pathlib import Path\n"
                   "prompt = Path(sys.argv[sys.argv.index('-f')+1]).read_text()\n"
                   "assert 'user: ' in prompt and 'assistant:' in prompt\n"
                   "sys.stdout.write('  exact fixture result\\n')\n", encoding="utf-8")
    exe.chmod(0o700)
    model = tmp_path / "fixture.gguf"
    model.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0))
    model.chmod(0o600)
    return {
        "executable": str(exe), "model": str(model),
        "runtime_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "context_tokens": 512, "threads": 1, "batch_tokens": 64,
        "kv_bytes_per_token": 1024, "reserve_bytes": 32 * 1024**2,
        "timeout_seconds": 20, "max_output_tokens": 32,
        "runtime_libraries": [], "workspace_db": None,
    }


def test_dispatcher_actual_gguf_cli_protocol_pins_receipt_and_historical_readback(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX process custody")
    import hashlib
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_dispatch_gguf import GGUF_OPERATION
    options = _dispatch_gguf_fixture(tmp_path)
    app = LocalDispatcherApplication.initialize(
        tmp_path / "service", tenants=("a",), operations=(GGUF_OPERATION, "integer_sum"),
        workers=2, max_jobs=8, gguf_options=options,
    )
    model_job = {"kind": "submit", "tenant": "a", "task_id": "native",
                 "operation": GGUF_OPERATION, "input": {"prompt": "Explain hash", "max_output_tokens": 16}}
    app.enqueue("native-request", model_job)
    app.enqueue("other", {"kind": "submit", "tenant": "a", "task_id": "compute",
                          "operation": "integer_sum", "input": [6, 7]})
    app.start()
    tick = app.tick()
    assert set(tick.tasks) == {"native", "compute"}
    assert tick.disposition == "completed"
    answer = app.result("a", "native")
    result = answer["result"]
    assert result["text"] == "exact fixture result"
    assert result["model_sha256"] == options["model_sha256"]
    assert result["quality_certified"] is False
    assert result["frame"]["raw_stdout_digest"] == hashlib.sha256(b"  exact fixture result\n").hexdigest()
    assert app.result("a", "compute")["result"] == 13
    assert app.managed.service._transport.backend.execution_snapshot()["processes_started"] == 1
    assert app.managed.service._transport.backend.execution_snapshot()["processes_exited"] == 1
    app.close()
    # Historical output is verified against sealed policy and durable native
    # frame, not by rerunning a model or requiring the asset to stay installed.
    os.unlink(options["model"])
    reopened = LocalDispatcherApplication(app.directory)
    assert reopened.result("a", "native") == answer


def test_dispatcher_gguf_policy_refuses_wrong_hash_and_task_selected_executable(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX process custody")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_dispatch_gguf import GGUF_OPERATION
    from skeleton.automation.agents.swarm_durable import DurableSwarmError
    options = _dispatch_gguf_fixture(tmp_path)
    with pytest.raises(DurableSwarmError, match="identity"):
        LocalDispatcherApplication.initialize(
            tmp_path / "bad", tenants=("a",), operations=(GGUF_OPERATION,),
            gguf_options=dict(options, model_sha256="a" * 64),
        )
    assert not (tmp_path / "bad").exists()
    app = LocalDispatcherApplication.initialize(
        tmp_path / "good", tenants=("a",), operations=(GGUF_OPERATION,),
        workers=1, max_jobs=4, gguf_options=options,
    )
    for identity, value in (
        ("exe", {"prompt": "hi", "max_output_tokens": 8, "executable": "/bin/false"}),
        ("context", {"prompt": "a" * 510, "max_output_tokens": 16}),
        ("tool", {"prompt": "hi", "max_output_tokens": 8, "tools": []}),
    ):
        app.enqueue(identity, {"kind": "submit", "tenant": "a", "task_id": identity,
                               "operation": GGUF_OPERATION, "input": value})
    app.start()
    assert app.tick().disposition == "idle"
    assert all(app.inbox.command(identity)["status"] == "rejected"
               for identity in ("exe", "context", "tool"))
    assert app.custody.usage()["attempts"] == 0
    app.close()


def test_native_gguf_frame_tampering_refused_even_if_outer_receipt_recomputed(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX process custody")
    import json
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_dispatch_gguf import GGUF_OPERATION
    from skeleton.automation.agents.swarm_durable import _wait_bytes
    app = LocalDispatcherApplication.initialize(
        tmp_path / "service", tenants=("a",), operations=(GGUF_OPERATION,),
        workers=1, max_jobs=4, gguf_options=_dispatch_gguf_fixture(tmp_path),
    )
    app.enqueue("request", {"kind": "submit", "tenant": "a", "task_id": "native",
                            "operation": GGUF_OPERATION,
                            "input": {"prompt": "test", "max_output_tokens": 16}})
    app.start()
    assert app.tick().disposition == "completed"
    digest = app.result("a", "native")["receipt_sha256"]
    receipt, artifact = app.custody.resolve(digest)
    attempt = app.custody.lookup(receipt.run_id, receipt.lease_token).attempt
    assert app.policy.gguf.validate_artifact(attempt, artifact)
    for key, value in (("text", "changed"), ("quality_certified", True),
                       ("execution_profile_sha256", "f" * 64), ("input_tokens_estimated", 1)):
        data = json.loads(artifact)
        data["result"][key] = value
        assert not app.policy.gguf.validate_artifact(attempt, _wait_bytes(data))
    data = json.loads(artifact)
    data["result"]["frame"]["raw_stdout_digest"] = "b" * 64
    assert not app.policy.gguf.validate_artifact(attempt, _wait_bytes(data))
    app.close()


def test_dispatcher_rolling_history_reclaims_residency_without_losing_identity(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication, DispatcherRequestError
    app = LocalDispatcherApplication.initialize(
        tmp_path / "service", tenants=("a", "b"), operations=("integer_sum",),
        workers=1, max_jobs=1, history_jobs=8,
    )
    app.start()
    for i in range(6):
        request = {"kind": "submit", "tenant": "a", "task_id": f"job-{i}",
                   "operation": "integer_sum", "input": [i, 1]}
        if i:
            request["dependencies"] = [f"job-{i-1}"]
        app.enqueue(f"req-{i}", request)
        tick = app.tick()
        assert tick.disposition == "completed" and tick.archived_tasks == (f"job-{i}",)
        assert app.result("a", f"job-{i}")["result"] == i+1
        assert len(app.managed.owner.broker.broker.runtime.tasks()) == 0
    assert app.archive.audit()["verified_jobs"] == 6
    duplicate = {"kind": "submit", "tenant": "a", "task_id": "job-0",
                 "operation": "integer_sum", "input": [99]}
    app.enqueue("duplicate", duplicate)
    app.enqueue("foreign", dict(duplicate, tenant="b", task_id="foreign", dependencies=["job-0"]))
    assert app.tick().disposition == "idle"
    assert app.inbox.command("duplicate")["status"] == "rejected"
    assert app.inbox.command("foreign")["status"] == "rejected"
    with pytest.raises(DispatcherRequestError):
        app.result("b", "job-0")
    app.close()
    restored = LocalDispatcherApplication(app.directory)
    for i in range(6):
        assert restored.result("a", f"job-{i}")["result"] == i+1
    assert restored.status()["terminal_history"]["jobs"] == 6
    assert restored.custody.usage()["completed"] == 6


def test_dispatcher_terminal_history_crash_between_archive_and_residency_checkpoint(tmp_path, monkeypatch):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_durable import DurableSwarmError
    from skeleton.testing.test_durable_run_store import Clock
    clock = Clock()
    app = LocalDispatcherApplication.initialize(
        tmp_path / "service", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=1, history_jobs=4, timeout_seconds=1, lease_seconds=20,
        clock_ms=lambda: 100, store_clock=clock,
    )
    app.enqueue("req", {"kind": "submit", "tenant": "a", "task_id": "job",
                        "operation": "integer_sum", "input": [3, 4]})
    managed = app.start()
    original = managed.owner.bridge._capture_checked
    def lost(run_id, owner_id, manager, broker):
        if app.archive.get("job") is not None and broker.broker.runtime.task("job") is None:
            raise DurableSwarmError("injected archive checkpoint interruption")
        return original(run_id, owner_id, manager, broker)
    monkeypatch.setattr(managed.owner.bridge, "_capture_checked", lost)
    with pytest.raises(DurableSwarmError, match="injected"):
        app.tick()
    assert managed.owner.broker.is_retired()
    prepared = app.archive.get("job")
    assert prepared is not None
    assert app.result("a", "job")["result"] == 7
    clock.advance(21)
    reopened = LocalDispatcherApplication(app.directory, clock_ms=lambda: 100, store_clock=clock)
    reopened.start()
    assert reopened.tick().archived_tasks == ("job",)
    assert reopened.archive.get("job").archive_sha256 == prepared.archive_sha256
    assert reopened.archive.audit()["verified_jobs"] == 1
    assert reopened.custody.usage()["attempts"] == 1
    assert reopened.result("a", "job")["result"] == 7
    reopened.close()


def test_dispatcher_history_tamper_and_capacity_refuse_unsafe_reuse(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    import sqlite3
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_durable import DurableSwarmError
    app = LocalDispatcherApplication.initialize(
        tmp_path / "service", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=1, history_jobs=2,
    )
    app.start()
    for i in range(3):
        app.enqueue(f"req-{i}", {"kind": "submit", "tenant": "a", "task_id": f"job-{i}",
                                 "operation": "integer_sum", "input": [i]})
        app.tick()
    assert app.inbox.command("req-2")["status"] == "rejected"
    assert app.archive.audit()["verified_jobs"] == 2
    app.close()
    with sqlite3.connect(app.store.path) as conn:
        conn.execute("UPDATE hyperdispatcher_history SET body=? WHERE task_id=?", (b"{}", "job-0"))
    with pytest.raises(DurableSwarmError, match="integrity"):
        app.result("a", "job-0")
    with pytest.raises(DurableSwarmError, match="integrity"):
        app.archive.audit()


def test_dispatcher_history_keeps_live_parent_until_all_references_finish(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    now = [100]
    app = LocalDispatcherApplication.initialize(
        tmp_path / "service", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=2, history_jobs=8, clock_ms=lambda: now[0],
    )
    app.enqueue("parent", {"kind": "submit", "tenant": "a", "task_id": "parent",
                           "operation": "integer_sum", "input": [1]})
    app.enqueue("child", {"kind": "submit", "tenant": "a", "task_id": "child",
                          "operation": "integer_sum", "input": [2],
                          "dependencies": ["parent"], "timer_ms": 200})
    app.start()
    assert app.tick().task_id == "parent"
    assert app.archive.get("parent") is None
    assert app.managed.owner.broker.broker.runtime.task("parent") is not None
    now[0] = 200
    finished = app.tick()
    assert finished.task_id == "child" and finished.archived_tasks == ("child",)
    assert app.result("a", "child")["result"] == 2
    assert app.result("a", "parent")["result"] == 1
    app.close()


def test_authenticated_jeeves_dispatcher_gateway_runs_real_jobs_and_scopes_identities(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.app.runtime.jeeves_host_runtime import (
        JeevesHostContext, JeevesDispatcherGateway, JeevesHostRuntimeError,
    )
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "dispatcher", tenants=("tenant",), operations=("integer_sum",),
        workers=2, max_jobs=8,
    )
    scope = JeevesHostContext("tenant", "project", "principal", "run", "trace")
    other = JeevesHostContext("tenant", "other-project", "principal", "run", "trace")
    authorized = []
    def allow(question):
        authorized.append(question)
        return question.action != "cancel"
    gateway = JeevesDispatcherGateway(directory=app.directory, policy_sha256=app.policy.digest,
                                     scope=scope, authorize=allow)
    other_gateway = JeevesDispatcherGateway(directory=app.directory, policy_sha256=app.policy.digest,
                                           scope=other, authorize=allow)
    job = {"task_id": "job", "operation": "integer_sum", "input": [8, 9]}
    initial = gateway.execute(context=scope, action="submit", request_id="request", arguments=job)
    assert initial["status"] == "pending"
    assert gateway.execute(context=scope, action="submit", request_id="request", arguments=job) == initial
    other_gateway.execute(context=other, action="submit", request_id="request",
                          arguments=dict(job, input=[5, 6]))
    with pytest.raises(JeevesHostRuntimeError, match="scope"):
        gateway.execute(context=other, action="result", request_id="read", arguments={"task_id": "job"})
    with pytest.raises(JeevesHostRuntimeError, match="denied"):
        gateway.execute(context=scope, action="cancel", request_id="cancel", arguments={"task_id": "job"})
    with pytest.raises(JeevesHostRuntimeError, match="priority"):
        gateway.execute(context=scope, action="submit", request_id="urgent",
                        arguments=dict(job, priority=0))
    with pytest.raises(JeevesHostRuntimeError, match="unsupported"):
        gateway.execute(context=scope, action="stop", request_id="halt", arguments={})
    assert all(len(row.digest) == 64 for row in authorized)
    app.start()
    assert app.tick().disposition == "completed"
    first = gateway.execute(context=scope, action="result", request_id="read", arguments={"task_id": "job"})
    second = other_gateway.execute(context=other, action="result", request_id="read", arguments={"task_id": "job"})
    assert first["result"] == 17 and second["result"] == 11
    assert first["task_id"] != second["task_id"]
    assert gateway.execute(context=scope, action="command", request_id="inspect",
                           arguments={"request_id": "request"})["command"]["status"] == "accepted"
    app.close()


def test_actual_jeeves_application_runtime_dispatch_binding_and_cli(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from pathlib import Path
    from skeleton.app.runtime.jeeves_host_runtime import (
        JeevesApplicationRuntime, JeevesHostContext, JeevesHostRuntimeError,
    )
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.app.cli import _parser, run_app_cli
    app = LocalDispatcherApplication.initialize(
        tmp_path / "dispatcher", tenants=("a",), operations=("integer_sum",), max_jobs=4,
    )
    context = JeevesHostContext("a", "project", "principal", "run", "trace")
    repo_root = Path(__file__).resolve().parents[2]
    options = dict(root=repo_root, state_directory=tmp_path / "workbench",
                   scope=context, read_authorize=lambda *a, **kw: False,
                   orchestration_authorize=lambda *a, **kw: False)
    with pytest.raises(JeevesHostRuntimeError, match="three host"):
        JeevesApplicationRuntime(**options, dispatcher_directory=app.directory)
    with JeevesApplicationRuntime(
        **options, dispatcher_directory=app.directory,
        dispatcher_policy_sha256=app.policy.digest,
        dispatcher_authorize=lambda question: question.action in ("submit", "result"),
    ) as runtime:
        accepted = runtime.dispatch_request(
            context=context, action="submit", request_id="create",
            arguments={"task_id": "local", "operation": "integer_sum", "input": [19, 23]},
        )
        assert accepted["status"] == "pending"
        # The workbench routes to the real installed service owner, not a
        # hidden in-process executor. Canonical app CLI starts that owner.
        assert "dispatch" in _parser().format_help()
        assert run_app_cli(["dispatch", "--directory", str(app.directory),
                            "serve", "--max-cycles", "1"]) == 0
        result = runtime.dispatch_request(context=context, action="result", request_id="inspect",
                                          arguments={"task_id": "local"})
        assert result["result"] == 42
    with pytest.raises(JeevesHostRuntimeError, match="closed"):
        runtime.dispatch_request(context=context, action="result", request_id="inspect",
                                 arguments={"task_id": "local"})


def test_dispatcher_archive_rollover_preserves_strict_delta_and_monotonic_outer_boundary(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_recovery import SwarmRecoveryManager
    import sqlite3
    app = LocalDispatcherApplication.initialize(
        tmp_path / "archive-anchor", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=1, history_jobs=5,
    )
    app.start()
    initial = app.managed.owner.manager.store.latest().sequence
    app.enqueue("one", {"kind": "submit", "tenant": "a", "task_id": "job",
                         "operation": "integer_sum", "input": [9]})
    assert app.tick().archived_tasks == ("job",)
    current = app.store.resume_state("local-hyperdispatcher-v1").checkpoint
    anchor = SwarmRecoveryManager.from_archive(current.state)
    assert anchor.delta_archive
    assert len(anchor.store.history()) == 1
    assert anchor.store.latest().sequence > initial
    assert anchor.restore_latest().task("job") is None
    sealed = app.archive.get("job")
    with sqlite3.connect(app.store.path) as conn:
        row = conn.execute("SELECT revision,state_json FROM checkpoints WHERE checkpoint_id=?",
                           (sealed.source_checkpoint_id,)).fetchone()
    assert row is not None and row[0] < current.revision
    predecessor = SwarmRecoveryManager.from_archive_bytes(row[1].encode())
    assert predecessor.restore_latest().task("job").state.value == "succeeded"
    assert app.result("a", "job")["result"] == 9
    app.close()


def _linked_submit(task, request, parent, values, *, deadline=1000, tenant="a"):
    return {
        "kind": "submit", "tenant": tenant, "task_id": task,
        "operation": "integer_sum", "input": values,
        "bindings": [{"source_request_id": request, "source_task_id": parent,
                      "source_path": [], "target_path": [0]}],
        "binding_deadline_ms": deadline,
    }


def test_result_linked_pipeline_consumes_real_verified_outputs_across_archival(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from hashlib import sha256
    app = LocalDispatcherApplication.initialize(
        tmp_path / "pipeline", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=1, history_jobs=10, clock_ms=lambda: 100,
    )
    app.enqueue("p1", {"kind": "submit", "tenant": "a", "task_id": "first",
                       "operation": "integer_sum", "input": [1, 2]})
    app.enqueue("p2", _linked_submit("second", "p1", "first", [None, 4]))
    app.enqueue("p3", _linked_submit("third", "p2", "second", [None, 8]))
    app.start()
    first = app.tick()
    assert first.task_id == "first" and first.deferred_commands == ("p2", "p3")
    assert app.inbox.command("p2")["status"] == "pending"
    assert app.tick().task_id == "second"
    assert app.tick().task_id == "third"
    assert [app.result("a", name)["result"] for name in ("first", "second", "third")] == [3, 7, 15]
    leaf = app.result("a", "third")
    assert leaf["input_lineage"][0]["receipt_sha256"] == app.result("a", "second")["receipt_sha256"]
    assert leaf["input_lineage"][0]["value_sha256"] == sha256(b"7").hexdigest()
    assert app.archive.audit()["verified_jobs"] == 3
    app.close()
    restored = LocalDispatcherApplication(app.directory, clock_ms=lambda: 2000)
    assert restored.result("a", "third") == leaf
    assert restored.custody.usage()["attempts"] == 3


def test_result_linked_pending_round_robin_reaches_event_signal_and_cancellation(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "fair", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=8, clock_ms=lambda: 100,
    )
    app.enqueue("source", {"kind": "submit", "tenant": "a", "task_id": "source",
                           "operation": "integer_sum", "input": [2],
                           "event": {"selector": "ready", "not_before_ms": 100}})
    app.enqueue("one", _linked_submit("one", "source", "source", [None, 4]))
    app.enqueue("two", _linked_submit("two", "source", "source", [None, 7]))
    app.enqueue("cancel-two", {"kind": "cancel-pending", "tenant": "a", "request_id": "two"})
    app.enqueue("signal", {"kind": "signal", "tenant": "a", "task_id": "source",
                           "event_id": "event-1", "selector": "ready", "evidence": True})
    app.start()
    for _ in range(8):
        app.tick(command_limit=1)
    assert app.inbox.command("two")["status"] == "rejected"
    assert app.inbox.command("cancel-two")["status"] == "accepted"
    assert app.result("a", "one")["result"] == 6
    assert app.custody.usage()["attempts"] == 2
    app.close()


def test_result_bindings_deadline_cycle_scope_and_invalid_path_never_launch(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    now = [100]
    app = LocalDispatcherApplication.initialize(
        tmp_path / "refusal", tenants=("a", "b"), operations=("integer_sum",),
        workers=1, max_jobs=12, clock_ms=lambda: now[0],
    )
    app.enqueue("source", {"kind": "submit", "tenant": "a", "task_id": "source",
                           "operation": "integer_sum", "input": [1],
                           "timer_ms": 5000})
    app.enqueue("expire", _linked_submit("expire", "source", "source", [None], deadline=200))
    app.enqueue("foreign", _linked_submit("foreign", "source", "source", [None], tenant="b"))
    app.enqueue("forward", _linked_submit("forward", "later", "later", [None]))
    app.enqueue("later", _linked_submit("later", "forward", "forward", [None]))
    invalid = _linked_submit("invalid", "source", "source", [8])
    app.enqueue("invalid", invalid)
    app.start()
    app.tick()
    assert app.inbox.command("expire")["status"] == "pending"
    assert all(app.inbox.command(name)["status"] == "rejected"
               for name in ("foreign", "forward", "later", "invalid"))
    now[0] = 200
    app.tick()
    assert app.inbox.command("expire")["status"] == "rejected"
    assert app.custody.usage()["attempts"] == 0
    app.close()


def test_result_binding_replay_after_task_capture_before_acknowledgement(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.testing.test_durable_run_store import Clock
    clock = Clock()
    now = [100]
    app = LocalDispatcherApplication.initialize(
        tmp_path / "replay", tenants=("a",), operations=("integer_sum",), workers=1,
        max_jobs=4, timeout_seconds=1, lease_seconds=20,
        clock_ms=lambda: now[0], store_clock=clock,
    )
    app.enqueue("root", {"kind": "submit", "tenant": "a", "task_id": "root",
                         "operation": "integer_sum", "input": [2, 3]})
    app.start()
    assert app.tick().task_id == "root"
    app.enqueue("child", _linked_submit("child", "root", "root", [None, 11], deadline=200))
    command = app.inbox.pending()[0]
    assert app._apply(command)["submission"] == "durable"
    assert app.inbox.command("child")["status"] == "pending"
    app.managed.stop()
    clock.advance(21)
    now[0] = 500
    restored = LocalDispatcherApplication(app.directory, clock_ms=lambda: now[0], store_clock=clock)
    restored.start()
    assert restored.tick().task_id == "child"
    assert restored.inbox.command("child")["status"] == "accepted"
    assert restored.result("a", "child")["result"] == 16
    assert restored.custody.usage()["attempts"] == 2
    restored.close()


def test_binding_path_exact_json_nested_values_and_overlap_refusal():
    from skeleton.automation.agents.swarm_dispatch_bindings import (
        BindingError, materialize, parse_bindings,
    )
    template = {"prompt": None, "settings": [None]}
    raw = [
        {"source_request_id": "r", "source_task_id": "a", "source_path": ["text"], "target_path": ["prompt"]},
        {"source_request_id": "r", "source_task_id": "a", "source_path": ["tokens", 1], "target_path": ["settings", 0]},
    ]
    bindings = parse_bindings(raw, template, task_id="b")
    calls = []
    def proof(binding):
        calls.append(binding.source_task_id)
        return {"task_id": "a", "state": "succeeded", "uncertain_on_restore": False,
                "receipt_sha256": "a"*64, "result": {"text": "literal {not a command}", "tokens": [1, 2]}}
    output, lineage = materialize(template, bindings, proof)
    assert output == {"prompt": "literal {not a command}", "settings": [2]}
    assert template == {"prompt": None, "settings": [None]}
    assert calls == ["a"] and len(lineage) == 2
    with pytest.raises(BindingError):
        parse_bindings(raw + [raw[0]], template, task_id="b")
    with pytest.raises(BindingError):
        parse_bindings([dict(raw[0], target_path=["settings"])], template, task_id="b")


def test_host_gateway_scopes_linked_source_requests_and_real_results(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.app.runtime.jeeves_host_runtime import JeevesHostContext, JeevesDispatcherGateway
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "service", tenants=("a",), operations=("integer_sum",), workers=1, max_jobs=8,
    )
    scope = JeevesHostContext("a", "project", "principal", "run", "trace")
    gateway = JeevesDispatcherGateway(directory=app.directory, policy_sha256=app.policy.digest,
                                     scope=scope, authorize=lambda question: True)
    gateway.execute(context=scope, action="submit", request_id="parent",
                    arguments={"task_id": "parent", "operation": "integer_sum", "input": [5, 6]})
    child = _linked_submit("child", "parent", "parent", [None, 10],
                           deadline=app.clock_ms() + 60000)
    child.pop("tenant")
    child.pop("kind")
    gateway.execute(context=scope, action="submit", request_id="child", arguments=child)
    app.start()
    app.tick()
    app.tick()
    result = gateway.execute(context=scope, action="result", request_id="inspect", arguments={"task_id": "child"})
    assert result["result"] == 21
    assert result["input_lineage"][0]["source_task_id"].startswith("app-task-")
    assert result["input_lineage"][0]["source_request_id"].startswith("app-request-")
    app.close()


def _workflow_node(request_id, task_id, value, **extra):
    return {"request_id": request_id, "task_id": task_id, "operation": "integer_sum",
            "input": value, **extra}


def test_atomic_workflow_topological_order_and_actual_fanin_with_one_resident_slot(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "graph", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=1, history_jobs=12, clock_ms=lambda: 100,
    )
    graph = {"deadline_ms": 1000, "jobs": [
        _workflow_node("r3", "c", [None, None, 3], bindings=[
            {"source_request_id": "r1", "source_task_id": "a",
             "source_path": [], "target_path": [0]},
            {"source_request_id": "r2", "source_task_id": "b",
             "source_path": [], "target_path": [1]},
        ]),
        _workflow_node("r2", "b", [5, 6], dependencies=["a"]),
        _workflow_node("r1", "a", [2, 4]),
    ]}
    receipt = app.enqueue_workflow("a", "workflow", graph)
    assert [row["task_id"] for row in receipt["jobs"]] == ["a", "b", "c"]
    assert app.enqueue_workflow("a", "workflow", {"deadline_ms": 1000,
                                                 "jobs": list(reversed(graph["jobs"]))}) == receipt
    app.start()
    for _ in range(6):
        if app.workflow_status("a", "workflow")["workflow_state"] == "succeeded":
            break
        app.tick()
    assert app.result("a", "c")["result"] == 20
    assert app.result("a", "b")["input_lineage"][0]["dependency_only"] is True
    state = app.workflow_status("a", "workflow")
    assert state["workflow_state"] == "succeeded" and state["counts"]["succeeded"] == 3
    app.close()
    reopened = LocalDispatcherApplication(app.directory, clock_ms=lambda: 2000)
    assert reopened.workflow_status("a", "workflow") == state
    assert reopened.custody.usage()["attempts"] == 3


def test_workflow_atomic_conflict_cycle_and_invalid_operation_leave_no_partial_rows(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication, DispatcherRequestError
    app = LocalDispatcherApplication.initialize(
        tmp_path / "graph", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=8, clock_ms=lambda: 100,
    )
    app.enqueue("existing", {"kind": "submit", "tenant": "a", "task_id": "standalone",
                             "operation": "integer_sum", "input": [1]})
    candidates = [
        [_workflow_node("fresh", "a", [1]), _workflow_node("existing", "b", [2])],
        [_workflow_node("fresh", "a", [1], dependencies=["b"]),
         _workflow_node("other", "b", [2], dependencies=["a"])],
        [_workflow_node("fresh", "a", [1]), _workflow_node("other", "b", ["bad"])],
    ]
    for nodes in candidates:
        with pytest.raises(DispatcherRequestError):
            app.enqueue_workflow("a", "refused", {"deadline_ms": 1000, "jobs": nodes})
        assert app.inbox.command("fresh") is None
        assert app.inbox.workflow("a", "refused") is None
    assert app.inbox.summary()["pending"] == 1


def test_workflow_manifest_and_command_tampering_fail_closed(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    import sqlite3
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_durable import DurableSwarmError
    app = LocalDispatcherApplication.initialize(
        tmp_path / "graph", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=4, clock_ms=lambda: 100,
    )
    app.enqueue_workflow("a", "tamper", {"deadline_ms": 1000,
                         "jobs": [_workflow_node("r", "job", [2])]})
    with sqlite3.connect(app.store.path) as conn:
        conn.execute("UPDATE hyperdispatcher_inbox SET body=? WHERE request_id=?", (b"{}", "r"))
    with pytest.raises(DurableSwarmError, match="integrity"):
        app.workflow_status("a", "tamper")


def test_workflow_host_requires_graph_and_each_operation_authorization(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.app.runtime.jeeves_host_runtime import JeevesHostContext, JeevesDispatcherGateway, JeevesHostRuntimeError
    app = LocalDispatcherApplication.initialize(
        tmp_path / "graph", tenants=("a",), operations=("integer_sum",), workers=1, max_jobs=8,
    )
    scope = JeevesHostContext("a", "project", "principal", "run", "trace")
    graph = {"deadline_ms": app.clock_ms()+60000, "jobs": [
        _workflow_node("parent", "parent", [4]),
        _workflow_node("child", "child", [6], dependencies=["parent"]),
    ]}
    calls = []
    def allow(question):
        calls.append((question.action, question.request_id))
        return question.request_id != "child"
    gateway = JeevesDispatcherGateway(directory=app.directory, policy_sha256=app.policy.digest,
                                     scope=scope, authorize=allow)
    with pytest.raises(JeevesHostRuntimeError, match="child authorization denied"):
        gateway.execute(context=scope, action="workflow-submit", request_id="flow", arguments=graph)
    assert app.inbox.summary()["pending"] == 0
    assert calls == [("workflow-submit", "flow"), ("submit", "parent"), ("submit", "child")]
    permitted = JeevesDispatcherGateway(directory=app.directory, policy_sha256=app.policy.digest,
                                       scope=scope, authorize=lambda q: True)
    permitted.execute(context=scope, action="workflow-submit", request_id="flow", arguments=graph)
    app.start()
    app.tick()
    app.tick()
    state = permitted.execute(context=scope, action="workflow-status", request_id="inspect",
                              arguments={"workflow_id": "flow"})
    assert state["workflow_state"] == "succeeded"
    assert state["counts"]["succeeded"] == 2
    app.close()


def test_workflow_independent_roots_wait_for_resident_capacity_and_claim_task_ids(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication, DispatcherRequestError
    app = LocalDispatcherApplication.initialize(
        tmp_path / "roots", tenants=("a", "b"), operations=("integer_sum",),
        workers=1, max_jobs=1, history_jobs=12, clock_ms=lambda: 100,
    )
    app.enqueue_workflow("a", "roots", {"deadline_ms": 1000, "jobs": [
        _workflow_node("a1", "a1", [1]), _workflow_node("a2", "a2", [2]),
        _workflow_node("a3", "a3", [3]),
    ]})
    with pytest.raises(DispatcherRequestError, match="reserved"):
        app.enqueue("foreign", {"kind": "submit", "tenant": "b", "task_id": "a2",
                                "operation": "integer_sum", "input": [90]})
    with pytest.raises(DispatcherRequestError, match="identity"):
        app.enqueue_workflow("b", "collision", {"deadline_ms": 1000, "jobs": [
            _workflow_node("c1", "a2", [90]),
        ]})
    app.start()
    assert app.tick().deferred_commands == ("a2", "a3")
    app.tick()
    app.tick()
    assert app.workflow_status("a", "roots")["workflow_state"] == "succeeded"
    assert app.custody.usage()["attempts"] == 3
    app.close()


def test_workflow_root_admission_deadline_expires_without_physical_attempt(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    now = [100]
    app = LocalDispatcherApplication.initialize(
        tmp_path / "deadline", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=2, clock_ms=lambda: now[0],
    )
    app.enqueue_workflow("a", "late", {"deadline_ms": 200,
                                      "jobs": [_workflow_node("r", "job", [2])]})
    now[0] = 200
    app.start()
    assert app.tick().disposition == "idle"
    assert app.inbox.command("r")["status"] == "rejected"
    assert app.custody.usage()["attempts"] == 0
    app.close()


def test_workflow_cancellation_stops_queued_and_unadmitted_nodes_without_fake_effects(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "cancel", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=2, history_jobs=8, clock_ms=lambda: 100,
    )
    app.enqueue_workflow("a", "flow", {"deadline_ms": 1000, "jobs": [
        _workflow_node("r1", "parent", [2], timer_ms=300),
        _workflow_node("r2", "child", [5], dependencies=["parent"]),
    ]})
    app.enqueue("stop-flow", {"kind": "workflow-cancel", "tenant": "a", "workflow_id": "flow"})
    app.start()
    app.tick()
    state = app.workflow_status("a", "flow")
    assert state["workflow_state"] == "cancelled"
    assert state["counts"]["cancelled"] == 1 and state["counts"]["rejected"] == 1
    assert state["cancellation"]["result"]["active_effects_terminated"] is False
    assert app.custody.usage()["attempts"] == 0
    app.enqueue("stop-again", {"kind": "workflow-cancel", "tenant": "a", "workflow_id": "flow"})
    app.tick()
    assert app.inbox.command("stop-again")["result"] == app.inbox.command("stop-flow")["result"]
    app.close()


def test_workflow_cancel_intent_recovered_before_new_dispatch_after_owner_loss(tmp_path, monkeypatch):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_durable import DurableSwarmError
    from skeleton.testing.test_durable_run_store import Clock
    clock, now = Clock(), [100]
    app = LocalDispatcherApplication.initialize(
        tmp_path / "recover-cancel", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=4, history_jobs=10, timeout_seconds=1, lease_seconds=20,
        store_clock=clock, clock_ms=lambda: now[0],
    )
    app.enqueue_workflow("a", "flow", {"deadline_ms": 1000, "jobs": [
        _workflow_node("r1", "first", [1], timer_ms=200),
        _workflow_node("r2", "second", [2], timer_ms=200),
    ]})
    managed = app.start()
    app.tick()
    app.enqueue("cancel", {"kind": "workflow-cancel", "tenant": "a", "workflow_id": "flow"})
    original = managed.cancel_queued
    calls = []
    def interrupted(tenant, task_id):
        calls.append(task_id)
        if len(calls) == 2:
            raise DurableSwarmError("injected owner loss during graph cancellation")
        return original(tenant, task_id)
    monkeypatch.setattr(managed, "cancel_queued", interrupted)
    with pytest.raises(DurableSwarmError, match="injected"):
        app.tick()
    assert app.inbox.cancellation("a", "flow")["status"] == "pending"
    managed.stop()
    clock.advance(21)
    now[0] = 300
    recovered = LocalDispatcherApplication(app.directory, store_clock=clock, clock_ms=lambda: now[0])
    recovered.start()
    recovered.tick(command_limit=1)
    state = recovered.workflow_status("a", "flow")
    assert state["workflow_state"] == "cancelled" and state["counts"]["cancelled"] == 2
    assert recovered.custody.usage()["attempts"] == 0
    recovered.close()


def test_workflow_cancel_preserves_unresolved_physical_attempt(tmp_path, monkeypatch):
    import os
    import subprocess
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "held", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=4, clock_ms=lambda: 100,
    )
    app.enqueue_workflow("a", "flow", {"deadline_ms": 1000, "jobs": [
        _workflow_node("r1", "parent", [1]),
        _workflow_node("r2", "child", [2], dependencies=["parent"]),
    ]})
    app.start()
    def unknown(*args, **kwargs):
        raise subprocess.TimeoutExpired("approved worker", 1)
    monkeypatch.setattr(subprocess, "run", unknown)
    assert app.tick().disposition == "transport-unknown"
    app.enqueue("cancel", {"kind": "workflow-cancel", "tenant": "a", "workflow_id": "flow"})
    app.tick()
    state = app.workflow_status("a", "flow")
    assert state["workflow_state"] == "cancelled-held-uncertain"
    assert state["counts"]["uncertain"] == 1
    assert state["cancellation"]["result"]["counts"]["held_uncertain"] == 1
    assert app.custody.usage()["attempts"] == 1
    app.close()


def test_workflow_host_graph_cancellation_requires_its_own_scope_grant(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.app.runtime.jeeves_host_runtime import JeevesHostContext, JeevesDispatcherGateway, JeevesHostRuntimeError
    app = LocalDispatcherApplication.initialize(
        tmp_path / "scope", tenants=("a",), operations=("integer_sum",), workers=1, max_jobs=4,
    )
    context = JeevesHostContext("a", "p", "owner", "r", "t")
    gateway = JeevesDispatcherGateway(directory=app.directory, policy_sha256=app.policy.digest,
                                     scope=context, authorize=lambda q: q.action != "workflow-cancel")
    gateway.execute(context=context, action="workflow-submit", request_id="flow", arguments={
        "deadline_ms": app.clock_ms()+60000, "jobs": [_workflow_node("req", "job", [5])],
    })
    with pytest.raises(JeevesHostRuntimeError, match="denied"):
        gateway.execute(context=context, action="workflow-cancel", request_id="cancel",
                        arguments={"workflow_id": "flow"})
    granted = JeevesDispatcherGateway(directory=app.directory, policy_sha256=app.policy.digest,
                                     scope=context, authorize=lambda q: True)
    granted.execute(context=context, action="workflow-cancel", request_id="cancel",
                    arguments={"workflow_id": "flow"})
    app.start()
    app.tick()
    state = granted.execute(context=context, action="workflow-status", request_id="inspect",
                            arguments={"workflow_id": "flow"})
    assert state["workflow_state"] == "cancelled" and app.custody.usage()["attempts"] == 0
    app.close()


def test_ingress_ledger_atomic_retry_and_graph_collisions_preserve_exact_totals(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication, DispatcherRequestError
    app = LocalDispatcherApplication.initialize(
        tmp_path / "ledger", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=4, clock_ms=lambda: 100,
    )
    malformed = {"kind": "submit", "tenant": "a", "task_id": ["invalid"],
                 "operation": "integer_sum", "input": [1]}
    app.enqueue("invalid", malformed)
    initial = app.inbox.audit()
    assert initial["verified_commands"] == 1 and initial["verified_indexed_tasks"] == 0
    standalone = {"kind": "submit", "tenant": "a", "task_id": "reserved",
                  "operation": "integer_sum", "input": [2]}
    app.enqueue("existing", standalone)
    before = app.inbox.audit()
    with pytest.raises(DispatcherRequestError, match="identity"):
        app.enqueue_workflow("a", "conflict", {"deadline_ms": 1000, "jobs": [
            _workflow_node("fresh", "fresh", [3]), _workflow_node("colliding", "reserved", [4]),
        ]})
    assert app.inbox.audit() == before
    graph = {"deadline_ms": 1000, "jobs": [_workflow_node("fresh", "fresh", [3])]}
    receipt = app.enqueue_workflow("a", "valid", graph)
    after = app.inbox.audit()
    assert after["verified_commands"] == 3 and after["verified_workflows"] == 1
    assert after["verified_indexed_tasks"] == after["verified_commands"]-1
    assert app.enqueue_workflow("a", "valid", graph) == receipt
    assert app.enqueue("existing", standalone)["status"] == "pending"
    assert app.inbox.audit() == after


def test_ingress_index_and_ledger_migration_preserves_sealed_graph_and_retries(tmp_path):
    import os
    import sqlite3
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "old", tenants=("a",), operations=("integer_sum",),
        max_jobs=4, clock_ms=lambda: 100,
    )
    graph = {"deadline_ms": 1000, "jobs": [_workflow_node("r", "job", [7])]}
    expected = app.enqueue_workflow("a", "flow", graph)
    audit = app.inbox.audit()
    with sqlite3.connect(app.store.path) as conn:
        conn.execute("DROP TABLE hyperdispatcher_submit_index")
        conn.execute("DROP TABLE hyperdispatcher_ingress_totals")
    reopened = LocalDispatcherApplication(app.directory, clock_ms=lambda: 100)
    assert reopened.inbox.audit() == audit
    assert reopened.enqueue_workflow("a", "flow", graph) == expected
    reopened.start()
    assert reopened.tick().disposition == "completed"
    assert reopened.result("a", "job")["result"] == 7
    reopened.close()


def test_ingress_ledger_corruption_detected_before_new_owner_admits_work(tmp_path):
    import os
    import sqlite3
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_durable import DurableSwarmError
    app = LocalDispatcherApplication.initialize(
        tmp_path / "broken", tenants=("a",), operations=("integer_sum",), max_jobs=4,
    )
    app.enqueue("r", {"kind": "submit", "tenant": "a", "task_id": "job",
                      "operation": "integer_sum", "input": [1]})
    with sqlite3.connect(app.store.path) as conn:
        conn.execute("UPDATE hyperdispatcher_ingress_totals SET reserved_bytes=reserved_bytes-1")
    with pytest.raises(DurableSwarmError, match="audit totals"):
        app.start()
    assert app.custody.usage()["attempts"] == 0
    assert app.store.get_run("local-hyperdispatcher-v1").worker_id is None


def test_dispatch_candidate_requires_exact_ack_before_physical_launch(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    app = LocalDispatcherApplication.initialize(
        tmp_path / "ack", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=4, clock_ms=lambda: 100,
    )
    app.enqueue("first", {"kind": "submit", "tenant": "a", "task_id": "job",
                          "operation": "integer_sum", "input": [12]})
    app.start()
    lost_ack = app.inbox.pending()[0]
    assert app._apply(lost_ack)["submission"] == "durable"
    assert app._candidates(100) == ()
    assert app.custody.usage()["attempts"] == 0
    assert app.tick().task_id == "job"
    assert app.result("a", "job")["result"] == 12
    app.close()


def test_dispatch_candidate_refuses_changed_workflow_manifest_before_transport(tmp_path):
    import os
    import sqlite3
    if os.name != "posix":
        pytest.skip("POSIX private-directory qualification")
    from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
    from skeleton.automation.agents.swarm_durable import DurableSwarmError
    now = [100]
    app = LocalDispatcherApplication.initialize(
        tmp_path / "manifest", tenants=("a",), operations=("integer_sum",),
        workers=1, max_jobs=4, clock_ms=lambda: now[0],
    )
    app.enqueue_workflow("a", "flow", {"deadline_ms": 1000,
                         "jobs": [_workflow_node("r", "job", [1], timer_ms=200)]})
    app.start()
    assert app.tick().disposition == "idle"
    with sqlite3.connect(app.store.path) as conn:
        conn.execute("UPDATE hyperdispatcher_workflows SET manifest=? WHERE workflow_id=?",
                     (b"{}", "flow"))
    now[0] = 200
    with pytest.raises(DurableSwarmError, match="seal mismatch"):
        app.tick()
    assert app.custody.usage()["attempts"] == 0
    app.managed.stop()
