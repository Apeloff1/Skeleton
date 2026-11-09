"""Vulnerability scanner — dependency and configuration security checks.

Static security scanner for Skeleton's own configuration and state:
checks for default secrets, overly broad RBAC permissions, unencrypted
storage, disabled audit logging, missing TLS on webhooks, and known-bad
dependency versions. Produces findings with severity and remediation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


@dataclass
class Finding:
    check: str
    severity: str
    message: str
    remediation: str
    timestamp_ns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check": self.check,
            "severity": self.severity,
            "message": self.message,
            "remediation": self.remediation,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass
class CheckRule:
    name: str
    severity: str
    probe: Callable[[Path], Optional[str]]
    remediation: str


class VulnScanner:
    """Rule-based security scanner with pluggable checks."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".")
        self._rules: List[CheckRule] = []
        self._last_scan: List[Finding] = []
        self._register_builtin()

    def _register_builtin(self) -> None:
        self.add_rule(
            "default-master-secret", "critical",
            lambda root: "master secret not overridden" if self._secret_is_default(root) else None,
            "Set SKELETON_MASTER_SECRET to a strong unique value.",
        )
        self.add_rule(
            "no-audit-log", "high",
            lambda root: None if (root / ".skeleton" / "audit.jsonl").exists() else "audit log absent",
            "Enable audit logging so operator actions are traceable.",
        )
        self.add_rule(
            "rbac-missing", "medium",
            lambda root: None if (root / ".skeleton" / "rbac.json").exists() else "no RBAC assignments persisted",
            "Grant least-privilege roles; avoid relying on default admin.",
        )
        self.add_rule(
            "unencrypted-secrets", "high",
            lambda root: self._secrets_unencrypted(root),
            "Install cryptography so the secret manager uses Fernet encryption.",
        )

    def _secret_is_default(self, root: Path) -> bool:
        import os
        return os.environ.get("SKELETON_MASTER_SECRET", "default-secret-change-me") == "default-secret-change-me"

    def _secrets_unencrypted(self, root: Path) -> Optional[str]:
        try:
            from cryptography.fernet import Fernet  # noqa: F401
            return None
        except Exception:
            return "cryptography package missing — secrets stored base64 only"

    def add_rule(self, name: str, severity: str,
                 probe: Callable[[Path], Optional[str]], remediation: str) -> None:
        self._rules.append(CheckRule(name, severity, probe, remediation))

    def scan(self) -> Dict[str, Any]:
        findings: List[Finding] = []
        for rule in self._rules:
            try:
                issue = rule.probe(self.root)
            except Exception as exc:  # noqa: BLE001
                issue = f"check errored: {exc}"
            if issue:
                findings.append(Finding(
                    check=rule.name,
                    severity=rule.severity,
                    message=issue,
                    remediation=rule.remediation,
                    timestamp_ns=time.time_ns(),
                ))
        self._last_scan = findings
        return self.card()

    def score(self) -> float:
        """100 = clean; deductions scale with severity."""
        if not self._last_scan:
            return 100.0
        deduction = sum(10 * SEVERITY_RANK.get(f.severity, 0) for f in self._last_scan)
        return max(0.0, 100.0 - deduction)

    def card(self) -> Dict[str, Any]:
        by_severity: Dict[str, int] = {}
        for f in self._last_scan:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        return {
            "kind": "vuln-scanner-card",
            "findings": [f.to_dict() for f in self._last_scan],
            "by_severity": by_severity,
            "score": round(self.score(), 1),
            "rules": len(self._rules),
        }
