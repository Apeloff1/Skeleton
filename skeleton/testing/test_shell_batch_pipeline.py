from pathlib import Path
import sys
import threading
import pytest

from skeleton.shells.batch import BatchExecutor, BatchItem
from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.executor import ExecutionOutcome, ShellExecutor
from skeleton.shells.pipeline import PipelineExecutor, PipelineSpec, PipelineStep, StepState, pipeline_from_commands
from skeleton.shells.runner import ShellCommand, ShellPolicy, ShellResult


class RoutingRunner:
    def __init__(self, tmp_path):
        self.policy = ShellPolicy(executables={"python": str(Path(sys.executable).resolve())}, cwd_roots=(tmp_path,))
        self.lock = threading.Lock()
        self.calls = []

    def run(self, command):
        with self.lock:
            self.calls.append(command.args)
        fail = "fail" in command.args
        return ShellResult(command.command, 1 if fail else 0, b"", b"", accepted=not fail)


def grant():
    return CapabilityGrant(frozenset({ShellCapability.EXECUTE, ShellCapability.PARALLEL, ShellCapability.PIPELINE}))


def test_batch_executes_items_and_preserves_ids(tmp_path):
    runner = RoutingRunner(tmp_path)
    executor = ShellExecutor(runner, grant=grant())
    result = BatchExecutor(executor, max_workers=2).execute(
        [
            BatchItem("a", ShellCommand("python", ("a",), cwd=tmp_path)),
            BatchItem("b", ShellCommand("python", ("b",), cwd=tmp_path)),
        ]
    )
    assert result.ok
    assert set(result.outcomes) == {"a", "b"}


def test_batch_requires_parallel_capability(tmp_path):
    runner = RoutingRunner(tmp_path)
    executor = ShellExecutor(runner)
    with pytest.raises(Exception):
        BatchExecutor(executor).execute([BatchItem("a", ShellCommand("python", cwd=tmp_path))])


def test_batch_rejects_duplicate_ids(tmp_path):
    executor = ShellExecutor(RoutingRunner(tmp_path), grant=grant())
    items = [BatchItem("same", ShellCommand("python", cwd=tmp_path)), BatchItem("same", ShellCommand("python", cwd=tmp_path))]
    with pytest.raises(ValueError):
        BatchExecutor(executor).execute(items)


def test_batch_bounds_item_count(tmp_path):
    executor = ShellExecutor(RoutingRunner(tmp_path), grant=grant())
    with pytest.raises(ValueError):
        BatchExecutor(executor, max_items=1).execute(
            [BatchItem("a", ShellCommand("python", cwd=tmp_path)), BatchItem("b", ShellCommand("python", cwd=tmp_path))]
        )


def test_batch_reports_failed_outcome_without_exception(tmp_path):
    executor = ShellExecutor(RoutingRunner(tmp_path), grant=grant())
    result = BatchExecutor(executor).execute([BatchItem("bad", ShellCommand("python", ("fail",), cwd=tmp_path))])
    assert not result.ok
    assert not result.outcomes["bad"].ok


def test_pipeline_spec_rejects_unknown_dependencies(tmp_path):
    with pytest.raises(ValueError):
        PipelineSpec("p", (PipelineStep("a", ShellCommand("python", cwd=tmp_path), depends_on=frozenset({"missing"})),))


def test_pipeline_spec_rejects_cycles(tmp_path):
    with pytest.raises(ValueError):
        PipelineSpec(
            "p",
            (
                PipelineStep("a", ShellCommand("python", cwd=tmp_path), depends_on=frozenset({"b"})),
                PipelineStep("b", ShellCommand("python", cwd=tmp_path), depends_on=frozenset({"a"})),
            ),
        )


def test_pipeline_topological_order_is_deterministic(tmp_path):
    spec = PipelineSpec(
        "p",
        (
            PipelineStep("c", ShellCommand("python", cwd=tmp_path), depends_on=frozenset({"a", "b"})),
            PipelineStep("b", ShellCommand("python", cwd=tmp_path)),
            PipelineStep("a", ShellCommand("python", cwd=tmp_path)),
        ),
    )
    assert spec.topological_order() == ("a", "b", "c")


def test_pipeline_runs_dependencies_before_dependents(tmp_path):
    runner = RoutingRunner(tmp_path)
    executor = ShellExecutor(runner, grant=grant())
    spec = PipelineSpec(
        "p",
        (
            PipelineStep("second", ShellCommand("python", ("second",), cwd=tmp_path), depends_on=frozenset({"first"})),
            PipelineStep("first", ShellCommand("python", ("first",), cwd=tmp_path)),
        ),
    )
    result = PipelineExecutor(executor).execute(spec)
    assert result.ok
    assert runner.calls == [("first",), ("second",)]


def test_pipeline_stops_after_hard_failure(tmp_path):
    runner = RoutingRunner(tmp_path)
    executor = ShellExecutor(runner, grant=grant())
    spec = PipelineSpec(
        "p",
        (
            PipelineStep("a", ShellCommand("python", ("fail",), cwd=tmp_path)),
            PipelineStep("b", ShellCommand("python", ("b",), cwd=tmp_path)),
        ),
    )
    result = PipelineExecutor(executor).execute(spec, stop_on_failure=True)
    assert result.steps["a"].state is StepState.FAILED
    assert result.steps["b"].state is StepState.SKIPPED
    assert len(runner.calls) == 1


def test_pipeline_marks_dependency_blocked_without_global_stop(tmp_path):
    runner = RoutingRunner(tmp_path)
    executor = ShellExecutor(runner, grant=grant())
    spec = PipelineSpec(
        "p",
        (
            PipelineStep("a", ShellCommand("python", ("fail",), cwd=tmp_path), continue_on_failure=True),
            PipelineStep("b", ShellCommand("python", ("b",), cwd=tmp_path), depends_on=frozenset({"a"})),
            PipelineStep("c", ShellCommand("python", ("c",), cwd=tmp_path)),
        ),
    )
    result = PipelineExecutor(executor).execute(spec, stop_on_failure=True)
    assert result.steps["b"].state is StepState.BLOCKED
    assert result.steps["c"].state is StepState.SUCCEEDED


def test_pipeline_from_commands_builds_linear_chain(tmp_path):
    spec = pipeline_from_commands(
        "linear",
        [ShellCommand("python", ("a",), cwd=tmp_path), ShellCommand("python", ("b",), cwd=tmp_path)],
    )
    assert spec.steps[0].depends_on == frozenset()
    assert spec.steps[1].depends_on == frozenset({"step-001"})
