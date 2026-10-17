"""Studio tools mediated by the generated-code sandbox.

File, process, test, and asset calls are untrusted payloads. The kernel
sandbox remains the grant authority. This module never widens a sealed
policy, never uses a shell, and refuses the injection corpus on preflight.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from skeleton.kernel.sandbox import Sandbox
from skeleton.security.generated_code_sandbox import (
    GeneratedCodeSandbox,
    Operation,
    OperationKind,
    PayloadKind,
    SandboxCapability,
    SandboxPolicyError,
)
from skeleton.security.injection_corpus import scan_injection_corpus


class ToolError(RuntimeError):
    """A tool call was denied or could not be mediated."""


AssetHook = Callable[[str, str], dict[str, Any]]


class StudioTools:
    """Workspace file ops, allowlisted process runs, and asset hooks."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        process_allowlist: Sequence[str] = (),
        asset_hook: AssetHook | None = None,
        kernel: Sandbox | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.kernel = kernel or Sandbox()
        allow = tuple(str(item) for item in process_allowlist)
        grants: list[SandboxCapability] = [SandboxCapability.FILESYSTEM]
        if allow:
            grants.append(SandboxCapability.PROCESS)
        self.sandbox = GeneratedCodeSandbox(
            self.workspace,
            grants=grants,
            process_allowlist=allow,
            kernel=self.kernel,
        )
        self.sandbox.seal()
        self.asset_hook = asset_hook
        self.process_allowlist = frozenset(allow)
        self.tool_calls = 0
        self.denied_tools = 0
        self.writes: dict[str, str] = {}

    def preflight_corpus(self) -> list[str]:
        """Return injection-corpus findings. Empty means the sandbox still fails closed."""
        return list(scan_injection_corpus())

    def read_text(self, relative: str) -> str:
        self.tool_calls += 1
        try:
            return self.sandbox.attempt(Operation(OperationKind.FS_READ, relative, SandboxCapability.FILESYSTEM))
        except (SandboxPolicyError, OSError) as exc:
            self.denied_tools += 1
            raise ToolError(str(exc)) from exc

    def write_text(self, relative: str, content: str) -> None:
        self.tool_calls += 1
        kind = PayloadKind.PYTHON if str(relative).endswith(".py") else PayloadKind.PROMPT
        try:
            self._admit(content, kind)
            self.sandbox.attempt(
                Operation(OperationKind.FS_WRITE, relative, SandboxCapability.FILESYSTEM, content)
            )
        except (SandboxPolicyError, OSError, ToolError) as exc:
            self.denied_tools += 1
            if isinstance(exc, ToolError):
                raise
            raise ToolError(str(exc)) from exc
        self.writes[relative.replace("\\", "/")] = content

    def run_process(self, argv: Sequence[str], *, timeout: float = 5.0) -> dict[str, Any]:
        self.tool_calls += 1
        try:
            command = self._command(argv)
            self._admit(" ".join(command), PayloadKind.PROMPT)
            detail = " ".join(command[1:])
            decision = self.sandbox.authorize(
                Operation(OperationKind.PROCESS, command[0], SandboxCapability.PROCESS, detail)
            )
            if not decision.allowed:
                raise ToolError(decision.reason)
        except (SandboxPolicyError, ToolError) as exc:
            self.denied_tools += 1
            if isinstance(exc, ToolError):
                raise
            raise ToolError(str(exc)) from exc
        return self._spawn(command, timeout=timeout)

    def run_tests(self, argv: Sequence[str] | None = None, *, timeout: float = 5.0) -> dict[str, Any]:
        command = list(argv) if argv is not None else ["python3", "check.py"]
        return self.run_process(command, timeout=timeout)

    def generate_asset(self, kind: str, prompt: str) -> dict[str, Any]:
        self.tool_calls += 1
        try:
            self._admit(f"{kind}\n{prompt}", PayloadKind.PROMPT)
        except ToolError:
            self.denied_tools += 1
            return {"ok": False, "reason": "asset prompt denied"}
        if self.asset_hook is not None:
            produced = self.asset_hook(kind, prompt)
            if not isinstance(produced, dict):
                raise ToolError("asset hook must return an object")
            return produced
        name = f"{_slug(kind)}-{_slug(prompt)}.txt"
        relative = f"assets/{name}"
        body = f"{_slug(kind)}\n{_slug(prompt)}\n"
        try:
            self.sandbox.attempt(
                Operation(OperationKind.FS_WRITE, relative, SandboxCapability.FILESYSTEM, body)
            )
        except (SandboxPolicyError, OSError) as exc:
            self.denied_tools += 1
            raise ToolError(str(exc)) from exc
        self.writes[relative] = body
        return {"ok": True, "path": str(self.workspace / relative), "relative": relative}

    def _admit(self, payload: str, kind: PayloadKind) -> None:
        decision = self.sandbox.ingest_untrusted(payload, kind=kind)
        if not decision.allowed:
            raise ToolError(decision.reason)

    def _command(self, argv: Sequence[str]) -> list[str]:
        if not isinstance(argv, Sequence) or isinstance(argv, (str, bytes)) or not argv:
            raise ToolError("argv must be a non-empty list")
        command = [str(part) for part in argv]
        if len(command) > 8 or any(len(part) > 200 or not part.strip() for part in command):
            raise ToolError("argv is out of bounds")
        if "/" in command[0] or "\\" in command[0]:
            raise ToolError("executable must be an allowlisted basename")
        return command

    def _spawn(self, command: list[str], *, timeout: float) -> dict[str, Any]:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < float(timeout) <= 30:
            raise ToolError("timeout must be a positive number up to 30 seconds")
        executable = _resolve_executable(command[0])
        if executable is None:
            return {"ok": False, "stdout": "", "stderr": "executable unavailable", "returncode": None}
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        try:
            completed = subprocess.run(
                [executable, *command[1:]],
                cwd=self.workspace,
                shell=False,
                capture_output=True,
                text=True,
                timeout=float(timeout),
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": "timeout", "returncode": None}
        except OSError as exc:
            return {"ok": False, "stdout": "", "stderr": type(exc).__name__, "returncode": None}
        return {
            "ok": completed.returncode == 0,
            "stdout": completed.stdout[:4000],
            "stderr": completed.stderr[:4000],
            "returncode": completed.returncode,
        }


def _resolve_executable(name: str) -> str | None:
    if name in {"python", "python3"}:
        return sys.executable
    found = shutil.which(name)
    return found


def _slug(value: str) -> str:
    cleaned = []
    for char in value.lower():
        cleaned.append(char if char.isalnum() else "-")
    parts = [part for part in "".join(cleaned).split("-") if part]
    return "-".join(parts)[:40] or "asset"
