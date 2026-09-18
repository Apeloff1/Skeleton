"""Service and policy invariants that must remain stable under future expansion."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.command_budget import CommandBudgetPolicy
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.runner import ShellCommand, ShellPolicy, ShellRunner
from skeleton.shells.service_state import ShellServicePhase
from skeleton.shells.shell_service import ShellService


def shell(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    runner = ShellRunner(
        ShellPolicy(
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
    )
    return ShellService(ShellExecutor(runner), concurrency_capacity=1)


def test_service_constructor_does_not_start(tmp_path):
    service = shell(tmp_path)
    assert service.state.phase is ShellServicePhase.NEW
    assert service.receipts.snapshot() == ()


def test_service_start_is_effectively_idempotent_when_ready(tmp_path):
    service = shell(tmp_path)
    service.start()
    service.start()
    assert service.state.phase is ShellServicePhase.READY


def test_service_receipt_chain_is_executor_chain(tmp_path):
    service = shell(tmp_path)
    assert service.executor.receipt_chain is service.receipts


def test_service_command_budget_can_deny_future_dispatch(tmp_path):
    service = shell(tmp_path)
    service.start()
    service.budgets.set_policy("python", CommandBudgetPolicy(max_starts=1))
    first = service.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=ExecutionContext("a", principal="p"),
    )
    assert first.ok
    with pytest.raises(RuntimeError):
        service.dispatch(
            ShellCommand("python", ("-c", "print(2)")),
            context=ExecutionContext("b", principal="p"),
        )


def test_service_concurrency_returns_to_zero_after_dispatch(tmp_path):
    service = shell(tmp_path)
    service.start()
    service.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=ExecutionContext("a", principal="p"),
    )
    assert service.concurrency.snapshot().used == 0


def test_service_dispatch_records_events(tmp_path):
    service = shell(tmp_path)
    service.start()
    service.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=ExecutionContext("a", principal="p"),
    )
    kinds = [item.kind for item in service.events.query()]
    assert "shell.dispatch.admitted" in kinds
    assert "shell.dispatch.started" in kinds
    assert "shell.dispatch.completed" in kinds


def test_service_receipt_root_changes_after_execution(tmp_path):
    service = shell(tmp_path)
    service.start()
    before = service.receipts.root_hash()
    service.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=ExecutionContext("a", principal="p"),
    )
    assert service.receipts.root_hash() != before


def test_service_reconcile_after_normal_execution_is_clean(tmp_path):
    service = shell(tmp_path)
    service.start()
    service.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=ExecutionContext("a", principal="p"),
    )
    assert service.reconcile().ok


def test_service_stopped_state_is_terminal(tmp_path):
    service = shell(tmp_path)
    service.start()
    service.state.transition(ShellServicePhase.STOPPING)
    service.state.transition(ShellServicePhase.STOPPED)
    with pytest.raises(RuntimeError):
        service.state.transition(ShellServicePhase.STARTING)
