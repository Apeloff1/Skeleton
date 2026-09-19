from pathlib import Path
import sys
import pytest

from skeleton.shells.arguments import ArgumentPolicy, ArgumentPolicySet, OptionRule
from skeleton.shells.audit import MemoryAuditSink
from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.circuit import CircuitPolicy, CircuitRegistry
from skeleton.shells.environment import EnvironmentPolicy, EnvironmentValueRule
from skeleton.shells.errors import CapabilityDenied, SessionBudgetExhausted
from skeleton.shells.executor import ExecutorConfig, ShellExecutor
from skeleton.shells.hooks import HookRegistry
from skeleton.shells.limits import ResourceLimits
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand, ShellPolicy, ShellResult
from skeleton.shells.session import ShellSession
from skeleton.shells.telemetry import ShellTelemetry
from skeleton.shells.workspace import WorkspacePolicy


class FakeRunner:
    def __init__(self, tmp_path: Path, results):
        self.policy = ShellPolicy(executables={"python": str(Path(sys.executable).resolve())}, cwd_roots=(tmp_path,))
        self.results = list(results)
        self.commands = []

    def run(self, command):
        self.commands.append(command)
        if not self.results:
            raise AssertionError("fake runner exhausted")
        return self.results.pop(0)


def ok_result(stdout=b"ok"):
    return ShellResult("python", 0, stdout, b"", accepted=True)


def fail_result(code=1):
    return ShellResult("python", code, b"", b"failed", accepted=False)


def full_grant():
    return CapabilityGrant(
        frozenset(
            {
                ShellCapability.EXECUTE,
                ShellCapability.CUSTOM_ENV,
                ShellCapability.STDIN,
                ShellCapability.NONZERO_SUCCESS,
                ShellCapability.LONG_RUNNING,
                ShellCapability.LARGE_OUTPUT,
                ShellCapability.RETRY,
                ShellCapability.PARALLEL,
                ShellCapability.PIPELINE,
            }
        ),
        principal="test",
    )


def test_executor_records_audit_telemetry_and_receipt(tmp_path):
    audit = MemoryAuditSink()
    telemetry = ShellTelemetry()
    chain = ReceiptChain()
    runner = FakeRunner(tmp_path, [ok_result(b"hello")])
    executor = ShellExecutor(runner, audit=audit, telemetry=telemetry, receipts=chain)
    outcome = executor.execute(ShellCommand("python", cwd=tmp_path))
    assert outcome.ok
    assert len(outcome.receipts) == 1
    assert chain.verify()
    assert telemetry.snapshot()["python"].completed == 1
    kinds = [event.kind for event in audit.snapshot()]
    assert kinds == ["shell.execution.started", "shell.execution.completed"]


def test_executor_audit_does_not_store_raw_arguments(tmp_path):
    secret = "super-private-argument"
    audit = MemoryAuditSink()
    runner = FakeRunner(tmp_path, [ok_result()])
    executor = ShellExecutor(runner, audit=audit)
    executor.execute(ShellCommand("python", (secret,), cwd=tmp_path))
    serialized = repr([event.to_dict() for event in audit.snapshot()])
    assert secret not in serialized
    assert "args_digest" in serialized


def test_executor_rejects_custom_env_without_capability(tmp_path):
    runner = FakeRunner(tmp_path, [ok_result()])
    executor = ShellExecutor(runner)
    with pytest.raises(CapabilityDenied):
        executor.execute(ShellCommand("python", cwd=tmp_path, env={"MODE": "test"}))
    assert runner.commands == []


def test_executor_rejects_stdin_without_capability(tmp_path):
    runner = FakeRunner(tmp_path, [ok_result()])
    executor = ShellExecutor(runner)
    with pytest.raises(CapabilityDenied):
        executor.execute(ShellCommand("python", cwd=tmp_path, stdin=b"x"))


def test_executor_rejects_nonzero_success_without_capability(tmp_path):
    runner = FakeRunner(tmp_path, [ok_result()])
    executor = ShellExecutor(runner)
    with pytest.raises(CapabilityDenied):
        executor.execute(ShellCommand("python", cwd=tmp_path, allowed_returncodes=frozenset({0, 2})))


def test_executor_applies_argument_policy_before_run(tmp_path):
    policies = ArgumentPolicySet({"python": ArgumentPolicy(options={"-q": OptionRule("-q")})})
    runner = FakeRunner(tmp_path, [ok_result()])
    executor = ShellExecutor(runner, arguments=policies)
    with pytest.raises(Exception):
        executor.execute(ShellCommand("python", ("--bad",), cwd=tmp_path))
    assert runner.commands == []


def test_executor_applies_environment_policy(tmp_path):
    env = EnvironmentPolicy(rules={"MODE": EnvironmentValueRule(choices=frozenset({"test"}))})
    runner = FakeRunner(tmp_path, [ok_result()])
    executor = ShellExecutor(runner, grant=full_grant(), environment=env)
    executor.execute(ShellCommand("python", cwd=tmp_path, env={"MODE": "test"}))
    assert dict(runner.commands[0].env) == {"MODE": "test"}


