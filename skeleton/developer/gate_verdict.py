"""Fail-closed gate / verdict primitives for STU-TOOLS paths.

GameForge Sev1/Sev2 style: a red gate never silently passes. Verdicts are
deterministic and serializable so health / visualize / doctor regressions can
assert exact fail-closed behavior.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


class GateSeverity(str, Enum):
    """Severity ladder — Sev1 and Sev2 always fail closed."""

    INFO = "info"
    SEV2 = "sev2"
    SEV1 = "sev1"

    @property
    def fail_closed(self) -> bool:
        return self in (GateSeverity.SEV1, GateSeverity.SEV2)

    @property
    def rank(self) -> int:
        return {GateSeverity.INFO: 0, GateSeverity.SEV2: 1, GateSeverity.SEV1: 2}[self]


class GateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True)
class GateEvidence:
    """Structured evidence attached to a gate result."""

    key: str
    value: Any
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "value": self.value, "note": self.note}


@dataclass
class GateResult:
    """Single gate outcome. Fail-closed when severity is Sev1/Sev2 and not passed."""

    name: str
    status: GateStatus
    severity: GateSeverity
    reason: str = ""
    evidence: List[GateEvidence] = field(default_factory=list)
    path: str = ""
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == GateStatus.PASSED

    @property
    def blocks(self) -> bool:
        """True when this result must fail the overall verdict closed."""
        if self.status == GateStatus.SKIPPED:
            return False
        if self.status in (GateStatus.FAILED, GateStatus.ERROR):
            return self.severity.fail_closed
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "severity": self.severity.value,
            "reason": self.reason,
            "evidence": [e.to_dict() for e in self.evidence],
            "path": self.path,
            "duration_ms": round(self.duration_ms, 3),
            "metadata": dict(self.metadata),
            "passed": self.passed,
            "blocks": self.blocks,
        }


@dataclass
class Verdict:
    """Aggregate fail-closed verdict over a gate suite."""

    kind: str
    gates: List[GateResult] = field(default_factory=list)
    stored_prose: int = 0

    @property
    def ok(self) -> int:
        return 1 if self.all_passed else 0

    @property
    def all_passed(self) -> bool:
        return not any(g.blocks for g in self.gates)

    @property
    def blocking(self) -> List[GateResult]:
        return [g for g in self.gates if g.blocks]

    @property
    def passed_count(self) -> int:
        return sum(1 for g in self.gates if g.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for g in self.gates if g.status == GateStatus.FAILED)

    @property
    def banner(self) -> str:
        if self.all_passed:
            return "VERDICT: ALL GATES PASSED"
        names = ", ".join(g.name for g in self.blocking) or "unknown"
        return f"VERDICT: FAIL CLOSED — {names}"

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "kind": self.kind,
                "gates": [
                    {
                        "name": g.name,
                        "status": g.status.value,
                        "severity": g.severity.value,
                        "reason": g.reason,
                        "path": g.path,
                    }
                    for g in sorted(self.gates, key=lambda x: x.name)
                ],
                "stored_prose": self.stored_prose,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "ok": self.ok,
            "banner": self.banner,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "blocking": [g.name for g in self.blocking],
            "gates": [g.to_dict() for g in self.gates],
            "fingerprint": self.fingerprint(),
            "stored_prose": self.stored_prose,
        }


def pass_gate(
    name: str,
    *,
    severity: GateSeverity = GateSeverity.SEV2,
    reason: str = "ok",
    evidence: Optional[Sequence[GateEvidence]] = None,
    path: str = "",
    duration_ms: float = 0.0,
    metadata: Optional[Mapping[str, Any]] = None,
) -> GateResult:
    return GateResult(
        name=name,
        status=GateStatus.PASSED,
        severity=severity,
        reason=reason,
        evidence=list(evidence or ()),
        path=path,
        duration_ms=duration_ms,
        metadata=dict(metadata or {}),
    )


def fail_gate(
    name: str,
    *,
    severity: GateSeverity = GateSeverity.SEV2,
    reason: str,
    evidence: Optional[Sequence[GateEvidence]] = None,
    path: str = "",
    duration_ms: float = 0.0,
    metadata: Optional[Mapping[str, Any]] = None,
) -> GateResult:
    return GateResult(
        name=name,
        status=GateStatus.FAILED,
        severity=severity,
        reason=reason,
        evidence=list(evidence or ()),
        path=path,
        duration_ms=duration_ms,
        metadata=dict(metadata or {}),
    )


def error_gate(
    name: str,
    *,
    severity: GateSeverity = GateSeverity.SEV1,
    reason: str,
    evidence: Optional[Sequence[GateEvidence]] = None,
    path: str = "",
    duration_ms: float = 0.0,
    metadata: Optional[Mapping[str, Any]] = None,
) -> GateResult:
    return GateResult(
        name=name,
        status=GateStatus.ERROR,
        severity=severity,
        reason=reason,
        evidence=list(evidence or ()),
        path=path,
        duration_ms=duration_ms,
        metadata=dict(metadata or {}),
    )


def skip_gate(
    name: str,
    *,
    reason: str = "skipped",
    path: str = "",
) -> GateResult:
    return GateResult(
        name=name,
        status=GateStatus.SKIPPED,
        severity=GateSeverity.INFO,
        reason=reason,
        path=path,
    )


def collect_verdict(kind: str, gates: Iterable[GateResult]) -> Verdict:
    """Build a fail-closed verdict. Empty gate suites fail Sev1 closed."""
    gate_list = list(gates)
    if not gate_list:
        gate_list = [
            fail_gate(
                "suite.empty",
                severity=GateSeverity.SEV1,
                reason="gate suite produced zero results — fail closed",
            )
        ]
    return Verdict(kind=kind, gates=gate_list, stored_prose=0)


def require(
    condition: bool,
    name: str,
    *,
    severity: GateSeverity = GateSeverity.SEV2,
    on_pass: str = "ok",
    on_fail: str,
    evidence: Optional[Sequence[GateEvidence]] = None,
    path: str = "",
) -> GateResult:
    """Assert a boolean condition into a gate result."""
    if condition:
        return pass_gate(name, severity=severity, reason=on_pass, evidence=evidence, path=path)
    return fail_gate(name, severity=severity, reason=on_fail, evidence=evidence, path=path)


def merge_verdicts(kind: str, verdicts: Sequence[Verdict]) -> Verdict:
    """Merge multiple path verdicts; any blocking gate fails closed."""
    gates: List[GateResult] = []
    for v in verdicts:
        gates.extend(v.gates)
    return collect_verdict(kind, gates)


def severity_at_least(actual: GateSeverity, minimum: GateSeverity) -> bool:
    return actual.rank >= minimum.rank


def summarize_gates(gates: Sequence[GateResult]) -> Dict[str, Any]:
    by_sev: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for g in gates:
        by_sev[g.severity.value] = by_sev.get(g.severity.value, 0) + 1
        by_status[g.status.value] = by_status.get(g.status.value, 0) + 1
    return {
        "total": len(gates),
        "by_severity": by_sev,
        "by_status": by_status,
        "blocking_names": [g.name for g in gates if g.blocks],
    }


class GateSuite:
    """Builder that accumulates gates and materializes a verdict."""

    def __init__(self, kind: str):
        self.kind = kind
        self._gates: List[GateResult] = []

    def add(self, gate: GateResult) -> "GateSuite":
        self._gates.append(gate)
        return self

    def check(
        self,
        condition: bool,
        name: str,
        *,
        severity: GateSeverity = GateSeverity.SEV2,
        on_pass: str = "ok",
        on_fail: str,
        evidence: Optional[Sequence[GateEvidence]] = None,
        path: str = "",
    ) -> "GateSuite":
        self._gates.append(
            require(
                condition,
                name,
                severity=severity,
                on_pass=on_pass,
                on_fail=on_fail,
                evidence=evidence,
                path=path,
            )
        )
        return self

    def extend(self, gates: Iterable[GateResult]) -> "GateSuite":
        self._gates.extend(gates)
        return self

    def verdict(self) -> Verdict:
        return collect_verdict(self.kind, self._gates)

    @property
    def gates(self) -> List[GateResult]:
        return list(self._gates)


def gate_table(verdict: Verdict) -> str:
    """Render a compact human-readable gate table."""
    lines = [
        f"┌{'─'*28}┬{'─'*10}┬{'─'*8}┬{'─'*40}┐",
        f"│ {'Gate':<26} │ {'Status':<8} │ {'Sev':<6} │ {'Reason':<38} │",
        f"├{'─'*28}┼{'─'*10}┼{'─'*8}┼{'─'*40}┤",
    ]
    for g in verdict.gates:
        reason = (g.reason or "")[:38]
        lines.append(
            f"│ {g.name:<26} │ {g.status.value:<8} │ {g.severity.value:<6} │ {reason:<38} │"
        )
    lines.append(f"└{'─'*28}┴{'─'*10}┴{'─'*8}┴{'─'*40}┘")
    lines.append(verdict.banner)
    return "\n".join(lines)


__all__ = [
    "GateSeverity",
    "GateStatus",
    "GateEvidence",
    "GateResult",
    "Verdict",
    "GateSuite",
    "pass_gate",
    "fail_gate",
    "error_gate",
    "skip_gate",
    "collect_verdict",
    "require",
    "merge_verdicts",
    "severity_at_least",
    "summarize_gates",
    "gate_table",
]
