"""Vulnerability scanner — dependency and configuration security checks.

This scanner is intentionally conservative: scanner self-failures are security
findings, unknown severities are rejected, diagnostics are bounded/redacted,
and an instance that has never completed a scan cannot report a healthy score.

The higher-level :mod:`skeleton.security.scanner_integrity` harness is the
canonical primitive for new scanners. This module preserves the historical
VulnScanner API while enforcing the same fail-closed invariants.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


SEVERITY_RANK = {
    "critical": 40,
    "high": 25,
    "medium": 10,
    "low": 3,
    "info": 0,
}
_BLOCKING = frozenset({"critical", "high"})
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_MESSAGE = 512
_MAX_REMEDIATION = 1024
_MAX_RULES = 512


class VulnScannerError(RuntimeError):
    """Raised when scanner configuration or evidence is invalid."""


def _bounded(value: object, *, field_name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise VulnScannerError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise VulnScannerError(f"{field_name} must not be empty")
    if len(text) > limit:
        raise VulnScannerError(f"{field_name} exceeds maximum length")
    if _CONTROL_RE.search(text):
        raise VulnScannerError(f"{field_name} contains control characters")
    return text


def _severity(value: object) -> str:
    if not isinstance(value, str):
        raise VulnScannerError("severity must be a string")
    normalized = value.strip().casefold()
    if normalized not in SEVERITY_RANK:
        raise VulnScannerError(
            "severity must be one of: critical, high, medium, low, info"
        )
    return normalized


def _rule_name(value: object) -> str:
    text = _bounded(value, field_name="rule name", limit=128).casefold()
    if _NAME_RE.fullmatch(text) is None:
        raise VulnScannerError("rule name must be a lowercase token")
    return text


def _safe_exception_type(exc: BaseException) -> str:
    name = type(exc).__name__
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
        return name
    return "Exception"


@dataclass(frozen=True, slots=True)
class Finding:
    check: str
    severity: str
    message: str
    remediation: str
    timestamp_ns: int = 0
    scanner_failure: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "check", _rule_name(self.check))
        object.__setattr__(self, "severity", _severity(self.severity))
        object.__setattr__(
            self,
            "message",
            _bounded(self.message, field_name="finding message", limit=_MAX_MESSAGE),
        )
        object.__setattr__(
            self,
            "remediation",
            _bounded(
                self.remediation,
                field_name="finding remediation",
                limit=_MAX_REMEDIATION,
            ),
        )
        if isinstance(self.timestamp_ns, bool) or not isinstance(self.timestamp_ns, int):
            raise VulnScannerError("timestamp_ns must be an integer")
        if self.timestamp_ns < 0:
            raise VulnScannerError("timestamp_ns must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check": self.check,
            "severity": self.severity,
            "message": self.message,
            "remediation": self.remediation,
            "timestamp_ns": self.timestamp_ns,
            "scanner_failure": self.scanner_failure,
        }


@dataclass(frozen=True, slots=True)
class CheckRule:
    name: str
    severity: str
    probe: Callable[[Path], Optional[str]]
    remediation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _rule_name(self.name))
        object.__setattr__(self, "severity", _severity(self.severity))
        if not callable(self.probe):
            raise VulnScannerError("probe must be callable")
        object.__setattr__(
            self,
            "remediation",
            _bounded(
                self.remediation,
                field_name="rule remediation",
                limit=_MAX_REMEDIATION,
            ),
        )


class VulnScanner:
    """Rule-based security scanner with explicit evidence state."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root is not None else Path(".")
        self._rules: List[CheckRule] = []
        self._last_scan: List[Finding] = []
        self._has_scanned = False
        self._scan_started_ns = 0
        self._scan_finished_ns = 0
        self._register_builtin()

    def _register_builtin(self) -> None:
        self.add_rule(
            "default-master-secret",
            "critical",
            lambda root: (
                "master secret not overridden" if self._secret_is_default(root) else None
            ),
            "Set SKELETON_MASTER_SECRET to a strong unique value.",
        )
        self.add_rule(
            "no-audit-log",
            "high",
            lambda root: (
                None
                if (root / ".skeleton" / "audit.jsonl").exists()
                else "audit log absent"
            ),
            "Enable audit logging so operator actions are traceable.",
        )
        self.add_rule(
            "rbac-missing",
            "medium",
            lambda root: (
                None
                if (root / ".skeleton" / "rbac.json").exists()
                else "no RBAC assignments persisted"
            ),
            "Grant least-privilege roles; avoid relying on default admin.",
        )
        self.add_rule(
            "unencrypted-secrets",
            "high",
            lambda root: self._secrets_unencrypted(root),
            "Install cryptography so the secret manager uses authenticated encryption.",
        )

    def _secret_is_default(self, root: Path) -> bool:
        del root
        import os

        return (
            os.environ.get("SKELETON_MASTER_SECRET", "default-secret-change-me")
            == "default-secret-change-me"
        )

    def _secrets_unencrypted(self, root: Path) -> Optional[str]:
        del root
        try:
            from cryptography.fernet import Fernet  # noqa: F401

            return None
        except ImportError:
            return "cryptography package missing — secrets encryption unavailable"

    def add_rule(
        self,
        name: str,
        severity: str,
        probe: Callable[[Path], Optional[str]],
        remediation: str,
    ) -> None:
        if len(self._rules) >= _MAX_RULES:
            raise VulnScannerError("scanner rule limit exceeded")
        rule = CheckRule(name, severity, probe, remediation)
        if any(existing.name == rule.name for existing in self._rules):
            raise VulnScannerError(f"duplicate scanner rule: {rule.name}")
        self._rules.append(rule)

    def scan(self) -> Dict[str, Any]:
        """Execute every configured rule.

        A raised probe exception becomes a CRITICAL scanner-failure finding.
        Raw exception text is deliberately excluded because it can contain
        credentials, paths, signed URLs, headers, or user-controlled payloads.
        """

        if not self._rules:
            raise VulnScannerError("security scanner has no rules")

        findings: List[Finding] = []
        executed = 0
        self._scan_started_ns = time.time_ns()

        for rule in self._rules:
            executed += 1
            try:
                issue = rule.probe(self.root)
            except Exception as exc:
                findings.append(
                    Finding(
                        check=rule.name,
                        severity="critical",
                        message=(
                            "scanner rule failed with "
                            f"{_safe_exception_type(exc)}"
                        ),
                        remediation=(
                            "Treat the scan as failed and repair the scanner "
                            "before merge or release."
                        ),
                        timestamp_ns=time.time_ns(),
                        scanner_failure=True,
                    )
                )
                continue

            if issue is None:
                continue
            if not isinstance(issue, str):
                findings.append(
                    Finding(
                        check=rule.name,
                        severity="critical",
                        message="scanner rule returned an unsupported result type",
                        remediation=(
                            "Repair the scanner rule contract before merge or release."
                        ),
                        timestamp_ns=time.time_ns(),
                        scanner_failure=True,
                    )
                )
                continue

            try:
                message = _bounded(
                    issue,
                    field_name="scanner finding",
                    limit=_MAX_MESSAGE,
                )
            except VulnScannerError:
                findings.append(
                    Finding(
                        check=rule.name,
                        severity="critical",
                        message="scanner rule returned an invalid or unbounded finding",
                        remediation=(
                            "Repair the scanner rule output before merge or release."
                        ),
                        timestamp_ns=time.time_ns(),
                        scanner_failure=True,
                    )
                )
                continue

            findings.append(
                Finding(
                    check=rule.name,
                    severity=rule.severity,
                    message=message,
                    remediation=rule.remediation,
                    timestamp_ns=time.time_ns(),
                )
            )

        self._scan_finished_ns = time.time_ns()
        self._last_scan = findings
        self._has_scanned = executed == len(self._rules)
        return self.card()

    def score(self) -> float:
        """Return a conservative posture score.

        Before the first completed scan the score is 0 rather than 100. This
        prevents callers from accidentally treating "not evaluated" as clean.
        """

        if not self._has_scanned:
            return 0.0
        deduction = sum(SEVERITY_RANK[f.severity] for f in self._last_scan)
        return max(0.0, 100.0 - float(deduction))

    def assert_merge_safe(self) -> None:
        if not self._has_scanned:
            raise VulnScannerError("security scanner has not completed")
        if any(f.scanner_failure for f in self._last_scan):
            raise VulnScannerError("security scanner self-failure detected")
        if any(f.severity in _BLOCKING for f in self._last_scan):
            raise VulnScannerError("blocking vulnerability findings detected")

    def card(self) -> Dict[str, Any]:
        by_severity: Dict[str, int] = {}
        for finding in self._last_scan:
            by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1

        state = "complete" if self._has_scanned else "not_run"
        duration_ns = (
            max(0, self._scan_finished_ns - self._scan_started_ns)
            if self._has_scanned
            else 0
        )
        return {
            "kind": "vuln-scanner-card",
            "state": state,
            "complete": self._has_scanned,
            "findings": [f.to_dict() for f in self._last_scan],
            "by_severity": by_severity,
            "score": round(self.score(), 1),
            "rules": len(self._rules),
            "duration_ns": duration_ns,
            "scanner_failures": sum(1 for f in self._last_scan if f.scanner_failure),
        }


__all__ = [
    "CheckRule",
    "Finding",
    "SEVERITY_RANK",
    "VulnScanner",
    "VulnScannerError",
]
