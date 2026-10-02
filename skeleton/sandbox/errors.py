"""Error hierarchy for the execution sandbox (B082/B086)."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SandboxError(Exception):
    code = "SANDBOX"

    def __init__(self, message: str, *, context: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = dict(context or {})

    def to_record(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


class PathEscapeError(SandboxError):
    """A path resolved (or linked) outside the jail root."""

    code = "SANDBOX.FS.ESCAPE"


class FsPolicyError(SandboxError):
    """A filesystem operation violated the jail policy (type, name, quota)."""

    code = "SANDBOX.FS.POLICY"


class QuotaExceededError(FsPolicyError):
    code = "SANDBOX.FS.QUOTA"


class ProcessPolicyError(SandboxError):
    """A process request was refused before launch (argv, env, binary)."""

    code = "SANDBOX.PROC.POLICY"


class ProcessLimitError(SandboxError):
    """A sandboxed process hit a wall-clock or output limit."""

    code = "SANDBOX.PROC.LIMIT"


class SanitizerError(SandboxError):
    """Input could not be made safe (e.g. too large or too deep)."""

    code = "SANDBOX.SANITIZE"


class InjectionDetectedError(SandboxError):
    """Untrusted input was blocked by the injection detector."""

    code = "SANDBOX.INJECTION"


__all__ = [
    "FsPolicyError",
    "InjectionDetectedError",
    "PathEscapeError",
    "ProcessLimitError",
    "ProcessPolicyError",
    "QuotaExceededError",
    "SandboxError",
    "SanitizerError",
]
