"""Fail-closed gates for the developer health path (STU-TOOLS).

Sev1: empty suite, explorer crash, stored_prose nonzero, required surfaces missing
      with failed overall.
Sev2: degraded overall, mean score below floor, failed subsystem count, regression.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from skeleton.developer.gate_verdict import (
    GateEvidence,
    GateSeverity,
    GateSuite,
    Verdict,
    error_gate,
    fail_gate,
    pass_gate,
)
from skeleton.developer.health_deepen import (
    HealthDiff,
    HealthSnapshot,
    collect_health_snapshot,
    deepen_health_report,
    snapshot_from_summary,
)


DEFAULT_MEAN_SCORE_FLOOR = 0.55
DEFAULT_MAX_FAILED = 0
DEFAULT_MAX_DEGRADED = 3


def gate_health_snapshot(
    snapshot: HealthSnapshot,
    *,
    mean_score_floor: float = DEFAULT_MEAN_SCORE_FLOOR,
    max_failed: int = DEFAULT_MAX_FAILED,
    max_degraded: int = DEFAULT_MAX_DEGRADED,
) -> Verdict:
    suite = GateSuite("stu-tools-health")

    # Sev1: stored_prose law
    suite.check(
        snapshot.stored_prose == 0,
        "health.stored_prose_zero",
        severity=GateSeverity.SEV1,
        on_pass="stored_prose=0",
        on_fail=f"stored_prose={snapshot.stored_prose}",
        evidence=[GateEvidence("stored_prose", snapshot.stored_prose)],
    )

    # Sev1: must have at least one subsystem card / surface
    suite.check(
        snapshot.total_subsystems > 0 or len(snapshot.inventory.surfaces) > 0,
        "health.nonempty",
        severity=GateSeverity.SEV1,
        on_pass="surfaces present",
        on_fail="health snapshot empty — fail closed",
    )

    missing = snapshot.missing_required
    suite.check(
        not missing,
        "health.required_surfaces",
        severity=GateSeverity.SEV1,
        on_pass="all required surfaces present",
        on_fail=f"missing required surfaces: {','.join(missing)}",
        evidence=[GateEvidence("missing", missing)],
    )

    failed = int(snapshot.status_breakdown.get("failed") or 0)
    suite.check(
        failed <= max_failed,
        "health.failed_count",
        severity=GateSeverity.SEV1 if failed > max_failed else GateSeverity.SEV2,
        on_pass=f"failed={failed}<={max_failed}",
        on_fail=f"failed={failed}>{max_failed}",
        evidence=[GateEvidence("failed", failed), GateEvidence("max_failed", max_failed)],
    )

    degraded = int(snapshot.status_breakdown.get("degraded") or 0)
    suite.check(
        degraded <= max_degraded,
        "health.degraded_count",
        severity=GateSeverity.SEV2,
        on_pass=f"degraded={degraded}<={max_degraded}",
        on_fail=f"degraded={degraded}>{max_degraded}",
        evidence=[GateEvidence("degraded", degraded)],
    )

    suite.check(
        snapshot.overall != "failed",
        "health.overall_not_failed",
        severity=GateSeverity.SEV1,
        on_pass=f"overall={snapshot.overall}",
        on_fail="overall=failed",
        evidence=[GateEvidence("overall", snapshot.overall)],
    )

    suite.check(
        snapshot.mean_score >= mean_score_floor,
        "health.mean_score_floor",
        severity=GateSeverity.SEV2,
        on_pass=f"mean_score={snapshot.mean_score}>={mean_score_floor}",
        on_fail=f"mean_score={snapshot.mean_score}<{mean_score_floor}",
        evidence=[
            GateEvidence("mean_score", snapshot.mean_score),
            GateEvidence("floor", mean_score_floor),
        ],
    )

    suite.check(
        snapshot.phases_booted >= 1,
        "health.phases_booted",
        severity=GateSeverity.SEV2,
        on_pass=f"phases_booted={snapshot.phases_booted}",
        on_fail="no phases booted",
    )

    return suite.verdict()


def gate_health_diff(diff: HealthDiff) -> Verdict:
    suite = GateSuite("stu-tools-health-diff")
    suite.check(
        not diff.regressed,
        "health.diff.no_regression",
        severity=GateSeverity.SEV2,
        on_pass="no health regression",
        on_fail=f"regressed: worsened={diff.worsened} score_delta={diff.score_delta}",
        evidence=[
            GateEvidence("worsened", list(diff.worsened)),
            GateEvidence("score_delta", diff.score_delta),
            GateEvidence("overall_before", diff.overall_before),
            GateEvidence("overall_after", diff.overall_after),
        ],
    )
    suite.check(
        len(diff.removed) == 0,
        "health.diff.no_removals",
        severity=GateSeverity.SEV2,
        on_pass="no surfaces removed",
        on_fail=f"removed surfaces: {','.join(diff.removed)}",
        evidence=[GateEvidence("removed", list(diff.removed))],
    )
    return suite.verdict()


def run_health_gates(
    summary: Optional[Mapping[str, Any]] = None,
    *,
    explorer: Any = None,
    previous: Optional[HealthSnapshot] = None,
    mean_score_floor: float = DEFAULT_MEAN_SCORE_FLOOR,
    max_failed: int = DEFAULT_MAX_FAILED,
    max_degraded: int = DEFAULT_MAX_DEGRADED,
) -> Dict[str, Any]:
    """Run health deepen + gates. Never returns ok=1 when Sev1/Sev2 red."""
    from skeleton.developer.gate_verdict import Verdict, merge_verdicts
    from skeleton.developer.health_deepen import (
        diff_health,
        health_recommendations,
    )
    from skeleton.developer.surface_inventory import SurfacePath

    try:
        if summary is None:
            snapshot = collect_health_snapshot(explorer)
        else:
            snapshot = snapshot_from_summary(summary)
    except Exception as exc:  # noqa: BLE001 — fail closed
        verdict = Verdict(
            kind="stu-tools-health",
            gates=[
                error_gate(
                    "health.collect",
                    severity=GateSeverity.SEV1,
                    reason=f"health collection crashed: {exc}",
                )
            ],
        )
        return {
            "kind": "stu-tools-health-gates",
            "ok": 0,
            "verdict": verdict.to_dict(),
            "report": None,
            "banner": verdict.banner,
            "error": str(exc),
            "stored_prose": 0,
        }

    report: Dict[str, Any] = {
        "kind": "stu-tools-health-report",
        "snapshot": snapshot.to_dict(),
        "weakest": [
            s.to_dict()
            for s in snapshot.inventory.weakest(fraction=0.15, path=SurfacePath.HEALTH)
        ],
        "recommendations": health_recommendations(snapshot),
        "stored_prose": 0,
    }

    verdict = gate_health_snapshot(
        snapshot,
        mean_score_floor=mean_score_floor,
        max_failed=max_failed,
        max_degraded=max_degraded,
    )
    if previous is not None:
        diff = diff_health(previous, snapshot)
        report["diff"] = diff.to_dict()
        verdict = merge_verdicts("stu-tools-health", [verdict, gate_health_diff(diff)])

    return {
        "kind": "stu-tools-health-gates",
        "ok": verdict.ok,
        "verdict": verdict.to_dict(),
        "report": report,
        "banner": verdict.banner,
        "stored_prose": 0,
    }


def assert_health_green(result: Mapping[str, Any]) -> None:
    """Raise AssertionError if health gates are red — for regression tests."""
    if int(result.get("ok") or 0) != 1:
        banner = result.get("banner") or (result.get("verdict") or {}).get("banner")
        raise AssertionError(f"health gates red: {banner}")


__all__ = [
    "DEFAULT_MEAN_SCORE_FLOOR",
    "DEFAULT_MAX_FAILED",
    "DEFAULT_MAX_DEGRADED",
    "gate_health_snapshot",
    "gate_health_diff",
    "run_health_gates",
    "assert_health_green",
]
