"""Fail-closed integrity primitives for repository security scanners.

Security scanners are part of the trust boundary. A scanner that crashes,
silently skips rules, emits unbounded diagnostics, or reports "clean" before
it has actually run is itself a vulnerability. This module provides a small,
standard-library-only harness that makes scanner state explicit and preserves
bounded, deterministic evidence.

The harness intentionally does not attempt to kill a hung Python callable.
Repository scanners that can block on external I/O must enforce their own
timeouts at that boundary. What this module guarantees is that every rule that
returns or raises produces explicit evidence and that scanner self-failures are
never converted into a green result.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

_MAX_RULES = 512
_MAX_TEXT = 512
_MAX_REMEDIATION = 1024
_MAX_METADATA_ITEMS = 64
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RULE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class ScannerIntegrityError(RuntimeError):
    """Raised when scanner configuration or evidence is not trustworthy."""


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ScanState(str, Enum):
    NOT_RUN = "not_run"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


_SEVERITY_WEIGHT = {
    Severity.CRITICAL: 40,
    Severity.HIGH: 25,
    Severity.MEDIUM: 10,
    Severity.LOW: 3,
    Severity.INFO: 0,
}


def _bounded_text(value: object, *, field_name: str, limit: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise ScannerIntegrityError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ScannerIntegrityError(f"{field_name} must not be empty")
    if len(text) > limit:
        raise ScannerIntegrityError(f"{field_name} exceeds maximum length")
    if _CONTROL_RE.search(text):
        raise ScannerIntegrityError(f"{field_name} contains control characters")
    return text


def _safe_rule_name(value: object) -> str:
    text = _bounded_text(value, field_name="rule name", limit=128)
    if _RULE_RE.fullmatch(text) is None:
        raise ScannerIntegrityError("rule name must be lowercase token text")
    return text


def _safe_exception_type(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name) else "Exception"


def _normalize_metadata(metadata: Mapping[str, object] | None) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise ScannerIntegrityError("metadata must be a mapping")
    if len(metadata) > _MAX_METADATA_ITEMS:
        raise ScannerIntegrityError("metadata contains too many entries")
    rows: list[tuple[str, str]] = []
    for raw_key, raw_value in metadata.items():
        key = _bounded_text(raw_key, field_name="metadata key", limit=96)
        value = _bounded_text(str(raw_value), field_name=f"metadata[{key}]", limit=256)
        rows.append((key, value))
    return tuple(sorted(rows))


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    severity: Severity
    message: str
    remediation: str
    scanner_failure: bool = False
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule", _safe_rule_name(self.rule))
        if not isinstance(self.severity, Severity):
            try:
                object.__setattr__(self, "severity", Severity(self.severity))
            except (TypeError, ValueError) as exc:
                raise ScannerIntegrityError("finding severity is invalid") from exc
        object.__setattr__(
            self,
            "message",
            _bounded_text(self.message, field_name="finding message", limit=_MAX_TEXT),
        )
        object.__setattr__(
            self,
            "remediation",
            _bounded_text(
                self.remediation,
                field_name="finding remediation",
                limit=_MAX_REMEDIATION,
            ),
        )
        object.__setattr__(self, "metadata", _normalize_metadata(dict(self.metadata)))

    def to_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "message": self.message,
            "remediation": self.remediation,
            "scanner_failure": self.scanner_failure,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Structured result returned by a scanner rule."""

    message: str
    remediation: str | None = None
    severity: Severity | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "message",
            _bounded_text(self.message, field_name="rule result message", limit=_MAX_TEXT),
        )
        if self.remediation is not None:
            object.__setattr__(
                self,
                "remediation",
                _bounded_text(
                    self.remediation,
                    field_name="rule result remediation",
                    limit=_MAX_REMEDIATION,
                ),
            )
        if self.severity is not None and not isinstance(self.severity, Severity):
            try:
                object.__setattr__(self, "severity", Severity(self.severity))
            except (TypeError, ValueError) as exc:
                raise ScannerIntegrityError("rule result severity is invalid") from exc
        object.__setattr__(self, "metadata", _normalize_metadata(dict(self.metadata)))


Probe = Callable[[Path], str | RuleResult | None]


@dataclass(frozen=True, slots=True)
class ScanRule:
    name: str
    severity: Severity
    probe: Probe
    remediation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _safe_rule_name(self.name))
        if not isinstance(self.severity, Severity):
            try:
                object.__setattr__(self, "severity", Severity(self.severity))
            except (TypeError, ValueError) as exc:
                raise ScannerIntegrityError("rule severity is invalid") from exc
        if not callable(self.probe):
            raise ScannerIntegrityError("rule probe must be callable")
        object.__setattr__(
            self,
            "remediation",
            _bounded_text(
                self.remediation,
                field_name="rule remediation",
                limit=_MAX_REMEDIATION,
            ),
        )


