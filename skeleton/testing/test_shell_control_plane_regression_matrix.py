"""Cross-plane regression matrix for shell control-plane invariants.

This file intentionally exercises interactions that are easy to break when the
individual modules continue evolving independently.
"""

from __future__ import annotations

from dataclasses import replace
import sys

import pytest

from skeleton.shells.admission_lease import AdmissionLeaseConflict, AdmissionLeases
from skeleton.shells.approvals import ApprovalError, ApprovalRegistry
from skeleton.shells.cancellation import CancellationReason, CancellationRegistry
from skeleton.shells.change_control import ChangeControl, ChangeState
from skeleton.shells.command_budget import CommandBudgetPolicy, CommandBudgets
from skeleton.shells.concurrency import WeightedConcurrency
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_history import ExecutionHistory, HistoryQuery
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.feature_gates import FeatureGate, FeatureGateRegistry
from skeleton.shells.incident import IncidentRegistry, IncidentSeverity, IncidentState
from skeleton.shells.maintenance import ShellMaintenance, ShellMaintenanceWindow
from skeleton.shells.namespace import NamespaceRegistry, ShellNamespace
from skeleton.shells.output_policy import OutputClass, OutputClassifier, OutputRetentionPolicy
from skeleton.shells.plan_store import PlanConflict, PlanStore
from skeleton.shells.policy_rollout import PolicyRolloutManager, RolloutPhase
from skeleton.shells.policy_store import PolicyConflict, PolicyStore
from skeleton.shells.receipts import ExecutionReceipt, ReceiptChain
from skeleton.shells.retention import OutputRetentionStore
from skeleton.shells.runner import ShellCommand, ShellPolicy
from skeleton.shells.service_state import ShellServicePhase, ShellServiceState
from skeleton.shells.shell_events import ShellEvents
from skeleton.shells.tracing import ShellTracer


def shell_policy(tmp_path, *, timeout=10, output=1024):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    return ShellPolicy(
        executables={"python": sys.executable},
        cwd_roots=(root,),
        default_timeout=2,
        max_timeout=timeout,
        max_output_bytes=output,
        max_input_bytes=1024,
        max_env_bytes=1024,
        max_args=16,
        max_arg_bytes=1024,
    )


def plan(plan_id="p", arg="1"):
    return ExecutionPlan(
        plan_id,
        (
            PlanStep("a", ShellCommand("python", ("-c", f"print({arg})"))),
            PlanStep(
                "b",
                ShellCommand("python", ("-c", "print(2)")),
                frozenset({"a"}),
            ),
        ),
    )


def receipt(command="python", correlation="c", *, ok=True, timeout=False, limited=False):
    return ExecutionReceipt(
        command=command,
        correlation_id=correlation,
        fingerprint="fp",
        started_at="s",
        finished_at="f",
        duration_ms=1,
        returncode=0 if ok else 1,
        ok=ok,
        timed_out=timeout,
        output_limited=limited,
        stdout_bytes=1,
        stderr_bytes=0,
    )


def test_policy_store_and_rollout_preserve_revision_history(tmp_path):
    base = shell_policy(tmp_path, timeout=10)
    store = PolicyStore(base)
    manager = PolicyRolloutManager(store)
    rollout = manager.prepare("r", shell_policy(tmp_path, timeout=9))
    manager.advance("r")
    manager.rollback("r")
    history = store.history()
    assert len(history) == 3
    assert history[0].policy == base
    assert history[1].revision == rollout.target_revision
    assert history[2].policy == base


def test_policy_store_conflict_does_not_modify_current(tmp_path):
    store = PolicyStore(shell_policy(tmp_path))
    second = store.replace(shell_policy(tmp_path, timeout=9))
    with pytest.raises(PolicyConflict):
        store.compare_and_swap(1, shell_policy(tmp_path, timeout=8))
    assert store.current() == second


def test_rollout_prepared_target_has_revision_identity(tmp_path):
    store = PolicyStore(shell_policy(tmp_path))
    rollout = PolicyRolloutManager(store).prepare(
        "r",
        shell_policy(tmp_path, timeout=9),
    )
    assert rollout.base_revision != rollout.target_revision


def test_rollout_phase_timestamps_monotonic(tmp_path):
    now = [0.0]
    store = PolicyStore(shell_policy(tmp_path))
    manager = PolicyRolloutManager(store, clock=lambda: now[0])
    first = manager.prepare("r", shell_policy(tmp_path, timeout=9))
    now[0] = 1
    second = manager.advance("r")
    assert second.updated_at > first.updated_at


