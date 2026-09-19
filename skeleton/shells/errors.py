"""Structured errors for the Skeleton shell execution plane.

Errors are intentionally metadata-light.  They never embed raw argv, child
output, environment values, or executable paths.  Callers that need forensic
detail should correlate the public error with an execution receipt or audit
record rather than expanding exception strings with sensitive material.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class ShellErrorCode(str, Enum):
    POLICY = "policy_violation"
    CAPABILITY = "capability_denied"
    ARGUMENT = "argument_rejected"
    ENVIRONMENT = "environment_rejected"
    WORKSPACE = "workspace_rejected"
    COMMAND = "command_not_registered"
    CIRCUIT_OPEN = "circuit_open"
    SESSION_BUDGET = "session_budget_exhausted"
    PIPELINE = "pipeline_invalid"
    EXECUTION = "execution_failed"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit"
    CANCELLED = "cancelled"
    SERIALIZATION = "serialization_error"


@dataclass(frozen=True)
class ShellErrorContext:
    """Non-sensitive context suitable for logs and machine responses."""

    code: ShellErrorCode
    command: str | None = None
    stage: str | None = None
    correlation_id: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {"code": self.code.value}
        if self.command:
            payload["command"] = self.command
        if self.stage:
            payload["stage"] = self.stage
        if self.correlation_id:
            payload["correlation_id"] = self.correlation_id
        if self.detail:
            payload["detail"] = self.detail
        return payload


class ShellPlaneError(RuntimeError):
    """Base error that carries safe structured context."""

    def __init__(self, context: ShellErrorContext) -> None:
        self.context = context
        message = context.code.value
        if context.command:
            message += f" for {context.command!r}"
        if context.detail:
            message += f": {context.detail}"
        super().__init__(message)

    def to_dict(self) -> Mapping[str, str]:
        return self.context.to_dict()


class CapabilityDenied(ShellPlaneError):
    pass


class ArgumentRejected(ShellPlaneError):
    pass


class EnvironmentRejected(ShellPlaneError):
    pass


class WorkspaceRejected(ShellPlaneError):
    pass


class CircuitOpen(ShellPlaneError):
    pass


class SessionBudgetExhausted(ShellPlaneError):
    pass


class PipelineError(ShellPlaneError):
    pass
