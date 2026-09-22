"""Deepen the developer doctor / cockpit diagnostic path (STU-TOOLS).

Turns organism doctor cards + cockpit knobs into scored snapshots that feed
fail-closed doctor gates and weakest-regenerate.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from skeleton.developer.surface_inventory import (
    REQUIRED_COCKPIT_KNOBS,
    REQUIRED_DOCTOR_DOMAINS,
    SurfaceInventory,
    SurfacePath,
    inventory_from_cockpit,
    inventory_from_doctor_card,
    merge_inventories,
)


@dataclass
class DoctorSnapshot:
    """Point-in-time doctor + cockpit snapshot."""

    domains: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    cockpit: Dict[str, Any]
    inventory: SurfaceInventory
    collected_at: float = field(default_factory=time.time)
    source: str = "doctor_card"
    stored_prose: int = 0

    @property
    def mean_score(self) -> float:
        return self.inventory.mean_score(SurfacePath.DOCTOR)

    @property
    def cockpit_mean(self) -> float:
        return self.inventory.mean_score(SurfacePath.COCKPIT)

    @property
    def critical_alerts(self) -> List[Dict[str, Any]]:
        return [a for a in self.alerts if str(a.get("severity") or "").lower() == "critical"]

    @property
    def warning_alerts(self) -> List[Dict[str, Any]]:
        return [a for a in self.alerts if str(a.get("severity") or "").lower() == "warning"]

    @property
    def missing_domains(self) -> List[str]:
        return self.inventory.required_missing(SurfacePath.DOCTOR)

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "domains": sorted(self.domains.keys()),
                "alerts": len(self.alerts),
                "critical": len(self.critical_alerts),
                "cockpit": self.cockpit,
                "inv": self.inventory.fingerprint(),
                "stored_prose": self.stored_prose,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-doctor-snapshot",
            "domains": dict(self.domains),
            "alerts": list(self.alerts),
            "cockpit": dict(self.cockpit),
            "mean_score": self.mean_score,
            "cockpit_mean": self.cockpit_mean,
            "critical_alerts": len(self.critical_alerts),
            "warning_alerts": len(self.warning_alerts),
            "missing_domains": self.missing_domains,
            "inventory": self.inventory.to_dict(),
            "collected_at": self.collected_at,
            "source": self.source,
            "fingerprint": self.fingerprint(),
            "stored_prose": self.stored_prose,
        }


@dataclass
class DoctorDiff:
    before_fp: str
    after_fp: str
    mean_before: float
    mean_after: float
    critical_before: int
    critical_after: int
    added_alerts: List[str] = field(default_factory=list)
    cleared_alerts: List[str] = field(default_factory=list)
    worsened_domains: List[str] = field(default_factory=list)

    @property
    def regressed(self) -> bool:
        if self.critical_after > self.critical_before:
            return True
        if self.mean_after + 1e-9 < self.mean_before - 0.05:
            return True
        return bool(self.worsened_domains)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-doctor-diff",
            "before_fp": self.before_fp,
            "after_fp": self.after_fp,
            "mean_before": self.mean_before,
            "mean_after": self.mean_after,
            "critical_before": self.critical_before,
            "critical_after": self.critical_after,
            "added_alerts": list(self.added_alerts),
            "cleared_alerts": list(self.cleared_alerts),
            "worsened_domains": list(self.worsened_domains),
            "regressed": self.regressed,
            "stored_prose": 0,
        }


def _normalize_alerts(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, Mapping):
            out.append(
                {
                    "subsystem": str(item.get("subsystem") or "unknown"),
                    "severity": str(item.get("severity") or "info"),
                    "message": str(item.get("message") or item.get("detail") or ""),
                    "code": str(item.get("code") or ""),
                }
            )
    return out


def snapshot_from_doctor_card(
    card: Mapping[str, Any],
    *,
    cockpit: Optional[Mapping[str, Any]] = None,
    source: str = "doctor_card",
) -> DoctorSnapshot:
    alerts = _normalize_alerts(card.get("alerts"))
    domains = {
        "repair": card.get("repair_effectiveness") or card.get("error_summary") or {},
        "kv_cache": card.get("kv_cache") or {},
        "policy": card.get("policy") or {},
        "resilience": card.get("circuit") or card.get("load_shedder") or {},
        "health": card.get("health") or {},
        "audit": card.get("audit_integrity") or {},
        "dashboard": card.get("dashboard") or {},
    }
    knobs = dict(cockpit or card.get("cockpit") or {})
    for k in REQUIRED_COCKPIT_KNOBS:
        knobs.setdefault(k, 1.0)
    knobs.setdefault("stored_prose", int(card.get("stored_prose") or 0))
    doc_inv = inventory_from_doctor_card(card)
    cock_inv = inventory_from_cockpit(knobs)
    inventory = merge_inventories(doc_inv, cock_inv)
    prose = int(knobs.get("stored_prose") or 0)
    inventory.stored_prose = prose
    return DoctorSnapshot(
        domains={k: (dict(v) if isinstance(v, Mapping) else {"value": v}) for k, v in domains.items()},
        alerts=alerts,
        cockpit=knobs,
        inventory=inventory,
        source=source,
        stored_prose=prose,
    )


def collect_doctor_snapshot(organism: Any = None, *, card: Optional[Mapping[str, Any]] = None) -> DoctorSnapshot:
    if card is not None:
        return snapshot_from_doctor_card(card, source="provided")
    if organism is None:
        # Synthetic healthy baseline for offline / unit paths
        card = {
            "alerts": [],
            "repair_effectiveness": {"ok": 1},
            "kv_cache": {"hit_rate": 0.9},
            "policy": {"enforced": 1},
            "circuit": {"open": 0},
            "health": {"overall": "healthy"},
            "audit_integrity": {"ok": 1},
            "dashboard": {"ready": 1},
            "cockpit": {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS},
            "stored_prose": 0,
        }
        return snapshot_from_doctor_card(card, source="synthetic")
    for attr in ("doctor_card", "doctor", "diagnostics"):
        fn = getattr(organism, attr, None)
        if callable(fn):
            raw = fn()
            if isinstance(raw, Mapping):
                return snapshot_from_doctor_card(raw, source=attr)
    if isinstance(organism, Mapping):
        return snapshot_from_doctor_card(organism, source="mapping")
    raise TypeError("organism does not expose a doctor card")


def diff_doctor(before: DoctorSnapshot, after: DoctorSnapshot) -> DoctorDiff:
    before_keys = {f"{a.get('subsystem')}:{a.get('code')}:{a.get('message')}" for a in before.alerts}
    after_keys = {f"{a.get('subsystem')}:{a.get('code')}:{a.get('message')}" for a in after.alerts}
    before_scores = {s.name: s.score for s in before.inventory.by_path(SurfacePath.DOCTOR)}
    after_scores = {s.name: s.score for s in after.inventory.by_path(SurfacePath.DOCTOR)}
    worsened = [
        name
        for name, score in after_scores.items()
        if name in before_scores and score + 1e-9 < before_scores[name] - 0.1
    ]
    return DoctorDiff(
        before_fp=before.fingerprint(),
        after_fp=after.fingerprint(),
        mean_before=before.mean_score,
        mean_after=after.mean_score,
        critical_before=len(before.critical_alerts),
        critical_after=len(after.critical_alerts),
        added_alerts=sorted(after_keys - before_keys),
        cleared_alerts=sorted(before_keys - after_keys),
        worsened_domains=sorted(worsened),
    )


def doctor_recommendations(snapshot: DoctorSnapshot) -> List[Dict[str, str]]:
    recs: List[Dict[str, str]] = []
    if snapshot.stored_prose != 0:
        recs.append({"action": "zero_stored_prose", "trigger": "law", "detail": f"stored_prose={snapshot.stored_prose}"})
    if snapshot.critical_alerts:
        recs.append(
            {
                "action": "clear_critical_alerts",
                "trigger": "sev1",
                "detail": ",".join(a.get("subsystem", "") for a in snapshot.critical_alerts[:8]),
            }
        )
    if snapshot.missing_domains:
        recs.append(
            {
                "action": "restore_doctor_domains",
                "trigger": "missing_required",
                "detail": ",".join(snapshot.missing_domains),
            }
        )
    weak = snapshot.inventory.weakest(fraction=0.15, path=SurfacePath.DOCTOR)
    if weak:
        recs.append(
            {
                "action": "regenerate_weak_domains",
                "trigger": "weakest",
                "detail": ",".join(s.name for s in weak),
            }
        )
    cock_weak = [s for s in snapshot.inventory.by_path(SurfacePath.COCKPIT) if s.score < 0.7]
    if cock_weak:
        recs.append(
            {
                "action": "retune_cockpit",
                "trigger": "cockpit_out_of_range",
                "detail": ",".join(s.name for s in cock_weak),
            }
        )
    if not recs:
        recs.append({"action": "maintain", "trigger": "healthy", "detail": "doctor ok"})
    return recs


def deepen_doctor_report(
    organism: Any = None,
    *,
    card: Optional[Mapping[str, Any]] = None,
    previous: Optional[DoctorSnapshot] = None,
) -> Dict[str, Any]:
    snap = collect_doctor_snapshot(organism, card=card)
    report: Dict[str, Any] = {
        "kind": "stu-tools-doctor-report",
        "snapshot": snap.to_dict(),
        "weakest": [s.to_dict() for s in snap.inventory.weakest(fraction=0.15, path=SurfacePath.DOCTOR)],
        "recommendations": doctor_recommendations(snap),
        "required_domains": list(REQUIRED_DOCTOR_DOMAINS),
        "stored_prose": snap.stored_prose,
    }
    if previous is not None:
        report["diff"] = diff_doctor(previous, snap).to_dict()
    return report


def render_doctor_deep(report: Mapping[str, Any]) -> str:
    snap = report.get("snapshot") or {}
    lines = [
        "STU-TOOLS Doctor Deep Report",
        f"  mean_score: {snap.get('mean_score')}  cockpit_mean: {snap.get('cockpit_mean')}",
        f"  critical: {snap.get('critical_alerts')}  warning: {snap.get('warning_alerts')}",
        f"  missing: {', '.join(snap.get('missing_domains') or []) or 'none'}",
        f"  fp: {snap.get('fingerprint')}",
    ]
    for rec in report.get("recommendations") or []:
        lines.append(f"  rec: {rec.get('action')} ({rec.get('trigger')})")
    return "\n".join(lines)


__all__ = [
    "DoctorSnapshot",
    "DoctorDiff",
    "snapshot_from_doctor_card",
    "collect_doctor_snapshot",
    "diff_doctor",
    "doctor_recommendations",
    "deepen_doctor_report",
    "render_doctor_deep",
]
