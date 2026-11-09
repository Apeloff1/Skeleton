"""Deepen the developer CLI health path with scoring, snapshots, and diffs.

Wraps SubsystemExplorer summaries into a richer health report that feeds
fail-closed health gates and the STU-TOOLS pipeline.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from skeleton.developer.surface_inventory import (
    SurfaceInventory,
    SurfacePath,
    inventory_from_health_summary,
)


HEALTH_OVERALL_RANK = {
    "healthy": 3,
    "degraded": 2,
    "failed": 1,
    "unknown": 0,
}


@dataclass
class HealthSnapshot:
    """Point-in-time health path snapshot."""

    overall: str
    total_subsystems: int
    phases_booted: int
    status_breakdown: Dict[str, int]
    inventory: SurfaceInventory
    cards: List[Dict[str, Any]] = field(default_factory=list)
    collected_at: float = field(default_factory=time.time)
    source: str = "explorer"
    stored_prose: int = 0

    @property
    def mean_score(self) -> float:
        return self.inventory.mean_score(SurfacePath.HEALTH)

    @property
    def missing_required(self) -> List[str]:
        return self.inventory.required_missing(SurfacePath.HEALTH)

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "overall": self.overall,
                "total": self.total_subsystems,
                "phases": self.phases_booted,
                "breakdown": self.status_breakdown,
                "inv": self.inventory.fingerprint(),
                "stored_prose": self.stored_prose,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-health-snapshot",
            "overall": self.overall,
            "total_subsystems": self.total_subsystems,
            "phases_booted": self.phases_booted,
            "status_breakdown": dict(self.status_breakdown),
            "mean_score": self.mean_score,
            "missing_required": self.missing_required,
            "inventory": self.inventory.to_dict(),
            "cards": list(self.cards),
            "collected_at": self.collected_at,
            "source": self.source,
            "fingerprint": self.fingerprint(),
            "stored_prose": self.stored_prose,
        }


@dataclass
class HealthDiff:
    """Diff between two health snapshots."""

    before_fp: str
    after_fp: str
    overall_before: str
    overall_after: str
    score_delta: float
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    worsened: List[str] = field(default_factory=list)
    improved: List[str] = field(default_factory=list)

    @property
    def regressed(self) -> bool:
        before_rank = HEALTH_OVERALL_RANK.get(self.overall_before, 0)
        after_rank = HEALTH_OVERALL_RANK.get(self.overall_after, 0)
        return after_rank < before_rank or self.score_delta < -0.05 or bool(self.worsened)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-health-diff",
            "before_fp": self.before_fp,
            "after_fp": self.after_fp,
            "overall_before": self.overall_before,
            "overall_after": self.overall_after,
            "score_delta": round(self.score_delta, 4),
            "added": list(self.added),
            "removed": list(self.removed),
            "worsened": list(self.worsened),
            "improved": list(self.improved),
            "regressed": self.regressed,
            "stored_prose": 0,
        }


def snapshot_from_summary(summary: Mapping[str, Any], *, source: str = "explorer") -> HealthSnapshot:
    """Build a health snapshot from a summary mapping."""
    if not isinstance(summary, Mapping):
        raise TypeError("health summary must be a mapping")
    inventory = inventory_from_health_summary(summary)
    overall = str(summary.get("overall") or "unknown")
    # If inventory shows missing required or failed cards, never claim healthy.
    failed = int((summary.get("status_breakdown") or {}).get("failed") or 0)
    degraded = int((summary.get("status_breakdown") or {}).get("degraded") or 0)
    if inventory.required_missing(SurfacePath.HEALTH) or failed:
        overall = "failed" if (failed or inventory.required_missing(SurfacePath.HEALTH)) else overall
    elif degraded and overall == "healthy":
        overall = "degraded"
    return HealthSnapshot(
        overall=overall,
        total_subsystems=int(summary.get("total_subsystems") or len(summary.get("cards") or [])),
        phases_booted=int(summary.get("phases_booted") or 0),
        status_breakdown=dict(summary.get("status_breakdown") or {}),
        inventory=inventory,
        cards=[dict(c) for c in (summary.get("cards") or []) if isinstance(c, Mapping)],
        source=source,
        stored_prose=0,
    )


def collect_health_snapshot(explorer: Any = None) -> HealthSnapshot:
    """Collect a live health snapshot via SubsystemExplorer."""
    if explorer is None:
        from skeleton.developer.wizard import SubsystemExplorer
        explorer = SubsystemExplorer()
    summary = explorer.summary()
    return snapshot_from_summary(summary, source="SubsystemExplorer")


def diff_health(before: HealthSnapshot, after: HealthSnapshot) -> HealthDiff:
    before_map = {s.name: s for s in before.inventory.by_path(SurfacePath.HEALTH)}
    after_map = {s.name: s for s in after.inventory.by_path(SurfacePath.HEALTH)}
    added = sorted(set(after_map) - set(before_map))
    removed = sorted(set(before_map) - set(after_map))
    worsened: List[str] = []
    improved: List[str] = []
    for name in sorted(set(before_map) & set(after_map)):
        delta = after_map[name].score - before_map[name].score
        if delta <= -0.05:
            worsened.append(name)
        elif delta >= 0.05:
            improved.append(name)
    return HealthDiff(
        before_fp=before.fingerprint(),
        after_fp=after.fingerprint(),
        overall_before=before.overall,
        overall_after=after.overall,
        score_delta=round(after.mean_score - before.mean_score, 4),
        added=added,
        removed=removed,
        worsened=worsened,
        improved=improved,
    )


def deepen_health_report(
    summary: Optional[Mapping[str, Any]] = None,
    *,
    explorer: Any = None,
    previous: Optional[HealthSnapshot] = None,
) -> Dict[str, Any]:
    """Produce a deepened health report for CLI / pipeline consumption."""
    if summary is None:
        snap = collect_health_snapshot(explorer)
    else:
        snap = snapshot_from_summary(summary)
    report: Dict[str, Any] = {
        "kind": "stu-tools-health-report",
        "snapshot": snap.to_dict(),
        "weakest": [s.to_dict() for s in snap.inventory.weakest(fraction=0.15, path=SurfacePath.HEALTH)],
        "recommendations": health_recommendations(snap),
        "stored_prose": 0,
    }
    if previous is not None:
        report["diff"] = diff_health(previous, snap).to_dict()
    return report


def health_recommendations(snapshot: HealthSnapshot) -> List[Dict[str, str]]:
    recs: List[Dict[str, str]] = []
    missing = snapshot.missing_required
    if missing:
        recs.append(
            {
                "action": "restore_required_surfaces",
                "trigger": "required_missing",
                "detail": ",".join(missing),
            }
        )
    failed = [s for s in snapshot.inventory.by_path(SurfacePath.HEALTH) if s.status == "failed"]
    if failed:
        recs.append(
            {
                "action": "inspect_failed_subsystems",
                "trigger": "failed_count>0",
                "detail": ",".join(s.name for s in failed[:8]),
            }
        )
    degraded = [s for s in snapshot.inventory.by_path(SurfacePath.HEALTH) if s.status == "degraded"]
    if degraded:
        recs.append(
            {
                "action": "doctor_then_weakest_regenerate",
                "trigger": "degraded_count>0",
                "detail": ",".join(s.name for s in degraded[:8]),
            }
        )
    if snapshot.mean_score < 0.7:
        recs.append(
            {
                "action": "run_stu_tools_pipeline",
                "trigger": "mean_score<0.7",
                "detail": f"mean_score={snapshot.mean_score}",
            }
        )
    if not recs:
        recs.append({"action": "maintain", "trigger": "healthy", "detail": "no action"})
    return recs


def render_health_deep(report: Mapping[str, Any]) -> str:
    snap = report.get("snapshot") or {}
    lines = [
        "STU-TOOLS Health Deep Report",
        f"  overall: {snap.get('overall')}",
        f"  subsystems: {snap.get('total_subsystems')}  phases: {snap.get('phases_booted')}",
        f"  mean_score: {snap.get('mean_score')}",
        f"  fingerprint: {snap.get('fingerprint')}",
    ]
    missing = snap.get("missing_required") or []
    if missing:
        lines.append(f"  missing_required: {', '.join(missing)}")
    weakest = report.get("weakest") or []
    if weakest:
        lines.append("  weakest:")
        for w in weakest[:10]:
            lines.append(f"    - {w.get('name')}: score={w.get('score')} status={w.get('status')}")
    for rec in report.get("recommendations") or []:
        lines.append(f"  rec: {rec.get('action')} ({rec.get('trigger')})")
    return "\n".join(lines)


__all__ = [
    "HealthSnapshot",
    "HealthDiff",
    "snapshot_from_summary",
    "collect_health_snapshot",
    "diff_health",
    "deepen_health_report",
    "health_recommendations",
    "render_health_deep",
]