def test_executor_applies_workspace_policy(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    runner = FakeRunner(allowed, [ok_result()])
    executor = ShellExecutor(runner, workspace=WorkspacePolicy((allowed,)))
    with pytest.raises(Exception):
        executor.execute(ShellCommand("python", cwd=outside))
    assert runner.commands == []


def test_executor_retries_selected_failure_and_then_succeeds(tmp_path):
    sleeps = []
    runner = FakeRunner(tmp_path, [fail_result(75), ok_result()])
    telemetry = ShellTelemetry()
    executor = ShellExecutor(runner, grant=full_grant(), telemetry=telemetry, sleeper=sleeps.append)
    outcome = executor.execute(
        ShellCommand("python", cwd=tmp_path),
        retry=RetryPolicy(max_attempts=2, retry_returncodes=frozenset({75}), initial_delay_seconds=0.25),
    )
    assert outcome.ok
    assert len(outcome.receipts) == 2
    assert sleeps == [0.25]
    assert telemetry.snapshot()["python"].retries == 1


def test_executor_does_not_retry_nonretryable_failure(tmp_path):
    runner = FakeRunner(tmp_path, [fail_result(2)])
    executor = ShellExecutor(runner, grant=full_grant())
    outcome = executor.execute(
        ShellCommand("python", cwd=tmp_path),
        retry=RetryPolicy(max_attempts=3, retry_returncodes=frozenset({75})),
    )
    assert not outcome.ok
    assert len(outcome.receipts) == 1


def test_executor_session_tracks_each_attempt(tmp_path):
    runner = FakeRunner(tmp_path, [fail_result(75), ok_result()])
    session = ShellSession(ResourceLimits(max_commands=3, max_retries=2), principal="worker")
    executor = ShellExecutor(runner, grant=full_grant())
    outcome = executor.execute(
        ShellCommand("python", cwd=tmp_path),
        retry=RetryPolicy(max_attempts=2, retry_returncodes=frozenset({75})),
        session=session,
    )
    assert outcome.ok
    snapshot = session.snapshot()
    assert snapshot.usage.commands == 2
    assert snapshot.usage.retries == 1
    assert snapshot.receipt_count == 2


def test_executor_session_command_budget_stops_retry(tmp_path):
    runner = FakeRunner(tmp_path, [fail_result(75), ok_result()])
    session = ShellSession(ResourceLimits(max_commands=1, max_retries=2))
    executor = ShellExecutor(runner, grant=full_grant())
    with pytest.raises(SessionBudgetExhausted):
        executor.execute(
            ShellCommand("python", cwd=tmp_path),
            retry=RetryPolicy(max_attempts=2, retry_returncodes=frozenset({75})),
            session=session,
        )
    assert len(runner.commands) == 1


def test_executor_circuit_opens_after_failure_threshold(tmp_path):
    circuits = CircuitRegistry(CircuitPolicy(failure_threshold=1, recovery_seconds=100))
    runner = FakeRunner(tmp_path, [fail_result()])
    executor = ShellExecutor(runner, circuits=circuits)
    assert not executor.execute(ShellCommand("python", cwd=tmp_path)).ok
    with pytest.raises(Exception):
        executor.execute(ShellCommand("python", cwd=tmp_path))
    assert len(runner.commands) == 1


def test_executor_post_hook_failure_does_not_change_success(tmp_path):
    hooks = HookRegistry(post=[lambda metadata, result: (_ for _ in ()).throw(ValueError("nope"))])
    runner = FakeRunner(tmp_path, [ok_result()])
    executor = ShellExecutor(runner, hooks=hooks)
    outcome = executor.execute(ShellCommand("python", cwd=tmp_path))
    assert outcome.ok
    assert outcome.final_receipt.metadata["post_hook_failures"] == ["ValueError"]


def test_executor_pre_hook_can_veto_before_spawn(tmp_path):
    def veto(metadata):
        raise RuntimeError("blocked")
    runner = FakeRunner(tmp_path, [ok_result()])
    executor = ShellExecutor(runner, hooks=HookRegistry(pre=[veto]))
    with pytest.raises(RuntimeError):
        executor.execute(ShellCommand("python", cwd=tmp_path))
    assert runner.commands == []


def test_executor_preserves_explicit_correlation_id(tmp_path):
    runner = FakeRunner(tmp_path, [ok_result()])
    executor = ShellExecutor(runner)
    outcome = executor.execute(ShellCommand("python", cwd=tmp_path), correlation_id="corr-123")
    assert outcome.correlation_id == "corr-123"
    assert outcome.final_receipt.correlation_id == "corr-123"


def test_executor_retry_sleep_is_capped_by_config(tmp_path):
    sleeps = []
    runner = FakeRunner(tmp_path, [fail_result(75), ok_result()])
    executor = ShellExecutor(
        runner,
        grant=full_grant(),
        config=ExecutorConfig(max_retry_sleep_seconds=0.5),
        sleeper=sleeps.append,
    )
    executor.execute(
        ShellCommand("python", cwd=tmp_path),
        retry=RetryPolicy(max_attempts=2, retry_returncodes=frozenset({75}), initial_delay_seconds=99),
    )
    assert sleeps == [0.5]
