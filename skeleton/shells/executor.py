"""High-level policy, audit, retry, and receipt orchestration for shell commands."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math
import time
from typing import Callable
import uuid

from skeleton.shells.arguments import ArgumentPolicySet
from skeleton.shells.audit import AuditEvent, AuditSink, NullAuditSink
from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.circuit import CircuitRegistry
from skeleton.shells.environment import EnvironmentPolicy
from skeleton.shells.hooks import ExecutionMetadata, HookRegistry
from skeleton.shells.provenance import command_fingerprint, digest_arguments, digest_environment_keys
from skeleton.shells.receipts import ExecutionReceipt, ReceiptChain
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand, ShellResult, ShellRunner
from skeleton.shells.session import ShellSession
from skeleton.shells.telemetry import ShellTelemetry
from skeleton.shells.workspace import WorkspacePolicy


@dataclass(frozen=True)
class ExecutorConfig:
    long_running_threshold_seconds: float = 30.0
    large_output_threshold_bytes: int = 1024 * 1024
    max_retry_sleep_seconds: float = 30.0

    def __post_init__(self) -> None:
        for name, value, allow_zero in (
            ("long_running_threshold_seconds", self.long_running_threshold_seconds, False),
            ("max_retry_sleep_seconds", self.max_retry_sleep_seconds, True),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < (0.0 if allow_zero else 0.0)
                or (not allow_zero and float(value) == 0.0)
            ):
                qualifier = "finite and non-negative" if allow_zero else "finite and positive"
                raise ValueError(f"{name} must be {qualifier}")
        if (
            isinstance(self.large_output_threshold_bytes, bool)
            or not isinstance(self.large_output_threshold_bytes, int)
            or self.large_output_threshold_bytes <= 0
        ):
            raise ValueError("large_output_threshold_bytes must be a positive integer")


@dataclass(frozen=True)
class ExecutionOutcome:
    result: ShellResult
    receipts: tuple[ExecutionReceipt, ...]
    correlation_id: str

    @property
    def ok(self) -> bool:
        return self.result.ok

    @property
    def final_receipt(self) -> ExecutionReceipt:
        return self.receipts[-1]


class ShellExecutor:
    """One security boundary for every higher-level shell workflow."""

    def __init__(
        self,
        runner: ShellRunner,
        *,
        grant: CapabilityGrant | None = None,
        arguments: ArgumentPolicySet | None = None,
        environment: EnvironmentPolicy | None = None,
        workspace: WorkspacePolicy | None = None,
        audit: AuditSink | None = None,
        telemetry: ShellTelemetry | None = None,
        receipts: ReceiptChain | None = None,
        circuits: CircuitRegistry | None = None,
        hooks: HookRegistry | None = None,
        config: ExecutorConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.runner = runner
        self.grant = grant or CapabilityGrant.execution_only()
        self.arguments = arguments
        self.environment = environment
        self.workspace = workspace
        self.audit = audit or NullAuditSink()
        self.telemetry = telemetry or ShellTelemetry()
        self.receipt_chain = receipts
        self.circuits = circuits or CircuitRegistry()
        self.hooks = hooks or HookRegistry()
        self.config = config or ExecutorConfig()
        self._clock = clock
        self._sleeper = sleeper

    def _required_capabilities(self, command: ShellCommand, retry: RetryPolicy) -> set[ShellCapability]:
        required = {ShellCapability.EXECUTE}
        if command.env:
            required.add(ShellCapability.CUSTOM_ENV)
        if command.stdin is not None:
            required.add(ShellCapability.STDIN)
        if command.allowed_returncodes != frozenset({0}):
            required.add(ShellCapability.NONZERO_SUCCESS)
        if command.timeout is not None and command.timeout > self.config.long_running_threshold_seconds:
            required.add(ShellCapability.LONG_RUNNING)
        if self.runner.policy.max_output_bytes > self.config.large_output_threshold_bytes:
            required.add(ShellCapability.LARGE_OUTPUT)
        if retry.max_attempts > 1:
            required.add(ShellCapability.RETRY)
        return required

    def _prepare(self, command: ShellCommand, retry: RetryPolicy) -> ShellCommand:
        self.grant.require_all(self._required_capabilities(command, retry), command=command.command)
        args = command.args
        if self.arguments is not None:
            args = self.arguments.validate(command.command, args)
        env = command.env
        if self.environment is not None:
            env = self.environment.build(command.command, env)
        cwd = command.cwd
        if self.workspace is not None:
            cwd = self.workspace.resolve(command.command, cwd)
        return replace(command, args=tuple(args), env=dict(env), cwd=cwd)

    @staticmethod
    def _receipt(
        *,
        command: ShellCommand,
        correlation_id: str,
        fingerprint: str,
        attempt: int,
        started_wall: str,
        finished_wall: str,
        duration_ms: float,
        result: ShellResult,
        hook_failures: tuple[str, ...] = (),
    ) -> ExecutionReceipt:
        return ExecutionReceipt(
            command=command.command,
            correlation_id=correlation_id,
            fingerprint=fingerprint,
            started_at=started_wall,
            finished_at=finished_wall,
            duration_ms=duration_ms,
            returncode=result.returncode,
            ok=result.ok,
            timed_out=result.timed_out,
            output_limited=result.output_limited,
            stdout_bytes=len(result.stdout),
            stderr_bytes=len(result.stderr),
            attempt=attempt,
            metadata={"post_hook_failures": list(hook_failures)} if hook_failures else {},
        )

    def execute(
        self,
        command: ShellCommand,
        *,
        retry: RetryPolicy | None = None,
        session: ShellSession | None = None,
        correlation_id: str | None = None,
        circuit_key: str | None = None,
    ) -> ExecutionOutcome:
        retry_policy = retry or RetryPolicy.none()
        prepared = self._prepare(command, retry_policy)
        correlation = correlation_id or uuid.uuid4().hex
        fingerprint = command_fingerprint(
            prepared.command,
            prepared.args,
            cwd=prepared.cwd,
            env_keys=tuple(prepared.env),
        )
        circuit = self.circuits.get(circuit_key or prepared.command)
        attempt = 1
        receipts: list[ExecutionReceipt] = []

        while True:
            circuit.allow(command=prepared.command)
            if session is not None:
                session.require_start(prepared.command)
            metadata = ExecutionMetadata(
                command=prepared.command,
                correlation_id=correlation,
                fingerprint=fingerprint,
                attempt=attempt,
                session_id=None if session is None else session.session_id,
            )
            self.hooks.run_pre(metadata)
            self.telemetry.started(prepared.command)
            self.audit.emit(
                AuditEvent.create(
                    "shell.execution.started",
                    correlation,
                    command=prepared.command,
                    data={
                        "attempt": attempt,
                        "fingerprint": fingerprint,
                        "args_digest": digest_arguments(prepared.args),
                        "env_keys_digest": digest_environment_keys(tuple(prepared.env)),
                        "session_id": metadata.session_id,
                    },
                )
            )
            started_wall = datetime.now(timezone.utc).isoformat()
            started = self._clock()
            result = self.runner.run(prepared)
            duration_ms = max(0.0, (self._clock() - started) * 1000.0)
            finished_wall = datetime.now(timezone.utc).isoformat()
            hook_failures = self.hooks.run_post(metadata, result)
            receipt = self._receipt(
                command=prepared,
                correlation_id=correlation,
                fingerprint=fingerprint,
                attempt=attempt,
                started_wall=started_wall,
                finished_wall=finished_wall,
                duration_ms=duration_ms,
                result=result,
                hook_failures=hook_failures,
            )
            receipts.append(receipt)
            if self.receipt_chain is not None:
                self.receipt_chain.append(receipt)
            if session is not None:
                session.record(receipt)
            self.telemetry.completed(
                prepared.command,
                ok=result.ok,
                timed_out=result.timed_out,
                output_limited=result.output_limited,
                stdout_bytes=len(result.stdout),
                stderr_bytes=len(result.stderr),
                duration_ms=duration_ms,
            )
            self.audit.emit(
                AuditEvent.create(
                    "shell.execution.completed",
                    correlation,
                    command=prepared.command,
                    data={
                        "attempt": attempt,
                        "receipt_id": receipt.receipt_id,
                        "returncode": result.returncode,
                        "ok": result.ok,
                        "timed_out": result.timed_out,
                        "output_limited": result.output_limited,
                        "stdout_bytes": len(result.stdout),
                        "stderr_bytes": len(result.stderr),
                        "duration_ms": duration_ms,
                        "post_hook_failures": list(hook_failures),
                    },
                )
            )

            if result.ok:
                circuit.record_success()
                return ExecutionOutcome(result, tuple(receipts), correlation)
            circuit.record_failure()
            decision = retry_policy.decide(
                attempt=attempt,
                returncode=result.returncode,
                timed_out=result.timed_out,
                output_limited=result.output_limited,
            )
            if not decision.retry:
                return ExecutionOutcome(result, tuple(receipts), correlation)
            if session is not None:
                session.require_retry(prepared.command)
            delay = min(decision.delay_seconds, self.config.max_retry_sleep_seconds)
            self.telemetry.retried(prepared.command)
            self.audit.emit(
                AuditEvent.create(
                    "shell.execution.retry",
                    correlation,
                    command=prepared.command,
                    data={"attempt": attempt, "delay_seconds": delay, "reason": decision.reason},
                )
            )
            if delay:
                self._sleeper(delay)
            attempt += 1
