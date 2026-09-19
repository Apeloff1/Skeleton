"""Agent/tool-facing adapter over ``ShellExecutor``.

The adapter deliberately returns a compact, redacted response rather than the
raw ``ShellResult``.  Tool callers may request bounded output views, but cannot
obtain executable paths or environment values through this surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from skeleton.shells.executor import ShellExecutor
from skeleton.shells.output import combined_summary
from skeleton.shells.redaction import SecretRedactor
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand
from skeleton.shells.session import ShellSession


@dataclass(frozen=True)
class ToolExecutionRequest:
    command: str
    args: tuple[str, ...] = ()
    cwd: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    stdin: bytes | None = None
    timeout: float | None = None
    include_output: bool = False
    max_output_chars: int = 4096

    def __post_init__(self) -> None:
        if not self.command or len(self.command) > 128:
            raise ValueError("tool command must be non-empty and bounded")
        if self.max_output_chars <= 0 or self.max_output_chars > 65_536:
            raise ValueError("tool output character bound is invalid")
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "env", dict(self.env))


@dataclass(frozen=True)
class ToolExecutionResponse:
    ok: bool
    command: str
    correlation_id: str
    receipt_id: str
    returncode: int | None
    timed_out: bool
    output_limited: bool
    duration_ms: float
    output: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": self.ok,
            "command": self.command,
            "correlation_id": self.correlation_id,
            "receipt_id": self.receipt_id,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "output_limited": self.output_limited,
            "duration_ms": self.duration_ms,
        }
        if self.output is not None:
            payload["output"] = dict(self.output)
        return payload


class ShellToolAdapter:
    def __init__(self, executor: ShellExecutor, *, redactor: SecretRedactor | None = None) -> None:
        self.executor = executor
        self.redactor = redactor or SecretRedactor()

    def execute(
        self,
        request: ToolExecutionRequest,
        *,
        session: ShellSession | None = None,
        retry: RetryPolicy | None = None,
    ) -> ToolExecutionResponse:
        command = ShellCommand(
            request.command,
            request.args,
            cwd=None if request.cwd is None else Path(request.cwd),
            env=request.env,
            stdin=request.stdin,
            timeout=request.timeout,
        )
        outcome = self.executor.execute(command, session=session, retry=retry)
        receipt = outcome.final_receipt
        output = None
        if request.include_output:
            output = combined_summary(
                outcome.result,
                max_chars_per_stream=request.max_output_chars,
                redactor=self.redactor,
            )
        return ToolExecutionResponse(
            ok=outcome.ok,
            command=request.command,
            correlation_id=outcome.correlation_id,
            receipt_id=receipt.receipt_id,
            returncode=outcome.result.returncode,
            timed_out=outcome.result.timed_out,
            output_limited=outcome.result.output_limited,
            duration_ms=receipt.duration_ms,
            output=output,
        )
