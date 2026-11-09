"""Runtime invocation surface for compiled logical toolchain contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
import uuid

from skeleton.shells.executor import ExecutionOutcome
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand
from skeleton.shells.session import ShellSession
from skeleton.shells.toolchains.compiler import CompiledToolchain
from skeleton.shells.toolchains.types import (
    CommandEffect,
    CommandRisk,
    LogicalCommandContract,
)


class ToolchainInvocationError(ValueError):
    pass


@dataclass(frozen=True)
class ToolchainInvocation:
    contract: str
    args: tuple[str, ...] = ()
    cwd: Path | str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    stdin: bytes | None = None
    timeout: float | None = None
    allowed_returncodes: frozenset[int] = frozenset({0})
    correlation_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))
        codes = frozenset(self.allowed_returncodes)
        if not codes:
            raise ValueError("allowed_returncodes cannot be empty")
        if any(isinstance(code, bool) or not isinstance(code, int) for code in codes):
            raise ValueError("return codes must be integers")
        object.__setattr__(self, "allowed_returncodes", codes)


@dataclass(frozen=True)
class PreparedToolchainInvocation:
    invocation: ToolchainInvocation
    contract: LogicalCommandContract
    command: ShellCommand
    correlation_id: str

    @property
    def effects(self) -> frozenset[CommandEffect]:
        return self.contract.effects

    @property
    def risk(self) -> CommandRisk:
        return self.contract.risk

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract.name,
            "executable_key": self.contract.executable_key,
            "args": list(self.command.args),
            "cwd": None if self.command.cwd is None else str(self.command.cwd),
            "env_keys": sorted(self.command.env),
            "stdin_bytes": 0 if self.command.stdin is None else len(self.command.stdin),
            "timeout": self.command.timeout,
            "allowed_returncodes": sorted(self.command.allowed_returncodes),
            "correlation_id": self.correlation_id,
            "effects": sorted(effect.value for effect in self.contract.effects),
            "risk": self.contract.risk.value,
        }


@dataclass(frozen=True)
class ToolchainExecutionResult:
    prepared: PreparedToolchainInvocation
    outcome: ExecutionOutcome

    @property
    def ok(self) -> bool:
        return self.outcome.ok

    @property
    def contract(self) -> LogicalCommandContract:
        return self.prepared.contract

    def to_dict(self) -> dict[str, object]:
        receipt = self.outcome.final_receipt
        return {
            "ok": self.ok,
            "contract": self.contract.name,
            "correlation_id": self.outcome.correlation_id,
            "returncode": self.outcome.result.returncode,
            "timed_out": self.outcome.result.timed_out,
            "output_limited": self.outcome.result.output_limited,
            "receipt_ids": [item.receipt_id for item in self.outcome.receipts],
            "duration_ms": receipt.duration_ms,
            "effects": sorted(effect.value for effect in self.contract.effects),
            "risk": self.contract.risk.value,
        }


class ToolchainExecutionPlane:
    """Prepare and execute only commands present in a compiled contract set."""

    def __init__(self, compiled: CompiledToolchain) -> None:
        self.compiled = compiled

    def _resolve_cwd(self, cwd: Path | str | None) -> Path:
        if cwd is None:
            return self.compiled.roots[0]
        candidate = Path(cwd).expanduser().resolve(strict=True)
        if not candidate.is_dir():
            raise ToolchainInvocationError("cwd must be a directory")
        if not any(
            candidate == root or root in candidate.parents
            for root in self.compiled.roots
        ):
            raise ToolchainInvocationError("cwd is outside compiled roots")
        return candidate

    @staticmethod
    def _timeout(
        contract: LogicalCommandContract,
        requested: float | None,
    ) -> float | None:
        if requested is None:
            return contract.max_timeout
        if (
            isinstance(requested, bool)
            or not isinstance(requested, (int, float))
            or requested <= 0
        ):
            raise ToolchainInvocationError("timeout must be positive")
        value = float(requested)
        if contract.max_timeout is not None and value > contract.max_timeout:
            raise ToolchainInvocationError(
                f"timeout exceeds contract maximum of {contract.max_timeout}"
            )
        return value

    @staticmethod
    def _returncodes(
        contract: LogicalCommandContract,
        requested: frozenset[int],
    ) -> frozenset[int]:
        if requested == frozenset({0}):
            return requested
        if not contract.allow_nonzero_success:
            raise ToolchainInvocationError(
                "contract does not permit non-zero success return codes"
            )
        return requested

    def prepare(
        self,
        invocation: ToolchainInvocation,
    ) -> PreparedToolchainInvocation:
        contract = self.compiled.get(invocation.contract)
        args = contract.arguments.validate(contract.name, invocation.args)
        env = contract.environment.build(contract.name, invocation.env)
        if invocation.stdin is not None and not contract.allow_stdin:
            raise ToolchainInvocationError("contract does not permit stdin")
        timeout = self._timeout(contract, invocation.timeout)
        returncodes = self._returncodes(
            contract,
            invocation.allowed_returncodes,
        )
        correlation = invocation.correlation_id or uuid.uuid4().hex
        command = ShellCommand(
            contract.name,
            tuple(args),
            cwd=self._resolve_cwd(invocation.cwd),
            env=dict(env),
            stdin=invocation.stdin,
            timeout=timeout,
            allowed_returncodes=returncodes,
        )
        return PreparedToolchainInvocation(
            invocation=invocation,
            contract=contract,
            command=command,
            correlation_id=correlation,
        )

    def execute(
        self,
        invocation: ToolchainInvocation,
        *,
        retry: RetryPolicy | None = None,
        session: ShellSession | None = None,
    ) -> ToolchainExecutionResult:
        prepared = self.prepare(invocation)
        outcome = self.compiled.executor.execute(
            prepared.command,
            retry=retry,
            session=session,
            correlation_id=prepared.correlation_id,
        )
        return ToolchainExecutionResult(prepared, outcome)

    def explain(self, contract_name: str) -> dict[str, object]:
        contract = self.compiled.get(contract_name)
        return {
            "name": contract.name,
            "executable_key": contract.executable_key,
            "effects": sorted(effect.value for effect in contract.effects),
            "risk": contract.risk.value,
            "tags": sorted(contract.tags),
            "max_timeout": contract.max_timeout,
            "stdin": contract.allow_stdin,
            "nonzero_success": contract.allow_nonzero_success,
            "environment_keys": list(contract.environment.allowed_keys()),
            "required_capabilities": sorted(
                capability.value
                for capability in contract.required_capabilities
            ),
        }

    def names(self) -> tuple[str, ...]:
        return self.compiled.names()
