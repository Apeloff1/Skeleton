"""Reusable STU-TOOLS fixtures for gates, CI bundles, and matrix tests."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from skeleton.developer.surface_inventory import (
    REQUIRED_COCKPIT_KNOBS,
    REQUIRED_DOCTOR_DOMAINS,
    REQUIRED_HEALTH_SURFACES,
)


def healthy_health_summary() -> Dict[str, Any]:
    return {
        "overall": "healthy",
        "total_subsystems": len(REQUIRED_HEALTH_SURFACES),
        "phases_booted": len(REQUIRED_HEALTH_SURFACES),
        "status_breakdown": {"healthy": len(REQUIRED_HEALTH_SURFACES)},
        "cards": [
            {"name": n, "status": "healthy", "phase": n, "metrics": {"ok": 1}}
            for n in REQUIRED_HEALTH_SURFACES
        ],
    }


def health_summary_with_statuses(statuses: Sequence[str]) -> Dict[str, Any]:
    if len(statuses) != len(REQUIRED_HEALTH_SURFACES):
        raise ValueError("statuses length must match REQUIRED_HEALTH_SURFACES")
    breakdown: Dict[str, int] = {}
    for s in statuses:
        breakdown[s] = breakdown.get(s, 0) + 1
    overall = "failed" if "failed" in breakdown else ("degraded" if "degraded" in breakdown else "healthy")
    return {
        "overall": overall,
        "total_subsystems": len(statuses),
        "phases_booted": len(statuses),
        "status_breakdown": breakdown,
        "cards": [
            {"name": n, "status": s, "phase": n, "metrics": {}}
            for n, s in zip(REQUIRED_HEALTH_SURFACES, statuses)
        ],
    }


def healthy_doctor_card(**knob_overrides: float) -> Dict[str, Any]:
    cockpit = {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}
    cockpit.update(knob_overrides)
    cockpit.setdefault("stored_prose", 0)
    return {
        "alerts": [],
        "repair_effectiveness": {"ok": 1, "rate": 0.95},
        "kv_cache": {"hit_rate": 0.93},
        "policy": {"enforced": 1},
        "circuit": {"open": 0},
        "health": {"overall": "healthy"},
        "audit_integrity": {"ok": 1},
        "dashboard": {"ready": 1},
        "cockpit": cockpit,
        "stored_prose": int(cockpit.get("stored_prose") or 0),
    }


def doctor_card_with_alerts(alerts: List[Dict[str, Any]], **knob_overrides: float) -> Dict[str, Any]:
    card = healthy_doctor_card(**knob_overrides)
    card["alerts"] = list(alerts)
    return card


def healthy_topology(name: str = "fixture") -> Dict[str, Any]:
    return {
        "name": name,
        "components": {
            "input": {"kind": "source", "ports": [{"name": "out", "direction": "out"}]},
            "process": {
                "kind": "transform",
                "ports": [
                    {"name": "in", "direction": "in"},
                    {"name": "out", "direction": "out"},
                ],
            },
            "output": {"kind": "sink", "ports": [{"name": "in", "direction": "in"}]},
        },
        "wires": [
            {"src": "input", "dst": "process"},
            {"src": "process", "dst": "output"},
        ],
    }


def chain_topology(n: int, name: str = "chain") -> Dict[str, Any]:
    if n < 2:
        raise ValueError("n must be >= 2")
    comps = {f"n{i}": {"kind": "node", "ports": [{"name": "p"}]} for i in range(n)}
    wires = [{"src": f"n{i}", "dst": f"n{i+1}"} for i in range(n - 1)]
    return {"name": f"{name}-{n}", "components": comps, "wires": wires}


def grid_topology(width: int, name: str = "grid") -> Dict[str, Any]:
    if width < 2:
        raise ValueError("width must be >= 2")
    comps: Dict[str, Any] = {}
    wires: List[Dict[str, str]] = []
    for r in range(width):
        for c in range(width):
            node = f"n{r}_{c}"
            comps[node] = {"kind": "cell", "ports": [{"name": "p"}]}
            if c + 1 < width:
                wires.append({"src": node, "dst": f"n{r}_{c+1}"})
            if r + 1 < width:
                wires.append({"src": node, "dst": f"n{r+1}_{c}"})
    return {"name": f"{name}-{width}", "components": comps, "wires": wires}


def healthy_cockpit_knobs(**overrides: float) -> Dict[str, Any]:
    knobs = {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}
    knobs.update(overrides)
    knobs.setdefault("stored_prose", 0)
    return knobs


def artefact_set(n: int = 8, *, todo_every: int = 3) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for i in range(n):
        if todo_every and i % todo_every == 0:
            out[f"f{i}.gd"] = "TODO unfinished\n"
        else:
            out[f"f{i}.gd"] = "extends Node\nfunc _ready() -> void:\n    pass\n"
    return out


def critical_alert(domain: str, message: str = "critical") -> Dict[str, str]:
    return {"subsystem": domain, "severity": "critical", "message": message}


def warning_alert(domain: str, message: str = "warning") -> Dict[str, str]:
    return {"subsystem": domain, "severity": "warning", "message": message}


def all_domain_critical_cards() -> List[Dict[str, Any]]:
    return [doctor_card_with_alerts([critical_alert(d)]) for d in REQUIRED_DOCTOR_DOMAINS]


def all_knob_oor_sets() -> List[Dict[str, Any]]:
    sets = []
    for knob in REQUIRED_COCKPIT_KNOBS:
        for value in (0.1, 9.0):
            knobs = healthy_cockpit_knobs()
            knobs[knob] = value
            sets.append(knobs)
    return sets


__all__ = [
    "healthy_health_summary",
    "health_summary_with_statuses",
    "healthy_doctor_card",
    "doctor_card_with_alerts",
    "healthy_topology",
    "chain_topology",
    "grid_topology",
    "healthy_cockpit_knobs",
    "artefact_set",
    "critical_alert",
    "warning_alert",
    "all_domain_critical_cards",
    "all_knob_oor_sets",
]
