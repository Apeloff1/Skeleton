"""Fail-closed gates for the STU-TOOLS cockpit path."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from skeleton.developer.cockpit_deepen import (
    CockpitSnapshot,
    apply_retune,
    cockpit_diff,
    deepen_cockpit_report,
    retune_plan,
    snapshot_cockpit,
)
from skeleton.developer.gate_verdict import (
    GateEvidence,
    GateSeverity,
    GateSuite,
    Verdict,
    error_gate,
    merge_verdicts,
)


DEFAULT_MEAN_FLOOR = 0.7


def gate_cockpit_snapshot(
    snapshot: CockpitSnapshot,
    *,
    mean_floor: float = DEFAULT_MEAN_FLOOR,
) -> Verdict:
    suite = GateSuite("stu-tools-cockpit")
    suite.check(
        snapshot.stored_prose == 0,
        "cockpit.stored_prose_zero",
        severity=GateSeverity.SEV1,
        on_pass="stored_prose=0",
        on_fail=f"stored_prose={snapshot.stored_prose}",
        evidence=[GateEvidence("stored_prose", snapshot.stored_prose)],
    )
    suite.check(
        bool(snapshot.knobs),
        "cockpit.knobs_nonempty",
        severity=GateSeverity.SEV1,
        on_pass="knobs present",
        on_fail="cockpit knobs empty — fail closed",
    )
    suite.check(
        not snapshot.out_of_range,
        "cockpit.all_in_range",
        severity=GateSeverity.SEV2,
        on_pass="all knobs in range",
        on_fail=f"out_of_range:{','.join(snapshot.out_of_range)}",
        evidence=[GateEvidence("out_of_range", list(snapshot.out_of_range))],
    )
    suite.check(
        snapshot.mean_score >= mean_floor,
        "cockpit.mean_score_floor",
        severity=GateSeverity.SEV2,
        on_pass=f"mean={snapshot.mean_score}>={mean_floor}",
        on_fail=f"mean={snapshot.mean_score}<{mean_floor}",
    )
    return suite.verdict()


def gate_cockpit_diff(diff: Mapping[str, Any]) -> Verdict:
    suite = GateSuite("stu-tools-cockpit-diff")
    suite.check(
        not bool(diff.get("regressed")),
        "cockpit.diff.no_regression",
        severity=GateSeverity.SEV2,
        on_pass="no cockpit regression",
        on_fail=f"worsened={diff.get('worsened')}",
        evidence=[GateEvidence("worsened", list(diff.get("worsened") or []))],
    )
    return suite.verdict()


def run_cockpit_gates(
    knobs: Optional[Mapping[str, Any]] = None,
    *,
    previous: Optional[CockpitSnapshot] = None,
    auto_retune: bool = False,
    mean_floor: float = DEFAULT_MEAN_FLOOR,
) -> Dict[str, Any]:
    try:
        snap = snapshot_cockpit(knobs)
    except Exception as exc:  # noqa: BLE001
        verdict = GateSuite("stu-tools-cockpit").add(
            error_gate("cockpit.collect", severity=GateSeverity.SEV1, reason=str(exc))
        ).verdict()
        return {
            "kind": "stu-tools-cockpit-gates",
            "ok": verdict.ok,
            "banner": verdict.banner,
            "verdict": verdict.to_dict(),
            "stored_prose": 0,
        }

    report = deepen_cockpit_report(knobs)
    verdict = gate_cockpit_snapshot(snap, mean_floor=mean_floor)
    applied = None
    if auto_retune and not verdict.ok:
        plan = retune_plan(snap)
        applied = apply_retune(knobs or {}, plan)
        after = snapshot_cockpit(applied, source="retune")
        report["after_retune"] = after.to_dict()
        verdict = gate_cockpit_snapshot(after, mean_floor=mean_floor)
        snap = after
    if previous is not None:
        diff = cockpit_diff(previous, snap)
        report["diff"] = diff
        verdict = merge_verdicts("stu-tools-cockpit", [verdict, gate_cockpit_diff(diff)])
    return {
        "kind": "stu-tools-cockpit-gates",
        "ok": verdict.ok,
        "banner": verdict.banner,
        "verdict": verdict.to_dict(),
        "report": report,
        "applied_knobs": applied,
        "stored_prose": snap.stored_prose,
    }


def assert_cockpit_green(result: Mapping[str, Any]) -> None:
    if int(result.get("ok") or 0) != 1:
        raise AssertionError(f"cockpit gates red: {result.get('banner')}")


__all__ = [
    "gate_cockpit_snapshot",
    "gate_cockpit_diff",
    "run_cockpit_gates",
    "assert_cockpit_green",
    "DEFAULT_MEAN_FLOOR",
]