def test_plan_store_versions_keep_old_plan(tmp_path):
    store = PlanStore()
    first = store.put(plan(arg="1"))
    second = store.put(plan(arg="2"), expected_version=1)
    assert first.plan.steps[0].command.args != second.plan.steps[0].command.args
    assert store.at("p", 1).plan == first.plan
    assert store.at("p", 2).plan == second.plan


def test_plan_store_conflict_keeps_history_length():
    store = PlanStore()
    store.put(plan(arg="1"))
    with pytest.raises(PlanConflict):
        store.put(plan(arg="2"), expected_version=0)
    assert len(store.history("p")) == 1


def test_plan_store_identical_put_does_not_supersede():
    store = PlanStore()
    first = store.put(plan())
    second = store.put(plan())
    assert first == second
    assert not store.current("p").superseded


def test_plan_dependency_shape_is_stable():
    item = plan()
    shapes = [step.shape() for step in item.steps]
    assert shapes[0]["depends_on"] == []
    assert shapes[1]["depends_on"] == ["a"]


def test_context_parent_chain():
    root = ExecutionContext("root", principal="p")
    child = root.child("child")
    grand = child.child("grand")
    assert child.parent_correlation_id == "root"
    assert grand.parent_correlation_id == "child"


def test_context_same_data_same_fingerprint():
    a = ExecutionContext("c", principal="p", tags=frozenset({"x"}), attributes={"a": "b"})
    b = ExecutionContext("c", principal="p", tags=frozenset({"x"}), attributes={"a": "b"})
    assert a.fingerprint == b.fingerprint


def test_context_principal_affects_fingerprint():
    a = ExecutionContext("c", principal="p")
    b = ExecutionContext("c", principal="q")
    assert a.fingerprint != b.fingerprint


def test_feature_gate_registry_replacement_changes_behavior():
    registry = FeatureGateRegistry()
    registry.set(FeatureGate("x", enabled=False))
    assert not registry.enabled("x", "p")
    registry.set(FeatureGate("x", enabled=True, rollout_percent=100))
    assert registry.enabled("x", "p")


def test_feature_gate_deny_principal_survives_full_rollout():
    gate = FeatureGate(
        "x",
        enabled=True,
        rollout_percent=100,
        deny_principals=frozenset({"p"}),
    )
    assert not gate.evaluate("p")
    assert gate.evaluate("q")


def test_feature_gate_allow_principal_survives_zero_rollout():
    gate = FeatureGate(
        "x",
        enabled=True,
        rollout_percent=0,
        allow_principals=frozenset({"p"}),
    )
    assert gate.evaluate("p")
    assert not gate.evaluate("q")


def test_namespace_and_gate_can_both_deny():
    namespace = ShellNamespace("n", principals=frozenset({"p"}))
    gate = FeatureGate("x", enabled=False)
    assert namespace.allows_principal("p")
    assert not gate.evaluate("p")


def test_namespace_command_prefix_does_not_match_middle():
    namespace = ShellNamespace("n", command_prefixes=frozenset({"build."}))
    assert not namespace.allows_command("xbuild.compile")
    assert namespace.allows_command("build.compile")


def test_namespace_registry_unknown_namespace_raises():
    with pytest.raises(KeyError):
        NamespaceRegistry().authorize("missing", principal="p", command="python")


