"""Additional end-to-end service integration and evidence tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.failure_ledger import ShellFailureKind
from skeleton.shells.incident import IncidentSeverity, IncidentState
from skeleton.shells.runner import ShellCommand, ShellPolicy, ShellRunner
from skeleton.shells.service_state import ShellServicePhase
from skeleton.shells.shell_service import ShellService


def service(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    policy = ShellPolicy(
        executables={"python": sys.executable},
        cwd_roots=(root,),
        default_timeout=2,
        max_timeout=5,
        max_output_bytes=4096,
        max_input_bytes=4096,
        max_env_bytes=4096,
        max_args=32,
        max_arg_bytes=4096,
    )
    executor = ShellExecutor(ShellRunner(policy))
    result = ShellService(executor, concurrency_capacity=2)
    result.start()
    return result


def ctx(value):
    return ExecutionContext(value, principal="integration")


def test_service_multiple_dispatches_chain_receipts(tmp_path):
    shell = service(tmp_path)
    for index in range(3):
        result = shell.dispatch(
            ShellCommand("python", ("-c", f"print({index})")),
            context=ctx(f"c{index}"),
        )
        assert result.ok
    assert len(shell.receipts.snapshot()) == 3
    assert shell.receipts.verify()


def test_service_failed_exit_is_receipted_not_exception(tmp_path):
    shell = service(tmp_path)
    result = shell.dispatch(
        ShellCommand("python", ("-c", "raise SystemExit(7)")),
        context=ctx("fail"),
    )
    assert not result.ok
    assert len(shell.receipts.snapshot()) == 1
    assert shell.receipts.snapshot()[0].receipt.returncode == 7


def test_service_status_after_execution(tmp_path):
    shell = service(tmp_path)
    shell.dispatch(
        ShellCommand("python", ("-c", "print('x')")),
        context=ctx("c"),
    )
    status = shell.status()
    assert status.phase is ShellServicePhase.READY
    assert status.diagnostics["ok"] is True
    assert status.reconcile["ok"] is True


def test_service_snapshot_changes_after_execution(tmp_path):
    shell = service(tmp_path)
    before = shell.snapshot().digest
    shell.dispatch(
        ShellCommand("python", ("-c", "print('x')")),
        context=ctx("c"),
    )
    after = shell.snapshot().digest
    assert before != after


def test_service_plan_failure_skips_dependency(tmp_path):
    shell = service(tmp_path)
    plan = ExecutionPlan(
        "p",
        (
            PlanStep("a", ShellCommand("python", ("-c", "raise SystemExit(2)"))),
            PlanStep("b", ShellCommand("python", ("-c", "print('no')")), frozenset({"a"})),
            PlanStep("c", ShellCommand("python", ("-c", "print('independent')"))),
        ),
    )
    report = shell.execute_plan(plan, context=ctx("plan"))
    states = {step.step_id: step.state.value for step in report.steps}
    assert states["a"] == "failed"
    assert states["b"] == "skipped"
    assert states["c"] == "succeeded"


def test_service_incident_lifecycle(tmp_path):
    shell = service(tmp_path)
    incident = shell.open_incident(
        "failure",
        severity=IncidentSeverity.ERROR,
        correlation_id="c",
        command="python",
        evidence={"receipt_root": shell.receipts.root_hash()},
    )
    shell.incidents.acknowledge(incident.incident_id, "operator")
    shell.incidents.mitigate(incident.incident_id)
    closed = shell.incidents.close(incident.incident_id)
    assert closed.state is IncidentState.CLOSED


def test_service_failure_exception_records_ledger(tmp_path):
    shell = service(tmp_path)
    token = shell.cancellations.create("x")
    token.cancel()
    with pytest.raises(Exception):
        shell.dispatch(
            ShellCommand("python", ("-c", "print(1)")),
            context=ctx("cancelled"),
            cancellation=token,
        )
    assert shell.failures.query(kind=ShellFailureKind.INTERNAL)


def test_service_state_can_enter_maintenance(tmp_path):
    shell = service(tmp_path)
    shell.state.transition(ShellServicePhase.MAINTENANCE, reason="upgrade")
    assert shell.state.phase is ShellServicePhase.MAINTENANCE
    with pytest.raises(RuntimeError):
        shell.dispatch(
            ShellCommand("python", ("-c", "print(1)")),
            context=ctx("c"),
        )


def test_service_state_can_drain_and_resume(tmp_path):
    shell = service(tmp_path)
    shell.state.transition(ShellServicePhase.DRAINING)
    assert not shell.state.ready()
    shell.state.transition(ShellServicePhase.READY)
    result = shell.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=ctx("c"),
    )
    assert result.ok


def test_service_stop_transition_blocks_dispatch(tmp_path):
    shell = service(tmp_path)
    shell.state.transition(ShellServicePhase.STOPPING)
    shell.state.transition(ShellServicePhase.STOPPED)
    with pytest.raises(RuntimeError):
        shell.dispatch(
            ShellCommand("python", ("-c", "print(1)")),
            context=ctx("c"),
        )
