"""Examples of composing the Skeleton shell execution plane.

This module is documentation-oriented and intentionally does not run anything on
import. Applications should supply trusted executable paths and task-specific
workspace paths from their own deployment/configuration layer.
"""

from __future__ import annotations

from pathlib import Path

from skeleton.shells.arguments import ArgumentPolicy, ArgumentPolicySet, OptionRule, ValueConstraint
from skeleton.shells.audit import MemoryAuditSink, RedactingAuditSink
from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.environment import EnvironmentPolicy, EnvironmentValueRule
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.limits import ResourceLimits
from skeleton.shells.pipeline import PipelineExecutor, PipelineSpec, PipelineStep
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand, ShellPolicy, ShellRunner
from skeleton.shells.session import ShellSession
from skeleton.shells.telemetry import ShellTelemetry
from skeleton.shells.workspace import WorkspacePolicy


def build_executor(*, python_executable: Path, workspace: Path) -> ShellExecutor:
    policy = ShellPolicy(
        executables={"python": str(python_executable.resolve(strict=True))},
        cwd_roots=(workspace.resolve(strict=True),),
        allowed_env=frozenset({"LANG", "LC_ALL"}),
        inherited_env=frozenset({"LANG", "LC_ALL"}),
        default_timeout=10.0,
        max_timeout=60.0,
        max_output_bytes=1024 * 1024,
        max_input_bytes=64 * 1024,
        max_env_bytes=4096,
        max_args=64,
        max_arg_bytes=16 * 1024,
    )
    arguments = ArgumentPolicySet(
        {
            "python": ArgumentPolicy(
                options={
                    "-m": OptionRule(
                        "-m",
                        takes_value=True,
                        value=ValueConstraint(choices=frozenset({"compileall"})),
                    ),
                    "-q": OptionRule("-q"),
                },
                variadic=ValueConstraint(pattern=r"[A-Za-z0-9_./-]+", max_length=512),
                max_positionals=8,
                max_total_args=16,
                max_total_bytes=4096,
            )
        }
    )
    environment = EnvironmentPolicy(
        rules={
            "LANG": EnvironmentValueRule(pattern=r"[A-Za-z0-9_.-]+", max_bytes=64),
            "LC_ALL": EnvironmentValueRule(pattern=r"[A-Za-z0-9_.-]+", max_bytes=64),
        },
        inherited=frozenset({"LANG", "LC_ALL"}),
        max_total_bytes=256,
    )
    grant = CapabilityGrant(
        frozenset(
            {
                ShellCapability.EXECUTE,
                ShellCapability.RETRY,
                ShellCapability.PIPELINE,
            }
        ),
        principal="build-worker",
        scope="compile",
    )
    audit_memory = MemoryAuditSink(max_events=1000)
    return ShellExecutor(
        ShellRunner(policy),
        grant=grant,
        arguments=arguments,
        environment=environment,
        workspace=WorkspacePolicy((workspace,)),
        audit=RedactingAuditSink(audit_memory),
        telemetry=ShellTelemetry(),
        receipts=ReceiptChain(max_receipts=1000),
    )


def compile_once(executor: ShellExecutor, workspace: Path):
    session = ShellSession(
        ResourceLimits(
            max_commands=2,
            max_failures=1,
            max_duration_ms=30_000,
            max_stdout_bytes=512 * 1024,
            max_stderr_bytes=512 * 1024,
            max_retries=0,
        ),
        principal="compile-once",
    )
    command = ShellCommand(
        "python",
        ("-m", "compileall", "-q", "."),
        cwd=workspace,
        timeout=20.0,
    )
    return executor.execute(command, session=session)


def compile_with_transient_retry(executor: ShellExecutor, workspace: Path):
    session = ShellSession(
        ResourceLimits(
            max_commands=3,
            max_failures=2,
            max_duration_ms=60_000,
            max_stdout_bytes=1024 * 1024,
            max_stderr_bytes=1024 * 1024,
            max_retries=1,
        ),
        principal="compile-retry",
    )
    policy = RetryPolicy(
        max_attempts=2,
        initial_delay_seconds=0.25,
        multiplier=2.0,
        max_delay_seconds=1.0,
        retry_returncodes=frozenset({75}),
    )
    command = ShellCommand("python", ("-m", "compileall", "-q", "."), cwd=workspace, timeout=20.0)
    return executor.execute(command, retry=policy, session=session)


def compile_pipeline(executor: ShellExecutor, workspace: Path):
    session = ShellSession(ResourceLimits(max_commands=4, max_failures=2), principal="pipeline")
    spec = PipelineSpec(
        "compile-project",
        (
            PipelineStep(
                "compile-root",
                ShellCommand("python", ("-m", "compileall", "-q", "."), cwd=workspace, timeout=20.0),
            ),
            PipelineStep(
                "compile-tests",
                ShellCommand("python", ("-m", "compileall", "-q", "tests"), cwd=workspace, timeout=20.0),
                depends_on=frozenset({"compile-root"}),
            ),
        ),
    )
    return PipelineExecutor(executor).execute(spec, session=session)
