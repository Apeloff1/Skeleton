#!/usr/bin/env python3
"""Fail CI when GitHub Actions shell steps can trivially print secrets.

This is intentionally a high-confidence log-sink scanner, not a generic secret
scanner. Legitimate secret *consumption* is allowed; direct output of GitHub
secret context, secret-like shell variables, whole environments, or xtrace is
rejected so credentials do not reach Actions logs by construction.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = REPO_ROOT / ".github" / "workflows"
WORKFLOW_SUFFIXES = {".yml", ".yaml"}

SECRET_CONTEXT_RE = re.compile(
    r"\$\{\{\s*(?:secrets\.[A-Za-z_][A-Za-z0-9_]*|github\.token)\s*\}\}",
    re.IGNORECASE,
)
SECRET_NAME_RE = re.compile(
    r"(?:^|_)(?:TOKEN|SECRET|PASSWORD|PASSWD|PASS|API_KEY|PRIVATE_KEY|ACCESS_KEY|"
    r"AUTH|AUTHORIZATION|CREDENTIAL|SIGNATURE|SIGNING_KEY|SSH_KEY|ENCRYPTION_KEY|SIGNED_URL|WEBHOOK_SECRET)(?:$|_)",
    re.IGNORECASE,
)
SHELL_VAR_RE = re.compile(
    r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))"
)
POWERSHELL_ENV_RE = re.compile(
    r"\$env:(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
OUTPUT_COMMAND_RE = re.compile(
    r"^\s*(?P<cmd>echo|printf|printenv|env|set|tee|cat|export|declare|typeset)\b(?P<rest>.*)$",
    re.IGNORECASE,
)
POWERSHELL_SINK_RE = re.compile(
    r"\b(?:Write-Host|Write-Output|Out-Host)\b",
    re.IGNORECASE,
)
POWERSHELL_ENV_DUMP_RE = re.compile(
    r"^\s*(?:Get-ChildItem|gci|dir)\s+(?:-Path\s+)?Env:\s*$",
    re.IGNORECASE,
)
INLINE_RUN_RE = re.compile(r"^(?P<indent>\s*)(?:-\s*)?run:\s*(?P<body>.+?)\s*$")
BLOCK_RUN_RE = re.compile(r"^(?P<indent>\s*)(?:-\s*)?run:\s*[>|][0-9+-]*\s*$")
XTRACE_RE = re.compile(
    r"^\s*(?:set\s+(?:-[A-Za-z]*x[A-Za-z]*|-o\s+xtrace)|(?:ba|z|k|c|da)?sh\s+-[A-Za-z]*x[A-Za-z]*)\b",
    re.IGNORECASE,
)
OPTION_ONLY_RE = re.compile(r"^(?:--?[A-Za-z0-9][A-Za-z0-9-]*\s*)+$")


class WorkflowSecretOutputScanError(RuntimeError):
    """Raised when required workflow coverage cannot be established."""


def _secretish_var(name: str) -> bool:
    return bool(SECRET_NAME_RE.search(name))


def _options_only(rest: str) -> bool:
    return bool(rest and OPTION_ONLY_RE.fullmatch(rest))


def command_violation(command: str) -> str | None:
    """Return one high-confidence reason for a dangerous shell command."""
    stripped = command.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if XTRACE_RE.match(stripped):
        return "shell xtrace is forbidden because it can expose expanded secrets"
    if POWERSHELL_ENV_DUMP_RE.match(stripped):
        return "PowerShell environment enumeration exposes the process environment"

    powershell_sink = bool(POWERSHELL_SINK_RE.search(stripped))
    if powershell_sink and SECRET_CONTEXT_RE.search(stripped):
        return "workflow output command exposes GitHub secret context"
    if powershell_sink:
        for variable in POWERSHELL_ENV_RE.finditer(stripped):
            name = variable.group("name")
            if _secretish_var(name):
                return f"workflow output command exposes secret-like variable {name}"

    match = OUTPUT_COMMAND_RE.match(stripped)
    if not match:
        return None

    cmd = match.group("cmd").lower()
    rest = match.group("rest").strip()
    if cmd == "env" and (not rest or _options_only(rest) or rest.startswith(("|", ">", "2>"))):
        return "workflow output command env exposes the process environment"
    if cmd == "set" and (not rest or rest.startswith(("|", ">", "2>"))):
        return "workflow output command set exposes shell variables"
    if cmd == "printenv" and (not rest or _options_only(rest)):
        return "workflow output command printenv exposes the process environment"
    if cmd in {"export", "declare", "typeset"} and re.fullmatch(
        r"-(?:[A-Za-z]*p[A-Za-z]*|[A-Za-z]*x[A-Za-z]*)",
        rest,
    ):
        return f"workflow output command {cmd} exposes exported shell variables"

    if SECRET_CONTEXT_RE.search(stripped):
        return "workflow output command exposes GitHub secret context"

    for variable in SHELL_VAR_RE.finditer(stripped):
        name = variable.group("braced") or variable.group("plain") or ""
        if _secretish_var(name):
            return f"workflow output command exposes secret-like variable {name}"

    if cmd == "printenv":
        for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", rest):
            if _secretish_var(name):
                return f"workflow output command exposes secret-like variable {name}"
    return None


def workflow_violations_text(text: str) -> list[str]:
    """Inspect inline and block ``run`` steps without parsing untrusted YAML."""
    findings: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        block = BLOCK_RUN_RE.match(line)
        if block:
            base_indent = len(block.group("indent"))
            child = index + 1
            while child < len(lines):
                current = lines[child]
                if not current.strip():
                    child += 1
                    continue
                indent = len(current) - len(current.lstrip(" "))
                if indent <= base_indent:
                    break
                violation = command_violation(current)
                if violation:
                    findings.append(f"line {child + 1}: {violation}")
                child += 1
            index = child
            continue

        inline = INLINE_RUN_RE.match(line)
        if inline:
            violation = command_violation(inline.group("body"))
            if violation:
                findings.append(f"line {index + 1}: {violation}")
        index += 1
    return findings


def workflow_files(root: Path = WORKFLOW_ROOT) -> Iterable[Path]:
    """Yield workflow files deterministically and fail closed on coverage loss."""
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise WorkflowSecretOutputScanError("workflow root is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise WorkflowSecretOutputScanError("workflow root must not be a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise WorkflowSecretOutputScanError("workflow root is not a directory")

    try:
        entries = sorted(os.scandir(root), key=lambda item: item.name)
    except OSError as exc:
        raise WorkflowSecretOutputScanError("workflow root cannot be enumerated") from exc

    count = 0
    for entry in entries:
        path = Path(entry.path)
        try:
            item = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise WorkflowSecretOutputScanError("workflow entry metadata failed") from exc
        if stat.S_ISLNK(item.st_mode):
            raise WorkflowSecretOutputScanError(f"workflow entry must not be a symlink: {entry.name}")
        if not stat.S_ISREG(item.st_mode) or path.suffix.lower() not in WORKFLOW_SUFFIXES:
            continue
        count += 1
        yield path
    if count == 0:
        raise WorkflowSecretOutputScanError("no workflow YAML files were scanned")


def violations(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"read failure: {type(exc).__name__}"]
    return workflow_violations_text(text)


def main() -> int:
    findings: list[str] = []
    scanned = 0
    try:
        for path in workflow_files():
            scanned += 1
            relative = path.relative_to(REPO_ROOT)
            for finding in violations(path):
                findings.append(f"{relative}: {finding}")
    except WorkflowSecretOutputScanError as exc:
        print(f"Workflow secret-output scan failed: {exc}", file=sys.stderr)
        return 1

    if findings:
        print("Workflow secret-output violations detected:", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Workflow secret-output safety passed across {scanned} workflows: "
        "no direct secret log sinks, environment dumps, or xtrace found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
