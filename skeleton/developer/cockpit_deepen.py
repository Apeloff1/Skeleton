"""Dedicated cockpit knob deepen path for STU-TOOLS.

Scores cockpit multipliers, detects out-of-range / law violations, and
produces retune plans consumed by cockpit gates + weakest regenerate.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from skeleton.developer.surface_inventory import (
    REQUIRED_COCKPIT_KNOBS,
    SurfaceInventory,
    SurfacePath,
    inventory_from_cockpit,
)


KNOB_RANGE: Dict[str, Tuple[float, float]] = {
    "speed_mul": (0.5, 2.0),
    "heat_mul": (0.5, 2.0),
    "collapse_mul": (0.5, 2.0),
}

DEFAULT_KNOB_VALUE = 1.0


@dataclass
class CockpitKnobState:
    name: str
    value: float
    lo: float
    hi: float
    in_range: bool
    score: float
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "lo": self.lo,
            "hi": self.hi,
            "in_range": self.in_range,
            "score": round(self.score, 4),
            "issues": list(self.issues),
        }


@dataclass
class CockpitSnapshot:
    knobs: List[CockpitKnobState]
    inventory: SurfaceInventory
    stored_prose: int = 0
    source: str = "cockpit"
    collected_at: float = field(default_factory=time.time)

    @property
    def mean_score(self) -> float:
        if not self.knobs:
            return 0.0
        return round(sum(k.score for k in self.knobs) / len(self.knobs), 4)

    @property
    def out_of_range(self) -> List[str]:
        return [k.name for k in self.knobs if not k.in_range]

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "knobs": [k.to_dict() for k in sorted(self.knobs, key=lambda x: x.name)],
                "stored_prose": self.stored_prose,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-cockpit-snapshot",
            "knobs": [k.to_dict() for k in self.knobs],
            "mean_score": self.mean_score,
            "out_of_range": self.out_of_range,
            "inventory": self.inventory.to_dict(),
            "stored_prose": self.stored_prose,
            "source": self.source,
            "collected_at": self.collected_at,
            "fingerprint": self.fingerprint(),
        }


@dataclass
class CockpitRetunePlan:
    clamps: Dict[str, float] = field(default_factory=dict)
    zero_stored_prose: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-cockpit-retune",
            "clamps": dict(self.clamps),
            "zero_stored_prose": self.zero_stored_prose,
            "notes": list(self.notes),
            "stored_prose": 0,
        }


def _parse_value(raw: Any) -> Tuple[Optional[float], List[str]]:
    issues: List[str] = []
    if raw is None:
        return DEFAULT_KNOB_VALUE, []
    try:
        return float(raw), issues
    except (TypeError, ValueError):
        issues.append("non_numeric")
        return None, issues


def snapshot_cockpit(knobs: Optional[Mapping[str, Any]] = None, *, source: str = "cockpit") -> CockpitSnapshot:
    raw = dict(knobs or {})
    for name in REQUIRED_COCKPIT_KNOBS:
        raw.setdefault(name, DEFAULT_KNOB_VALUE)
    try:
        prose = int(raw.get("stored_prose", 0) or 0)
    except (TypeError, ValueError):
        prose = 1
    states: List[CockpitKnobState] = []
    for name in REQUIRED_COCKPIT_KNOBS:
        lo, hi = KNOB_RANGE[name]
        value, issues = _parse_value(raw.get(name))
        if value is None:
            states.append(
                CockpitKnobState(
                    name=name, value=0.0, lo=lo, hi=hi, in_range=False, score=0.0, issues=issues
                )
            )
            continue
        in_range = lo <= value <= hi
        score = 1.0 if in_range else max(0.0, 1.0 - abs(value - max(lo, min(hi, value))) / max(hi, 1.0))
        if not in_range:
            issues = list(issues) + [f"out_of_range:{value}"]
            score = 0.2
        states.append(
            CockpitKnobState(
                name=name, value=value, lo=lo, hi=hi, in_range=in_range, score=score, issues=issues
            )
        )
    inv = inventory_from_cockpit({**{k.name: k.value for k in states}, "stored_prose": prose})
    inv.stored_prose = prose
    return CockpitSnapshot(knobs=states, inventory=inv, stored_prose=prose, source=source)


def retune_plan(snapshot: CockpitSnapshot) -> CockpitRetunePlan:
    clamps: Dict[str, float] = {}
    notes: List[str] = []
    for knob in snapshot.knobs:
        if not knob.in_range:
            target = DEFAULT_KNOB_VALUE
            clamps[knob.name] = target
            notes.append(f"clamp {knob.name} {knob.value}->{target}")
    zero = snapshot.stored_prose != 0
    if zero:
        notes.append(f"zero stored_prose from {snapshot.stored_prose}")
    return CockpitRetunePlan(clamps=clamps, zero_stored_prose=zero, notes=notes)


def apply_retune(knobs: Mapping[str, Any], plan: CockpitRetunePlan) -> Dict[str, Any]:
    out = dict(knobs)
    for name, value in plan.clamps.items():
        out[name] = value
    if plan.zero_stored_prose:
        out["stored_prose"] = 0
    for name in REQUIRED_COCKPIT_KNOBS:
        out.setdefault(name, DEFAULT_KNOB_VALUE)
    out.setdefault("stored_prose", 0)
    return out


def deepen_cockpit_report(knobs: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    snap = snapshot_cockpit(knobs)
    plan = retune_plan(snap)
    return {
        "kind": "stu-tools-cockpit-report",
        "snapshot": snap.to_dict(),
        "retune": plan.to_dict(),
        "weakest": [s.to_dict() for s in snap.inventory.weakest(fraction=0.15, path=SurfacePath.COCKPIT)],
        "stored_prose": snap.stored_prose,
    }


def render_cockpit_deep(report: Mapping[str, Any]) -> str:
    snap = report.get("snapshot") or {}
    lines = [
        "STU-TOOLS Cockpit Deep Report",
        f"  mean_score: {snap.get('mean_score')}  fp: {snap.get('fingerprint')}",
        f"  out_of_range: {', '.join(snap.get('out_of_range') or []) or 'none'}",
        f"  stored_prose: {snap.get('stored_prose')}",
    ]
    for note in (report.get("retune") or {}).get("notes") or []:
        lines.append(f"  retune: {note}")
    return "\n".join(lines)


def cockpit_diff(before: CockpitSnapshot, after: CockpitSnapshot) -> Dict[str, Any]:
    before_map = {k.name: k for k in before.knobs}
    after_map = {k.name: k for k in after.knobs}
    changed = []
    worsened = []
    for name in REQUIRED_COCKPIT_KNOBS:
        b = before_map.get(name)
        a = after_map.get(name)
        if not b or not a:
            continue
        if abs(b.value - a.value) > 1e-9:
            changed.append(name)
        if a.score + 1e-9 < b.score - 0.05:
            worsened.append(name)
    return {
        "kind": "stu-tools-cockpit-diff",
        "before_fp": before.fingerprint(),
        "after_fp": after.fingerprint(),
        "changed": changed,
        "worsened": worsened,
        "mean_before": before.mean_score,
        "mean_after": after.mean_score,
        "regressed": bool(worsened) or after.stored_prose > before.stored_prose,
        "stored_prose": 0,
    }


__all__ = [
    "KNOB_RANGE",
    "DEFAULT_KNOB_VALUE",
    "CockpitKnobState",
    "CockpitSnapshot",
    "CockpitRetunePlan",
    "snapshot_cockpit",
    "retune_plan",
    "apply_retune",
    "deepen_cockpit_report",
    "render_cockpit_deep",
    "cockpit_diff",
]
