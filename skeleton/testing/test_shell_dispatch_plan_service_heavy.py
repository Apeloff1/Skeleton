"""Integration tests for dispatch, plans, and the shell service facade."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.cancellation import CancellationReason
from skeleton.shells.deadlines import DeadlineExceeded
from skeleton.shells.dispatch import ShellDispatcher
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.plan_executor import ShellPlanExecutor, StepState
from skeleton.shells.runner import ShellCommand, ShellPolicy, ShellRunner
from skeleton.shells.service_state import ShellServicePhase
from skeleton.shells.shell_service import ShellService


def make_policy(tmp_path, **changes):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    values = dict(
        executables={"python": sys.executable},
        cwd_roots=(root,),
        default_timeout=2.0,
        max_timeout=5.0,
        max_output_bytes=4096,
        max_input_bytes=4096,
        max_env_bytes=4096,
        max_args=32,
        max_arg_bytes=4096,
    )
    values.update(changes)
    return ShellPolicy(**values)


def make_executor(tmp_path, **changes):
    runner = ShellRunner(make_policy(tmp_path, **changes))
    return ShellExecutor(runner)


def context(value="c1"):
    return ExecutionContext(value, principal="tester", request_id="r1")


def test_execution_context_requires_id():
    with pytest.raises(ValueError):
        ExecutionContext("")


def test_execution_context_child_links_parent():
    parent = context("root")
    child = parent.child("root:child")
    assert child.parent_correlation_id == "root"
    assert child.correlation_id == "root:child"
    assert child.principal == parent.principal


def test_execution_context_fingerprint_stable():
    first = ExecutionContext("c", principal="p", tags=frozenset({"a", "b"}))
    second = ExecutionContext("c", principal="p", tags=frozenset({"b", "a"}))
    assert first.fingerprint == second.fingerprint


def test_dispatch_executes_successfully(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    result = dispatcher.dispatch(
        ShellCommand("python", ("-c", "print('ok')")),
        context=context(),
    )
    assert result.ok
    assert result.outcome.result.stdout.strip() == b"ok"
    assert result.permit_id > 0
    assert result.lease_id


def test_dispatch_releases_concurrency_after_success(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    dispatcher.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=context(),
    )
    assert dispatcher.concurrency.snapshot().used == 0
    assert dispatcher.concurrency.snapshot().permits == 0


def test_dispatch_releases_lease_after_success(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    dispatcher.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=context(),
        lease_key="key",
    )
    assert dispatcher.leases.snapshot() == ()


def test_dispatch_records_budget(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    dispatcher.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=context(),
    )
    usage = dispatcher.budgets.snapshot()["python"]
    assert usage.starts == 1
    assert usage.runtime_ms >= 0
    assert usage.output_bytes > 0


def test_dispatch_emits_lifecycle_events(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    dispatcher.dispatch(
        ShellCommand("python", ("-c", "print(1)")),
        context=context(),
    )
    assert [event.kind for event in dispatcher.events.query()] == [
        "shell.dispatch.admitted",
        "shell.dispatch.started",
        "shell.dispatch.completed",
    ]


def test_dispatch_cancelled_before_admission(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    token = dispatcher.events  # keep dispatcher referenced for branch parity
    from skeleton.shells.cancellation import CancellationToken

    cancellation = CancellationToken()
    cancellation.cancel(CancellationReason.USER)
    with pytest.raises(Exception):
        dispatcher.dispatch(
            ShellCommand("python", ("-c", "print(1)")),
            context=context(),
            cancellation=cancellation,
        )
    assert dispatcher.concurrency.snapshot().used == 0


def test_dispatch_deadline_clamps_timeout(tmp_path):
    now = [0.0]
    executor = make_executor(tmp_path)
    dispatcher = ShellDispatcher(executor, clock=lambda: now[0])
    dispatcher.deadline_clock = type(
        "Clock",
        (),
        {
            "clamp_timeout": lambda self, deadline, requested: min(requested, 0.25),
        },
    )()
    result = dispatcher.dispatch(
        ShellCommand("python", ("-c", "print(1)"), timeout=1.0),
        context=context(),
        deadline=object(),
    )
    assert result.ok


def test_dispatch_failure_records_error_event(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    result = dispatcher.dispatch(
        ShellCommand("python", ("-c", "raise SystemExit(2)")),
        context=context(),
    )
    assert not result.ok
    assert dispatcher.events.query(kind="shell.dispatch.completed")


def test_plan_executor_runs_dependency_order(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    executor = ShellPlanExecutor(dispatcher)
    plan = ExecutionPlan(
        "p",
        (
            PlanStep("a", ShellCommand("python", ("-c", "print('a')"))),
            PlanStep(
                "b",
                ShellCommand("python", ("-c", "print('b')")),
                frozenset({"a"}),
            ),
        ),
    )
    report = executor.execute(plan, context=context("plan"))
    assert report.ok
    assert [step.step_id for step in report.steps] == ["a", "b"]
    assert all(step.state is StepState.SUCCEEDED for step in report.steps)


def test_plan_executor_skips_failed_dependency(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    executor = ShellPlanExecutor(dispatcher)
    plan = ExecutionPlan(
        "p",
        (
            PlanStep("a", ShellCommand("python", ("-c", "raise SystemExit(3)"))),
            PlanStep(
                "b",
                ShellCommand("python", ("-c", "print('never')")),
                frozenset({"a"}),
            ),
        ),
    )
    report = executor.execute(plan, context=context("plan"))
    assert report.failed == 1
    assert report.skipped == 1
    assert report.steps[1].state is StepState.SKIPPED


def test_plan_continue_on_failure_allows_step(tmp_path):
    dispatcher = ShellDispatcher(make_executor(tmp_path))
    executor = ShellPlanExecutor(dispatcher)
    plan = ExecutionPlan(
        "p",
        (
            PlanStep("a", ShellCommand("python", ("-c", "raise SystemExit(3)"))),
            PlanStep(
                "b",
                ShellCommand("python", ("-c", "print('runs')")),
                frozenset({"a"}),
                continue_on_failure=True,
            ),
        ),
    )
    report = executor.execute(plan, context=context("plan"))
    assert report.steps[0].state is StepState.FAILED
    assert report.steps[1].state is StepState.SUCCEEDED


def test_plan_cancelled_marks_remaining_steps(tmp_path):
    from skeleton.shells.cancellation import CancellationToken

    dispatcher = ShellDispatcher(make_executor(tmp_path))
    executor = ShellPlanExecutor(dispatcher)
    plan = ExecutionPlan(
        "p",
        (
            PlanStep("a", ShellCommand("python", ("-c", "print(1)"))),
            PlanStep("b", ShellCommand("python", ("-c", "print(2)"))),
        ),
    )
    token = CancellationToken()
    token.cancel()
    report = executor.execute(plan, context=context("plan"), cancellation=token)
    assert all(step.state is StepState.CANCELLED for step in report.steps)


def test_shell_service_start_ready(tmp_path):
    service = ShellService(make_executor(tmp_path))
    service.start()
    assert service.state.phase is ShellServicePhase.READY


def test_shell_service_dispatch_requires_ready(tmp_path):
    service = ShellService(make_executor(tmp_path))
    with pytest.raises(RuntimeError):
        service.dispatch(
            ShellCommand("python", ("-c", "print(1)")),
            context=context(),
        )


def test_shell_service_dispatch_and_receipt_chain(tmp_path):
    service = ShellService(make_executor(tmp_path))
    service.start()
    result = service.dispatch(
        ShellCommand("python", ("-c", "print('service')")),
        context=context(),
    )
    assert result.ok
    assert len(service.receipts.snapshot()) == 1
    assert service.receipts.verify()


def test_shell_service_plan_execution(tmp_path):
    service = ShellService(make_executor(tmp_path))
    service.start()
    plan = ExecutionPlan(
        "p",
        (
            PlanStep("a", ShellCommand("python", ("-c", "print(1)"))),
            PlanStep("b", ShellCommand("python", ("-c", "print(2)"))),
        ),
    )
    report = service.execute_plan(plan, context=context("plan"))
    assert report.ok
    assert len(service.receipts.snapshot()) == 2


def test_shell_service_status_has_snapshot_digest(tmp_path):
    service = ShellService(make_executor(tmp_path))
    service.start()
    status = service.status()
    assert status.phase is ShellServicePhase.READY
    assert status.snapshot_digest


def test_shell_service_open_incident(tmp_path):
    service = ShellService(make_executor(tmp_path))
    incident = service.open_incident(
        "test",
        correlation_id="c",
        command="python",
        evidence={"x": 1},
    )
    assert incident.command == "python"
    assert service.incidents.get(incident.incident_id) == incident


def test_shell_service_failed_dispatch_records_failure(tmp_path):
    service = ShellService(make_executor(tmp_path))
    service.start()
    service.cancellations.create("cancel")
    service.cancellations.cancel("cancel")
    token = service.cancellations.require("cancel")
    with pytest.raises(Exception):
        service.dispatch(
            ShellCommand("python", ("-c", "print(1)")),
            context=context(),
            cancellation=token,
        )
    assert service.failures.counts()["internal"] == 1
