"""Fail-closed gates for the developer doctor / cockpit path (STU-TOOLS)."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from skeleton.developer.doctor_deepen import (
    DoctorDiff,
    DoctorSnapshot,
    collect_doctor_snapshot,
    diff_doctor,
    doctor_recommendations,
)
from skeleton.developer.gate_verdict import (
    GateEvidence,
    GateSeverity,
    GateSuite,
    Verdict,
    error_gate,
    merge_verdicts,
)
from skeleton.developer.surface_inventory import SurfacePath


DEFAULT_MEAN_SCORE_FLOOR = 0.55
DEFAULT_MAX_CRITICAL = 0
DEFAULT_MAX_WARNING = 5


def gate_doctor_snapshot(
    snapshot: DoctorSnapshot,
    *,
    mean_score_floor: float = DEFAULT_MEAN_SCORE_FLOOR,
    max_critical: int = DEFAULT_MAX_CRITICAL,
    max_warning: int = DEFAULT_MAX_WARNING,
) -> Verdict:
    suite = GateSuite("stu-tools-doctor")
    suite.check(
        snapshot.stored_prose == 0,
        "doctor.stored_prose_zero",
        severity=GateSeverity.SEV1,
        on_pass="stored_prose=0",
        on_fail=f"stored_prose={snapshot.stored_prose}",
        evidence=[GateEvidence("stored_prose", snapshot.stored_prose)],
    )
    suite.check(
        len(snapshot.inventory.by_path(SurfacePath.DOCTOR)) > 0,
        "doctor.domains_nonempty",
        severity=GateSeverity.SEV1,
        on_pass="doctor domains present",
        on_fail="doctor domains empty — fail closed",
    )
    missing = snapshot.missing_domains
    suite.check(
        not missing,
        "doctor.required_domains",
        severity=GateSeverity.SEV1,
        on_pass="all required domains present",
        on_fail=f"missing domains: {','.join(missing)}",
        evidence=[GateEvidence("missing", missing)],
    )
    crit = len(snapshot.critical_alerts)
    suite.check(
        crit <= max_critical,
        "doctor.critical_alerts",
        severity=GateSeverity.SEV1,
        on_pass=f"critical={crit}<={max_critical}",
        on_fail=f"critical={crit}>{max_critical}",
        evidence=[GateEvidence("critical", crit)],
    )
    warn = len(snapshot.warning_alerts)
    suite.check(
        warn <= max_warning,
        "doctor.warning_alerts",
        severity=GateSeverity.SEV2,
        on_pass=f"warning={warn}<={max_warning}",
        on_fail=f"warning={warn}>{max_warning}",
        evidence=[GateEvidence("warning", warn)],
    )
    suite.check(
        snapshot.mean_score >= mean_score_floor,
        "doctor.mean_score_floor",
        severity=GateSeverity.SEV2,
        on_pass=f"mean={snapshot.mean_score}>={mean_score_floor}",
        on_fail=f"mean={snapshot.mean_score}<{mean_score_floor}",
        evidence=[GateEvidence("mean_score", snapshot.mean_score)],
    )
    suite.check(
        snapshot.cockpit_mean >= 0.7,
        "doctor.cockpit_healthy",
        severity=GateSeverity.SEV2,
        on_pass=f"cockpit_mean={snapshot.cockpit_mean}",
        on_fail=f"cockpit_mean={snapshot.cockpit_mean}<0.7",
        evidence=[GateEvidence("cockpit_mean", snapshot.cockpit_mean)],
    )
    bad_knobs = [
        s.name
        for s in snapshot.inventory.by_path(SurfacePath.COCKPIT)
        if s.name != "stored_prose" and s.score < 0.7
    ]
    suite.check(
        not bad_knobs,
        "doctor.cockpit_knobs_in_range",
        severity=GateSeverity.SEV2,
        on_pass="cockpit knobs in range",
        on_fail=f"out_of_range:{','.join(bad_knobs)}",
        evidence=[GateEvidence("bad_knobs", bad_knobs)],
    )
    return suite.verdict()


def gate_doctor_diff(diff: DoctorDiff) -> Verdict:
    suite = GateSuite("stu-tools-doctor-diff")
    suite.check(
        not diff.regressed,
        "doctor.diff.no_regression",
        severity=GateSeverity.SEV2,
        on_pass="no doctor regression",
        on_fail=(
            f"regressed critical {diff.critical_before}->{diff.critical_after} "
            f"domains={diff.worsened_domains}"
        ),
        evidence=[
            GateEvidence("critical_before", diff.critical_before),
            GateEvidence("critical_after", diff.critical_after),
            GateEvidence("worsened", list(diff.worsened_domains)),
        ],
    )
    suite.check(
        diff.critical_after <= diff.critical_before,
        "doctor.diff.critical_not_up",
        severity=GateSeverity.SEV1,
        on_pass="critical alerts not increased",
        on_fail=f"critical rose {diff.critical_before}->{diff.critical_after}",
    )
    return suite.verdict()


def run_doctor_gates(
    organism: Any = None,
    *,
    card: Optional[Mapping[str, Any]] = None,
    previous: Optional[DoctorSnapshot] = None,
    mean_score_floor: float = DEFAULT_MEAN_SCORE_FLOOR,
    max_critical: int = DEFAULT_MAX_CRITICAL,
    max_warning: int = DEFAULT_MAX_WARNING,
) -> Dict[str, Any]:
    """Run doctor deepen + gates. Never returns ok=1 when Sev1/Sev2 red."""
    try:
        snapshot = collect_doctor_snapshot(organism, card=card)
    except Exception as exc:
        verdict = GateSuite("stu-tools-doctor").add(
            error_gate(
                "doctor.collect",
                severity=GateSeverity.SEV1,
                reason=f"doctor collection crashed: {exc}",
            )
        ).verdict()
        return {
            "kind": "stu-tools-doctor-gates",
            "ok": verdict.ok,
            "banner": verdict.banner,
            "verdict": verdict.to_dict(),
            "stored_prose": 0,
        }

    report = {
        "kind": "stu-tools-doctor-report",
        "snapshot": snapshot.to_dict(),
        "weakest": [
            s.to_dict()
            for s in snapshot.inventory.weakest(fraction=0.15, path=SurfacePath.DOCTOR)
        ],
        "recommendations": doctor_recommendations(snapshot),
        "stored_prose": snapshot.stored_prose,
    }
    verdict = gate_doctor_snapshot(
        snapshot,
        mean_score_floor=mean_score_floor,
        max_critical=max_critical,
        max_warning=max_warning,
    )
    if previous is not None:
        diff = diff_doctor(previous, snapshot)
        report["diff"] = diff.to_dict()
        verdict = merge_verdicts("stu-tools-doctor", [verdict, gate_doctor_diff(diff)])
    return {
        "kind": "stu-tools-doctor-gates",
        "ok": verdict.ok,
        "banner": verdict.banner,
        "verdict": verdict.to_dict(),
        "report": report,
        "stored_prose": snapshot.stored_prose,
    }


def assert_doctor_green(result: Mapping[str, Any]) -> None:
    if int(result.get("ok") or 0) != 1:
        banner = result.get("banner") or (result.get("verdict") or {}).get("banner") or "red"
        raise AssertionError(f"doctor gates red: {banner}")


__all__ = [
    "gate_doctor_snapshot",
    "gate_doctor_diff",
    "run_doctor_gates",
    "assert_doctor_green",
    "DEFAULT_MEAN_SCORE_FLOOR",
    "DEFAULT_MAX_CRITICAL",
    "DEFAULT_MAX_WARNING",
]
