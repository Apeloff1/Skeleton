"""Service-state, reconciliation, and shell snapshot tests."""

from __future__ import annotations

from dataclasses import replace
import sys

import pytest

from skeleton.shells.cancellation import CancellationRegistry
from skeleton.shells.command_budget import CommandBudgetPolicy, CommandBudgets
from skeleton.shells.concurrency import WeightedConcurrency
from skeleton.shells.failure_ledger import ShellFailureKind, ShellFailureLedger
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.reconciler import ReconcileSeverity, ShellReconciler
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.service_state import ShellServicePhase, ShellServiceState
from skeleton.shells.shell_diagnostics import ShellDiagnostics
from skeleton.shells.shell_events import ShellEvents
from skeleton.shells.shell_snapshot import ShellSnapshotter
from skeleton.shells.status import ShellPlaneStatus


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_service_state_rejects_invalid_history_bound(value):
    with pytest.raises(ValueError):
        ShellServiceState(max_history=value)


@pytest.mark.parametrize("reason", ["bad\x00reason", 123])
def test_service_state_rejects_invalid_transition_reason(reason):
    state = ShellServiceState()
    with pytest.raises(ValueError):
        state.transition(ShellServicePhase.STARTING, reason=reason)


def test_service_state_happy_path():
    state = ShellServiceState()
    state.transition(ShellServicePhase.STARTING)
    state.transition(ShellServicePhase.READY)
    state.transition(ShellServicePhase.DRAINING)
    state.transition(ShellServicePhase.READY)
    state.transition(ShellServicePhase.STOPPING)
    state.transition(ShellServicePhase.STOPPED)
    assert state.phase is ShellServicePhase.STOPPED


def test_service_state_invalid_jump():
    state = ShellServiceState()
    with pytest.raises(RuntimeError):
        state.transition(ShellServicePhase.READY)


def test_service_state_failure_path():
    state = ShellServiceState()
    transition = state.transition(ShellServicePhase.FAILED, reason="bootstrap")
    assert transition.current is ShellServicePhase.FAILED
    state.transition(ShellServicePhase.STOPPING)
    state.transition(ShellServicePhase.STOPPED)


def test_service_state_history_bound():
    state = ShellServiceState(max_history=2)
    state.transition(ShellServicePhase.STARTING)
    state.transition(ShellServicePhase.READY)
    state.transition(ShellServicePhase.DRAINING)
    assert len(state.history()) == 2


def test_reconciler_clean_state():
    reconciler = ShellReconciler(
        receipts=ReceiptChain(),
        events=ShellEvents(),
        failures=ShellFailureLedger(),
        concurrency=WeightedConcurrency(2),
        budgets=CommandBudgets(),
    )
    assert reconciler.reconcile().ok


def test_reconciler_detects_receipt_tamper():
    from skeleton.shells.receipts import ExecutionReceipt

    chain = ReceiptChain()
    receipt = ExecutionReceipt.now_failure(
        command="python",
        correlation_id="c",
        fingerprint="fp",
    )
    chain.append(receipt)
    item = chain._items[0]
    chain._items[0] = replace(item, receipt_hash="0" * 64)
    report = ShellReconciler(receipts=chain).reconcile()
    assert not report.ok
    assert any(item.code == "receipt_chain_invalid" for item in report.findings)


def test_reconciler_reports_inflight_dispatch():
    events = ShellEvents()
    events.emit("shell.dispatch.started")
    report = ShellReconciler(events=events).reconcile()
    assert report.ok
    assert any(item.code == "dispatches_inflight" for item in report.findings)


def test_reconciler_detects_terminal_without_start():
    events = ShellEvents()
    events.emit("shell.dispatch.completed")
    report = ShellReconciler(events=events).reconcile()
    assert not report.ok
    assert any(item.code == "event_order_invalid" for item in report.findings)


def test_reconciler_reports_internal_failures():
    failures = ShellFailureLedger()
    failures.record("python", ShellFailureKind.INTERNAL)
    report = ShellReconciler(failures=failures).reconcile()
    assert any(item.code == "internal_failures" for item in report.findings)


def test_reconciler_reports_budget_exhaustion():
    budgets = CommandBudgets(CommandBudgetPolicy(max_starts=1))
    budgets.reserve_start("python")
    report = ShellReconciler(budgets=budgets).reconcile()
    assert any(item.code == "budgets_exhausted" for item in report.findings)


def make_runner(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    policy = ShellPolicy(
        executables={"python": sys.executable},
        cwd_roots=(root,),
        default_timeout=5,
        max_timeout=10,
        max_output_bytes=1024,
        max_input_bytes=1024,
        max_env_bytes=1024,
        max_args=16,
        max_arg_bytes=1024,
    )
    return ShellRunner(policy)


def test_shell_diagnostics_healthy(tmp_path):
    diagnostics = ShellDiagnostics(
        runner=make_runner(tmp_path),
        receipts=ReceiptChain(),
        cancellations=CancellationRegistry(),
        concurrency=WeightedConcurrency(2),
        budgets=CommandBudgets(),
    )
    assert diagnostics.inspect().ok


def test_shell_diagnostics_saturated_concurrency_warns(tmp_path):
    limiter = WeightedConcurrency(1)
    permit = limiter.acquire()
    diagnostics = ShellDiagnostics(
        runner=make_runner(tmp_path),
        concurrency=limiter,
    )
    report = diagnostics.inspect()
    assert report.ok
    assert any(item.code == "concurrency_saturated" for item in report.findings)
    limiter.release(permit)


def test_shell_diagnostics_cancelled_token_info(tmp_path):
    cancellations = CancellationRegistry()
    cancellations.create("x")
    cancellations.cancel("x")
    report = ShellDiagnostics(
        runner=make_runner(tmp_path),
        cancellations=cancellations,
    ).inspect()
    assert any(item.code == "cancelled_operations" for item in report.findings)


def test_shell_snapshot_contains_all_sections(tmp_path):
    runner = make_runner(tmp_path)
    diagnostics = ShellDiagnostics(runner=runner)
    cancellations = CancellationRegistry()
    concurrency = WeightedConcurrency(2)
    budgets = CommandBudgets()

    status = ShellPlaneStatus(
        healthy=True,
        policy_health={},
        metrics={},
        circuits={},
        receipt_chain_valid=True,
        receipt_root="root",
    )

    snapshotter = ShellSnapshotter(
        status_provider=lambda: status,
        diagnostics=diagnostics,
        cancellations=cancellations,
        concurrency=concurrency,
        budgets=budgets,
    )
    snapshot = snapshotter.capture()
    payload = snapshot.to_dict()
    assert payload["schema_version"] == 1
    assert "status" in payload
    assert "diagnostics" in payload
    assert "cancellations" in payload
    assert "concurrency" in payload
    assert "budgets" in payload
    assert snapshot.digest


def test_shell_snapshot_digest_changes_with_state(tmp_path):
    runner = make_runner(tmp_path)
    diagnostics = ShellDiagnostics(runner=runner)
    cancellations = CancellationRegistry()
    concurrency = WeightedConcurrency(2)
    budgets = CommandBudgets()
    status = ShellPlaneStatus(True, {}, {}, {}, True, "root")

    snapshotter = ShellSnapshotter(
        status_provider=lambda: status,
        diagnostics=diagnostics,
        cancellations=cancellations,
        concurrency=concurrency,
        budgets=budgets,
    )
    first = snapshotter.capture().digest
    cancellations.create("x")
    second = snapshotter.capture().digest
    assert first != second