@dataclass(frozen=True, slots=True)
class ScanReport:
    scanner: str
    state: ScanState
    findings: tuple[Finding, ...]
    executed_rules: tuple[str, ...]
    expected_rules: tuple[str, ...]
    started_ns: int
    finished_ns: int
    evidence_digest: str

    @property
    def complete(self) -> bool:
        return self.state is ScanState.COMPLETE

    @property
    def duration_ns(self) -> int:
        return max(0, self.finished_ns - self.started_ns)

    @property
    def scanner_failures(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.scanner_failure)

    @property
    def blocking_findings(self) -> tuple[Finding, ...]:
        return tuple(
            item
            for item in self.findings
            if item.severity in {Severity.CRITICAL, Severity.HIGH}
        )

    def score(self) -> float:
        """Return a conservative posture score.

        Incomplete evidence is never allowed to look healthy: an incomplete
        report has score 0 regardless of the individual finding weights.
        """

        if not self.complete:
            return 0.0
        deduction = sum(_SEVERITY_WEIGHT[item.severity] for item in self.findings)
        return max(0.0, 100.0 - float(deduction))

    def assert_merge_safe(self) -> None:
        if not self.complete:
            raise ScannerIntegrityError("security scan evidence is incomplete")
        if self.scanner_failures:
            raise ScannerIntegrityError("security scanner self-failure detected")
        if self.blocking_findings:
            raise ScannerIntegrityError("blocking security findings detected")

    def to_dict(self) -> dict[str, object]:
        return {
            "scanner": self.scanner,
            "state": self.state.value,
            "complete": self.complete,
            "findings": [item.to_dict() for item in self.findings],
            "executed_rules": list(self.executed_rules),
            "expected_rules": list(self.expected_rules),
            "started_ns": self.started_ns,
            "finished_ns": self.finished_ns,
            "duration_ns": self.duration_ns,
            "evidence_digest": self.evidence_digest,
            "score": self.score(),
        }


@dataclass(slots=True)
class ScannerHarness:
    """Execute a closed rule set and produce fail-closed evidence."""

    scanner: str
    root: Path = field(default_factory=lambda: Path("."))
    _rules: list[ScanRule] = field(default_factory=list, init=False, repr=False)
    _last_report: ScanReport | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.scanner = _safe_rule_name(self.scanner)
        self.root = Path(self.root)

    @property
    def last_report(self) -> ScanReport | None:
        return self._last_report

    def add_rule(
        self,
        name: str,
        severity: Severity | str,
        probe: Probe,
        remediation: str,
    ) -> None:
        if len(self._rules) >= _MAX_RULES:
            raise ScannerIntegrityError("scanner rule limit exceeded")
        rule = ScanRule(
            name=name,
            severity=Severity(severity),
            probe=probe,
            remediation=remediation,
        )
        if any(existing.name == rule.name for existing in self._rules):
            raise ScannerIntegrityError(f"duplicate scanner rule: {rule.name}")
        self._rules.append(rule)

    def extend(self, rules: Iterable[ScanRule]) -> None:
        for rule in rules:
            self.add_rule(rule.name, rule.severity, rule.probe, rule.remediation)

    def scan(self) -> ScanReport:
        if not self._rules:
            raise ScannerIntegrityError("security scanner must contain at least one rule")

        started_ns = time.time_ns()
        findings: list[Finding] = []
        executed: list[str] = []
        expected = tuple(rule.name for rule in self._rules)

        for rule in self._rules:
            try:
                result = rule.probe(self.root)
            except Exception as exc:
                # Never include raw exception text: it may contain paths, URLs,
                # credentials, request data, or environment-derived values.
                findings.append(
                    Finding(
                        rule=rule.name,
                        severity=Severity.CRITICAL,
                        message=f"scanner rule failed with {_safe_exception_type(exc)}",
                        remediation="Treat the scan as failed and repair the scanner before merge.",
                        scanner_failure=True,
                    )
                )
                executed.append(rule.name)
                continue

            executed.append(rule.name)
            if result is None:
                continue

            try:
                if isinstance(result, str):
                    finding = Finding(
                        rule=rule.name,
                        severity=rule.severity,
                        message=result,
                        remediation=rule.remediation,
                    )
                elif isinstance(result, RuleResult):
                    finding = Finding(
                        rule=rule.name,
                        severity=result.severity or rule.severity,
                        message=result.message,
                        remediation=result.remediation or rule.remediation,
                        metadata=result.metadata,
                    )
                else:
                    finding = Finding(
                        rule=rule.name,
                        severity=Severity.CRITICAL,
                        message="scanner rule returned an unsupported result type",
                        remediation="Repair the scanner rule contract before merge.",
                        scanner_failure=True,
                        metadata=(("result_type", type(result).__name__),),
                    )
            except ScannerIntegrityError:
                # Probe output is untrusted scanner evidence. Invalid, oversized,
                # or control-bearing diagnostics must make the scan fail closed
                # without crashing the harness or leaking the raw diagnostic.
                finding = Finding(
                    rule=rule.name,
                    severity=Severity.CRITICAL,
                    message="scanner rule returned invalid bounded evidence",
                    remediation="Repair the scanner rule contract before merge.",
                    scanner_failure=True,
                )
            findings.append(finding)

        finished_ns = time.time_ns()
        complete = tuple(executed) == expected
        state = ScanState.COMPLETE if complete else ScanState.INCOMPLETE
        digest = _evidence_digest(
            scanner=self.scanner,
            state=state,
            findings=findings,
            executed=executed,
            expected=expected,
        )
        report = ScanReport(
            scanner=self.scanner,
            state=state,
            findings=tuple(findings),
            executed_rules=tuple(executed),
            expected_rules=expected,
            started_ns=started_ns,
            finished_ns=finished_ns,
            evidence_digest=digest,
        )
        self._last_report = report
        return report

    def require_report(self) -> ScanReport:
        if self._last_report is None:
            raise ScannerIntegrityError("security scanner has not run")
        return self._last_report

    def score(self) -> float:
        return self.require_report().score()


def _evidence_digest(
    *,
    scanner: str,
    state: ScanState,
    findings: Sequence[Finding],
    executed: Sequence[str],
    expected: Sequence[str],
) -> str:
    payload = {
        "scanner": scanner,
        "state": state.value,
        "findings": [item.to_dict() for item in findings],
        "executed_rules": list(executed),
        "expected_rules": list(expected),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "Finding",
    "RuleResult",
    "ScanReport",
    "ScanRule",
    "ScanState",
    "ScannerHarness",
    "ScannerIntegrityError",
    "Severity",
]
