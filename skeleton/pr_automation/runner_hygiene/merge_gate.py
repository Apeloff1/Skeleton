"""Merge-gate ledger hygiene and gate-matrix evaluation.

Strengthens gates without adding mutation powers. Consumes admission evidence
and durable ledger state to decide whether a candidate remains gate-clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from .admission import AdmissionDecision, evaluate_admission
from .admission_evidence import AdmissionEvidence
from .observe_mode import ObservePolicy
from .types import (
    Finding,
    GateState,
    HygieneMode,
    HygienePolicy,
    HygieneVerdict,
    canonical_json,
    fingerprint,
    parse_timestamp,
    utc_now,
)


@dataclass(frozen=True, slots=True)
class GateRequirementSpec:
    name: str
    required: bool = True
    security: bool = False
    allow_skipped: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("gate name required")


DEFAULT_GATE_MATRIX: tuple[GateRequirementSpec, ...] = (
    GateRequirementSpec("CI/CD"),
    GateRequirementSpec("Merge Readiness"),
    GateRequirementSpec("Secret scanning", security=True),
    GateRequirementSpec("Malware Gate", security=True),
    GateRequirementSpec("Repository Hygiene Gate"),
    GateRequirementSpec("Artifact Policy"),
    GateRequirementSpec("Provenance Policy"),
    GateRequirementSpec("PR Hygiene"),
    GateRequirementSpec("Workflow Input Security", security=True, required=False),
    GateRequirementSpec("Dependency Review", security=True, required=False),
    GateRequirementSpec("Backend Quality", required=False),
    GateRequirementSpec("Frontier Contracts", required=False),
)


@dataclass(frozen=True, slots=True)
class GateMatrixResult:
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    failing: tuple[str, ...]
    pending: tuple[str, ...]
    unknown: tuple[str, ...]
    skipped_allowed: tuple[str, ...]
    findings: tuple[Finding, ...]

    @property
    def clean(self) -> bool:
        return not self.missing and not self.failing and not self.pending and not self.unknown


def evaluate_gate_matrix(
    states: Mapping[str, GateState],
    matrix: Sequence[GateRequirementSpec] = DEFAULT_GATE_MATRIX,
    *,
    require_optional_security: bool = False,
) -> GateMatrixResult:
    satisfied: list[str] = []
    missing: list[str] = []
    failing: list[str] = []
    pending: list[str] = []
    unknown: list[str] = []
    skipped_allowed: list[str] = []
    findings: list[Finding] = []

    for spec in matrix:
        required = spec.required or (require_optional_security and spec.security)
        state = states.get(spec.name)
        if state is None:
            if required:
                missing.append(spec.name)
                findings.append(
                    Finding(
                        code="merge_gate.missing",
                        severity="high" if not spec.security else "critical",
                        message=f"required gate {spec.name!r} missing",
                        subject=spec.name,
                    )
                )
            continue
        if state is GateState.SUCCESS:
            satisfied.append(spec.name)
            continue
        if state is GateState.SKIPPED and spec.allow_skipped:
            skipped_allowed.append(spec.name)
            continue
        if state is GateState.FAILURE:
            failing.append(spec.name)
            findings.append(
                Finding(
                    code="merge_gate.failing",
                    severity="critical" if spec.security else "high",
                    message=f"gate {spec.name!r} failing",
                    subject=spec.name,
                )
            )
        elif state is GateState.PENDING:
            pending.append(spec.name)
            findings.append(
                Finding(
                    code="merge_gate.pending",
                    severity="medium",
                    message=f"gate {spec.name!r} pending",
                    subject=spec.name,
                )
            )
        elif state is GateState.MISSING:
            missing.append(spec.name)
            findings.append(
                Finding(
                    code="merge_gate.missing",
                    severity="high",
                    message=f"gate {spec.name!r} missing",
                    subject=spec.name,
                )
            )
        else:
            unknown.append(spec.name)
            findings.append(
                Finding(
                    code="merge_gate.unknown",
                    severity="critical",
                    message=f"gate {spec.name!r} unknown; fail closed",
                    subject=spec.name,
                )
            )
    return GateMatrixResult(
        satisfied=tuple(satisfied),
        missing=tuple(missing),
        failing=tuple(failing),
        pending=tuple(pending),
        unknown=tuple(unknown),
        skipped_allowed=tuple(skipped_allowed),
        findings=tuple(findings),
    )


@dataclass(frozen=True, slots=True)
class StabilityWindow:
    earliest_success_at: str | None
    now: str
    required_seconds: int

    @property
    def elapsed_seconds(self) -> float | None:
        start = parse_timestamp(self.earliest_success_at)
        now = parse_timestamp(self.now)
        if start is None or now is None:
            return None
        return max(0.0, (now - start).total_seconds())

    @property
    def stable(self) -> bool | None:
        elapsed = self.elapsed_seconds
        if elapsed is None:
            return None
        return elapsed >= self.required_seconds


def assess_stability(
    *,
    success_timestamps: Sequence[str | None],
    required_seconds: int = 30,
    now: datetime | None = None,
) -> tuple[StabilityWindow, tuple[Finding, ...]]:
    stamp = (now or utc_now()).astimezone(timezone.utc).isoformat()
    parsed = [parse_timestamp(ts) for ts in success_timestamps if ts]
    if not parsed:
        window = StabilityWindow(
            earliest_success_at=None, now=stamp, required_seconds=required_seconds
        )
        return window, (
            Finding(
                code="merge_gate.stability_unknown",
                severity="high",
                message="no success timestamps available for stability window",
            ),
        )
    earliest = min(parsed).isoformat()
    window = StabilityWindow(
        earliest_success_at=earliest, now=stamp, required_seconds=required_seconds
    )
    if window.stable is None:
        return window, (
            Finding(
                code="merge_gate.stability_unknown",
                severity="high",
                message="stability window could not be computed",
            ),
        )
    if not window.stable:
        return window, (
            Finding(
                code="merge_gate.stability_hold",
                severity="medium",
                message=(
                    f"stability elapsed {window.elapsed_seconds:.1f}s "
                    f"< required {required_seconds}s"
                ),
            ),
        )
    return window, ()


@dataclass(frozen=True, slots=True)
class MergeGateDecision:
    verdict: HygieneVerdict
    reasons: tuple[str, ...]
    findings: tuple[Finding, ...]
    matrix: GateMatrixResult
    admission: AdmissionDecision | None
    stability: StabilityWindow | None
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "findings": [f.to_dict() for f in self.findings],
            "matrix": {
                "satisfied": list(self.matrix.satisfied),
                "missing": list(self.matrix.missing),
                "failing": list(self.matrix.failing),
                "pending": list(self.matrix.pending),
                "unknown": list(self.matrix.unknown),
            },
            "admission_verdict": None if self.admission is None else self.admission.verdict.value,
            "stability_elapsed": None
            if self.stability is None
            else self.stability.elapsed_seconds,
            "fingerprint": self.fingerprint,
        }


def evaluate_merge_gate(
    *,
    evidence: AdmissionEvidence,
    policy: HygienePolicy,
    observe: ObservePolicy | None = None,
    matrix: Sequence[GateRequirementSpec] = DEFAULT_GATE_MATRIX,
    stability_seconds: int = 30,
    success_timestamps: Sequence[str | None] = (),
    require_optional_security: bool = False,
) -> MergeGateDecision:
    admission = evaluate_admission(evidence=evidence, policy=policy, observe=observe)
    matrix_result = evaluate_gate_matrix(
        evidence.checks.states,
        matrix,
        require_optional_security=require_optional_security,
    )
    stability, stability_findings = assess_stability(
        success_timestamps=success_timestamps,
        required_seconds=stability_seconds,
    )
    findings = list(admission.findings) + list(matrix_result.findings) + list(stability_findings)

    verdict = admission.verdict
    reasons = list(admission.reasons)
    if not matrix_result.clean:
        if matrix_result.unknown or matrix_result.failing or matrix_result.missing:
            if verdict not in {HygieneVerdict.DENY, HygieneVerdict.INCOMPLETE}:
                verdict = HygieneVerdict.DENY
            reasons.append("merge_gate_matrix_denied")
        elif matrix_result.pending:
            if verdict is HygieneVerdict.ALLOW:
                verdict = HygieneVerdict.HOLD
            reasons.append("merge_gate_matrix_pending")
    if stability.stable is False and verdict is HygieneVerdict.ALLOW:
        verdict = HygieneVerdict.HOLD
        reasons.append("stability_hold")
    if stability.stable is None and verdict is HygieneVerdict.ALLOW:
        verdict = HygieneVerdict.DENY
        reasons.append("stability_unknown")

    fp = fingerprint(
        {
            "admission": admission.to_dict(),
            "matrix": {
                "missing": list(matrix_result.missing),
                "failing": list(matrix_result.failing),
                "pending": list(matrix_result.pending),
                "unknown": list(matrix_result.unknown),
            },
            "stability": {
                "earliest": stability.earliest_success_at,
                "required": stability.required_seconds,
                "elapsed": stability.elapsed_seconds,
            },
        }
    )
    return MergeGateDecision(
        verdict=verdict,
        reasons=tuple(dict.fromkeys(reasons)),
        findings=tuple(findings),
        matrix=matrix_result,
        admission=admission,
        stability=stability,
        fingerprint=fp,
    )


__all__ = [
    "DEFAULT_GATE_MATRIX",
    "GateMatrixResult",
    "GateRequirementSpec",
    "MergeGateDecision",
    "StabilityWindow",
    "assess_stability",
    "evaluate_gate_matrix",
    "evaluate_merge_gate",
]