def test_maintenance_window_can_observe_without_denial():
    now = [5.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.add(
        ShellMaintenanceWindow(
            "observe",
            0,
            10,
            reason="watch",
            deny_new=False,
        )
    )
    assert maintenance.active(command="python", principal="p")
    assert maintenance.admit(command="python", principal="p")


def test_maintenance_scope_composes_command_and_principal():
    now = [5.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.add(
        ShellMaintenanceWindow(
            "w",
            0,
            10,
            command_prefix="deploy.",
            principal="ops",
        )
    )
    assert not maintenance.admit(command="deploy.prod", principal="ops")
    assert maintenance.admit(command="deploy.prod", principal="dev")
    assert maintenance.admit(command="test.unit", principal="ops")


def test_change_control_approval_sorting():
    control = ChangeControl(required_approvals=3)
    item = control.propose(
        kind="policy",
        target="shell",
        summary="x",
        payload={"x": 1},
        proposed_by="a",
    )
    for approver in ("z", "b", "m"):
        item = control.approve(item.change_id, approver)
    assert item.approvals == ("b", "m", "z")
    assert item.state is ChangeState.APPROVED


def test_change_control_payload_change_changes_digest():
    control = ChangeControl()
    a = control.propose(
        kind="policy",
        target="shell",
        summary="x",
        payload={"x": 1},
        proposed_by="a",
    )
    b = control.propose(
        kind="policy",
        target="shell",
        summary="x",
        payload={"x": 2},
        proposed_by="a",
    )
    assert a.payload_digest != b.payload_digest


def test_approval_fingerprint_binding_is_exact():
    registry = ApprovalRegistry()
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="abc",
        approved_by="a",
    )
    with pytest.raises(ApprovalError):
        registry.require(
            approval,
            principal="p",
            command="python",
            fingerprint="ABC",
        )


def test_approval_expired_entry_does_not_consume_capacity():
    now = [0.0]
    registry = ApprovalRegistry(max_approvals=1, clock=lambda: now[0])
    registry.approve(
        principal="p",
        command="python",
        fingerprint="a",
        approved_by="a",
        ttl_seconds=1,
    )
    now[0] = 2
    second = registry.approve(
        principal="p",
        command="python",
        fingerprint="b",
        approved_by="a",
    )
    assert second.fingerprint == "b"


def test_admission_lease_expiry_frees_same_key():
    now = [0.0]
    leases = AdmissionLeases(clock=lambda: now[0])
    first = leases.acquire("x", principal="p", command="python", ttl_seconds=1)
    now[0] = 2
    second = leases.acquire("x", principal="p", command="python")
    assert first.lease_id != second.lease_id


def test_admission_lease_wrong_revision_release_fails():
    leases = AdmissionLeases()
    first = leases.acquire("x", principal="p", command="python")
    second = leases.renew(first)
    assert not leases.release(first)
    assert leases.release(second)


def test_command_budget_independent_commands():
    budgets = CommandBudgets(CommandBudgetPolicy(max_starts=1))
    budgets.reserve_start("python")
    assert not budgets.inspect("python").allowed
    assert budgets.inspect("git").allowed


def test_command_budget_failure_does_not_change_start_count():
    budgets = CommandBudgets()
    budgets.record_result("python", ok=False, runtime_ms=1, output_bytes=1)
    usage = budgets.snapshot()["python"]
    assert usage.starts == 0
    assert usage.failures == 1


def test_command_budget_start_does_not_change_failure_count():
    budgets = CommandBudgets()
    usage = budgets.reserve_start("python")
    assert usage.starts == 1
    assert usage.failures == 0


def test_concurrency_owner_accounting():
    limiter = WeightedConcurrency(4)
    a1 = limiter.acquire(1, owner="a")
    a2 = limiter.acquire(2, owner="a")
    b = limiter.acquire(1, owner="b")
    assert len(limiter.by_owner("a")) == 2
    assert len(limiter.by_owner("b")) == 1
    limiter.release(a1)
    limiter.release(a2)
    limiter.release(b)
    assert limiter.snapshot().used == 0


def test_events_keep_sequence_monotonic_after_eviction():
    events = ShellEvents(max_events=2)
    first = events.emit("a")
    second = events.emit("b")
    third = events.emit("c")
    fourth = events.emit("d")
    assert [item.sequence for item in events.tail(10)] == [third.sequence, fourth.sequence]
    assert fourth.sequence > second.sequence > first.sequence


def test_events_filters_compose():
    events = ShellEvents()
    events.emit("x", correlation_id="a", command="python")
    target = events.emit("x", correlation_id="b", command="python")
    events.emit("y", correlation_id="b", command="python")
    assert events.query(kind="x", correlation_id="b", command="python") == (target,)


def test_tracer_parent_ids_are_preserved():
    tracer = ShellTracer()
    root = tracer.start("root", trace_id="t")
    child = tracer.start("child", trace_id="t", parent_span_id=root.span_id)
    assert child.parent_span_id == root.span_id


def test_tracer_finished_span_stays_in_trace():
    tracer = ShellTracer()
    span = tracer.start("x", trace_id="t")
    finished = tracer.finish(span)
    assert tracer.trace("t") == (finished,)


def test_output_classification_and_retention_pipeline():
    classifier = OutputClassifier(secret_patterns=("secret",))
    policy = OutputRetentionPolicy()
    data = b"secret-value"
    classification = classifier.classify(data)
    classified = policy.apply(data, classification)
    store = OutputRetentionStore()
    stored = store.put("x", classified, retention_seconds=10)
    assert classification is OutputClass.SECRET
    assert stored.payload == b""
    assert stored.digest


def test_output_retention_internal_keeps_only_policy_bytes():
    policy = OutputRetentionPolicy()
    data = b"x" * (70 * 1024)
    classified = policy.apply(data, OutputClass.INTERNAL)
    store = OutputRetentionStore()
    stored = store.put("x", classified, retention_seconds=10)
    assert len(stored.payload) == 64 * 1024


def test_receipt_chain_root_changes_each_append():
    chain = ReceiptChain()
    genesis = chain.root_hash()
    chain.append(receipt(correlation="a"))
    first = chain.root_hash()
    chain.append(receipt(correlation="b"))
    second = chain.root_hash()
    assert genesis != first != second


def test_receipt_chain_tamper_does_not_change_root_property_but_breaks_verify():
    chain = ReceiptChain()
    chain.append(receipt())
    root = chain.root_hash()
    item = chain._items[0]
    chain._items[0] = replace(item, previous_hash="x" * 64)
    assert chain.root_hash() == root
    assert not chain.verify()


def test_history_summary_counts_commands_after_eviction():
    history = ExecutionHistory(max_receipts=2)
    history.append(receipt(command="old", correlation="a"))
    history.append(receipt(command="python", correlation="b"))
    history.append(receipt(command="python", correlation="c"))
    summary = history.summary()
    assert summary.total == 2
    assert summary.commands == {"python": 2}


def test_history_query_combines_filters():
    history = ExecutionHistory()
    a = receipt(command="python", correlation="a", ok=True)
    b = receipt(command="python", correlation="b", ok=False, timeout=True)
    c = receipt(command="git", correlation="b", ok=False)
    history.extend((a, b, c))
    assert history.query(
        HistoryQuery(command="python", ok=False, timed_out=True)
    ) == (b,)


def test_incident_acknowledged_then_mitigated_preserves_actor():
    registry = IncidentRegistry()
    incident = registry.open(IncidentSeverity.ERROR, "x")
    acknowledged = registry.acknowledge(incident.incident_id, "operator")
    mitigated = registry.mitigate(incident.incident_id)
    assert mitigated.acknowledged_by == acknowledged.acknowledged_by == "operator"


def test_incident_close_timestamp_uses_injected_clock():
    now = [0.0]
    registry = IncidentRegistry(clock=lambda: now[0])
    incident = registry.open(IncidentSeverity.ERROR, "x")
    registry.acknowledge(incident.incident_id, "operator")
    now[0] = 5
    closed = registry.close(incident.incident_id)
    assert closed.closed_at == 5


def test_service_state_maintenance_roundtrip():
    state = ShellServiceState()
    state.transition(ShellServicePhase.STARTING)
    state.transition(ShellServicePhase.READY)
    state.transition(ShellServicePhase.MAINTENANCE)
    state.transition(ShellServicePhase.READY)
    assert state.phase is ShellServicePhase.READY


def test_service_state_draining_can_fail():
    state = ShellServiceState()
    state.transition(ShellServicePhase.STARTING)
    state.transition(ShellServicePhase.READY)
    state.transition(ShellServicePhase.DRAINING)
    state.transition(ShellServicePhase.FAILED)
    assert state.phase is ShellServicePhase.FAILED


def test_service_state_failed_can_stop():
    state = ShellServiceState()
    state.transition(ShellServicePhase.FAILED)
    state.transition(ShellServicePhase.STOPPING)
    state.transition(ShellServicePhase.STOPPED)
    assert state.phase is ShellServicePhase.STOPPED


def test_service_state_stopped_has_no_outgoing_transition():
    state = ShellServiceState()
    state.transition(ShellServicePhase.FAILED)
    state.transition(ShellServicePhase.STOPPED)
    with pytest.raises(RuntimeError):
        state.transition(ShellServicePhase.STARTING)


def test_incident_new_record_is_open_and_unacknowledged():
    registry = IncidentRegistry()
    incident = registry.open(IncidentSeverity.WARNING, "fresh")
    assert incident.state is IncidentState.OPEN
    assert incident.acknowledged_by == ""
    assert incident.closed_at is None


def test_namespace_default_enabled_state_allows_normal_checks():
    namespace = ShellNamespace("default")
    assert namespace.enabled
    assert namespace.allows_principal("principal")
    assert namespace.allows_command("python")
