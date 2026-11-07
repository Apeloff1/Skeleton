"""Fail-closed gates for the developer visualize path (STU-TOOLS)."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from skeleton.developer.gate_verdict import (
    GateEvidence,
    GateSeverity,
    GateSuite,
    Verdict,
    error_gate,
)
from skeleton.developer.surface_inventory import SurfacePath
from skeleton.developer.visualize_deepen import (
    VisualizeSnapshot,
    deepen_visualize_report,
    snapshot_visualize,
)


DEFAULT_MEAN_SCORE_FLOOR = 0.5
DEFAULT_MAX_ORPHANS = 2
DEFAULT_MAX_DANGLING = 0


def gate_visualize_snapshot(
    snapshot: VisualizeSnapshot,
    *,
    mean_score_floor: float = DEFAULT_MEAN_SCORE_FLOOR,
    max_orphans: int = DEFAULT_MAX_ORPHANS,
    max_dangling: int = DEFAULT_MAX_DANGLING,
) -> Verdict:
    suite = GateSuite("stu-tools-visualize")
    suite.check(
        snapshot.stored_prose == 0,
        "visualize.stored_prose_zero",
        severity=GateSeverity.SEV1,
        on_pass="stored_prose=0",
        on_fail=f"stored_prose={snapshot.stored_prose}",
    )
    suite.check(
        snapshot.stats.component_count > 0,
        "visualize.nonempty",
        severity=GateSeverity.SEV1,
        on_pass="components present",
        on_fail="visualize topology empty — fail closed",
    )
    missing = snapshot.inventory.required_missing(SurfacePath.VISUALIZE)
    suite.check(
        not missing,
        "visualize.required_fields",
        severity=GateSeverity.SEV1,
        on_pass="required visualize fields present",
        on_fail=f"missing fields: {','.join(missing)}",
        evidence=[GateEvidence("missing", missing)],
    )
    dangling_n = len(snapshot.stats.dangling_wires)
    suite.check(
        dangling_n <= max_dangling,
        "visualize.dangling_wires",
        severity=GateSeverity.SEV1 if dangling_n > max_dangling else GateSeverity.SEV2,
        on_pass=f"dangling={dangling_n}<={max_dangling}",
        on_fail=f"dangling={dangling_n}>{max_dangling}",
        evidence=[GateEvidence("dangling", list(snapshot.stats.dangling_wires))],
    )
    orphan_n = len(snapshot.stats.orphan_components)
    suite.check(
        orphan_n <= max_orphans,
        "visualize.orphan_components",
        severity=GateSeverity.SEV2,
        on_pass=f"orphans={orphan_n}<={max_orphans}",
        on_fail=f"orphans={orphan_n}>{max_orphans}",
        evidence=[GateEvidence("orphans", list(snapshot.stats.orphan_components))],
    )
    suite.check(
        snapshot.mean_score >= mean_score_floor,
        "visualize.mean_score_floor",
        severity=GateSeverity.SEV2,
        on_pass=f"mean={snapshot.mean_score}>={mean_score_floor}",
        on_fail=f"mean={snapshot.mean_score}<{mean_score_floor}",
    )
    if snapshot.stats.component_count > 1:
        suite.check(
            snapshot.stats.connected,
            "visualize.connected",
            severity=GateSeverity.SEV2,
            on_pass="topology connected",
            on_fail="topology disconnected",
        )
    return suite.verdict()


def run_visualize_gates(
    blueprint: Any = None,
    *,
    topology: Optional[Mapping[str, Any]] = None,
    name: str = "",
    mean_score_floor: float = DEFAULT_MEAN_SCORE_FLOOR,
    max_orphans: int = DEFAULT_MAX_ORPHANS,
    max_dangling: int = DEFAULT_MAX_DANGLING,
) -> Dict[str, Any]:
    try:
        snapshot = snapshot_visualize(blueprint, topology=topology, name=name)
    except Exception as exc:
        verdict = GateSuite("stu-tools-visualize").add(
            error_gate(
                "visualize.collect",
                severity=GateSeverity.SEV1,
                reason=f"visualize collection crashed: {exc}",
            )
        ).verdict()
        return {
            "kind": "stu-tools-visualize-gates",
            "ok": verdict.ok,
            "banner": verdict.banner,
            "verdict": verdict.to_dict(),
            "stored_prose": 0,
        }
    report = deepen_visualize_report(blueprint, topology=topology, name=name)
    verdict = gate_visualize_snapshot(
        snapshot,
        mean_score_floor=mean_score_floor,
        max_orphans=max_orphans,
        max_dangling=max_dangling,
    )
    return {
        "kind": "stu-tools-visualize-gates",
        "ok": verdict.ok,
        "banner": verdict.banner,
        "verdict": verdict.to_dict(),
        "report": report,
        "stored_prose": 0,
    }


def assert_visualize_green(result: Mapping[str, Any]) -> None:
    if int(result.get("ok") or 0) != 1:
        banner = result.get("banner") or (result.get("verdict") or {}).get("banner") or "red"
        raise AssertionError(f"visualize gates red: {banner}")


__all__ = [
    "gate_visualize_snapshot",
    "run_visualize_gates",
    "assert_visualize_green",
    "DEFAULT_MEAN_SCORE_FLOOR",
    "DEFAULT_MAX_ORPHANS",
    "DEFAULT_MAX_DANGLING",
]
