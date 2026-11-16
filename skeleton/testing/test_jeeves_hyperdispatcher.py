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
