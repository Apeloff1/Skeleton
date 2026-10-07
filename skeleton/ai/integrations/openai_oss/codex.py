"""Codex sandbox/approval compatibility with stricter Skeleton admission."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from typing import Callable

from .optional import load_optional
from .registry import source


class CodexSandbox(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "full-access"


class CodexApprovalMode(str, Enum):
    DENY_ALL = "deny_all"
    AUTO_REVIEW = "auto_review"


@dataclass(frozen=True, slots=True)
class CodexAdmission:
    allowed: bool
    reason_code: str


class CodexInteropPolicy:
    def __init__(self, *, allow_full_access: bool = False) -> None:
        self.allow_full_access = bool(allow_full_access)

    def admit(
        self,
        sandbox: CodexSandbox,
        approval_mode: CodexApprovalMode,
        *,
        explicit_user_action: bool = False,
        workspace_trusted: bool = False,
    ) -> CodexAdmission:
        sandbox = (
            sandbox if isinstance(sandbox, CodexSandbox) else CodexSandbox(str(sandbox))
        )
        approval_mode = (
            approval_mode
            if isinstance(approval_mode, CodexApprovalMode)
            else CodexApprovalMode(str(approval_mode))
        )
        if sandbox is CodexSandbox.READ_ONLY:
            return CodexAdmission(True, "read-only")
        if sandbox is CodexSandbox.WORKSPACE_WRITE:
            if not (workspace_trusted or explicit_user_action):
                return CodexAdmission(False, "workspace-write-requires-trust")
            return CodexAdmission(True, "workspace-write-admitted")
        if not self.allow_full_access:
            return CodexAdmission(False, "full-access-disabled")
        if not explicit_user_action:
            return CodexAdmission(False, "full-access-requires-explicit-user-action")
        if approval_mode is not CodexApprovalMode.AUTO_REVIEW:
            return CodexAdmission(False, "full-access-requires-active-review")
        return CodexAdmission(True, "full-access-explicitly-admitted")


class CodexSdkBridge:
    def __init__(
        self,
        *,
        importer: Callable[[str], object] = import_module,
    ) -> None:
        self._importer = importer

    def upstream_values(
        self,
        sandbox: CodexSandbox,
        approval_mode: CodexApprovalMode,
    ) -> tuple[object, object]:
        module = load_optional(source("codex"), "openai_codex", importer=self._importer)
        upstream_sandbox = module.Sandbox(str(CodexSandbox(sandbox).value))
        upstream_approval = module.ApprovalMode(str(CodexApprovalMode(approval_mode).value))
        return upstream_sandbox, upstream_approval


__all__ = [
    "CodexAdmission",
    "CodexApprovalMode",
    "CodexInteropPolicy",
    "CodexSandbox",
    "CodexSdkBridge",
]
