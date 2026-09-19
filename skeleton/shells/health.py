"""Non-executing health diagnostics for shell-plane configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from skeleton.shells.runner import ShellPolicy


@dataclass(frozen=True)
class HealthFinding:
    code: str
    severity: str
    subject: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "subject": self.subject,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ShellHealthReport:
    healthy: bool
    findings: tuple[HealthFinding, ...]
    executable_count: int
    cwd_root_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "healthy": self.healthy,
            "executable_count": self.executable_count,
            "cwd_root_count": self.cwd_root_count,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def inspect_policy(policy: ShellPolicy) -> ShellHealthReport:
    findings: list[HealthFinding] = []
    for name, raw_path in sorted(policy.executables.items()):
        path = Path(raw_path)
        if not path.exists():
            findings.append(HealthFinding("missing_executable", "error", name, "registered executable no longer exists"))
            continue
        if path.is_symlink():
            findings.append(HealthFinding("executable_symlink", "warning", name, "registered executable path is a symlink"))
        if not path.is_file():
            findings.append(HealthFinding("invalid_executable", "error", name, "registered executable is not a file"))
        elif os.name != "nt" and not os.access(path, os.X_OK):
            findings.append(HealthFinding("not_executable", "error", name, "registered file is not executable"))
    for index, root in enumerate(policy.cwd_roots):
        subject = f"cwd_root[{index}]"
        if not root.exists():
            findings.append(HealthFinding("missing_root", "error", subject, "cwd root no longer exists"))
        elif not root.is_dir():
            findings.append(HealthFinding("invalid_root", "error", subject, "cwd root is not a directory"))
        elif root.is_symlink():
            findings.append(HealthFinding("root_symlink", "warning", subject, "cwd root is a symlink"))
    if policy.inherited_env:
        findings.append(
            HealthFinding(
                "environment_inheritance",
                "info",
                "environment",
                f"{len(policy.inherited_env)} environment keys may be inherited",
            )
        )
    healthy = not any(finding.severity == "error" for finding in findings)
    return ShellHealthReport(healthy, tuple(findings), len(policy.executables), len(policy.cwd_roots))
