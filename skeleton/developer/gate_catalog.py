"""Catalog of STU-TOOLS gates — discovery, severity map, and regression helpers.

Provides a deterministic registry of gate names by path so CI and doctor
dashboards can assert coverage without scraping source.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from skeleton.developer.gate_verdict import GateSeverity


@dataclass(frozen=True)
class GateSpec:
    name: str
    path: str
    severity: str
    description: str
    fail_closed: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "severity": self.severity,
            "description": self.description,
            "fail_closed": self.fail_closed,
        }


CATALOG: Tuple[GateSpec, ...] = (
    GateSpec("health.stored_prose_zero", "health", "sev1", "stored_prose must be 0"),
    GateSpec("health.nonempty", "health", "sev1", "health snapshot non-empty"),
    GateSpec("health.required_surfaces", "health", "sev1", "required health surfaces present"),
    GateSpec("health.failed_count", "health", "sev1", "failed subsystem count ceiling"),
    GateSpec("health.degraded_count", "health", "sev2", "degraded subsystem count ceiling"),
    GateSpec("health.overall_not_failed", "health", "sev2", "overall not failed"),
    GateSpec("health.mean_score_floor", "health", "sev2", "mean score floor"),
    GateSpec("health.phases_booted", "health", "sev2", "phases booted"),
    GateSpec("health.diff.no_regression", "health", "sev2", "health diff no regression"),
    GateSpec("health.diff.no_removals", "health", "sev2", "health diff no removals"),
    GateSpec("visualize.stored_prose_zero", "visualize", "sev1", "stored_prose must be 0"),
    GateSpec("visualize.nonempty", "visualize", "sev1", "topology non-empty"),
    GateSpec("visualize.required_fields", "visualize", "sev1", "required visualize fields"),
    GateSpec("visualize.dangling_wires", "visualize", "sev1", "dangling wire ceiling"),
    GateSpec("visualize.orphan_components", "visualize", "sev2", "orphan component ceiling"),
    GateSpec("visualize.mean_score_floor", "visualize", "sev2", "visualize mean floor"),
    GateSpec("visualize.connected", "visualize", "sev2", "topology connected"),
    GateSpec("doctor.stored_prose_zero", "doctor", "sev1", "stored_prose must be 0"),
    GateSpec("doctor.domains_nonempty", "doctor", "sev1", "doctor domains present"),
    GateSpec("doctor.required_domains", "doctor", "sev1", "required doctor domains"),
    GateSpec("doctor.critical_alerts", "doctor", "sev1", "critical alert ceiling"),
    GateSpec("doctor.warning_alerts", "doctor", "sev2", "warning alert ceiling"),
    GateSpec("doctor.mean_score_floor", "doctor", "sev2", "doctor mean floor"),
    GateSpec("doctor.cockpit_healthy", "doctor", "sev2", "cockpit mean healthy"),
    GateSpec("doctor.cockpit_knobs_in_range", "doctor", "sev2", "cockpit knobs in range"),
    GateSpec("doctor.diff.no_regression", "doctor", "sev2", "doctor diff no regression"),
    GateSpec("doctor.diff.critical_not_up", "doctor", "sev1", "critical alerts not increased"),
    GateSpec("cockpit.stored_prose_zero", "cockpit", "sev1", "stored_prose must be 0"),
    GateSpec("cockpit.knobs_nonempty", "cockpit", "sev1", "cockpit knobs present"),
    GateSpec("cockpit.all_in_range", "cockpit", "sev2", "all knobs in range"),
    GateSpec("cockpit.mean_score_floor", "cockpit", "sev2", "cockpit mean floor"),
    GateSpec("cockpit.diff.no_regression", "cockpit", "sev2", "cockpit diff no regression"),
    GateSpec("regen.stored_prose_zero", "regen", "sev1", "stored_prose must be 0"),
    GateSpec("regen.targets_nonempty", "regen", "sev2", "regen targets present"),
    GateSpec("regen.actions_present", "regen", "sev1", "regen actions present"),
)


def gates_for_path(path: str) -> List[GateSpec]:
    return [g for g in CATALOG if g.path == path]


def sev1_gates() -> List[GateSpec]:
    return [g for g in CATALOG if g.severity == "sev1"]


def sev2_gates() -> List[GateSpec]:
    return [g for g in CATALOG if g.severity == "sev2"]


def catalog_dict() -> Dict[str, Any]:
    by_path: Dict[str, List[Dict[str, Any]]] = {}
    for g in CATALOG:
        by_path.setdefault(g.path, []).append(g.to_dict())
    return {
        "kind": "stu-tools-gate-catalog",
        "count": len(CATALOG),
        "sev1": len(sev1_gates()),
        "sev2": len(sev2_gates()),
        "by_path": by_path,
        "gates": [g.to_dict() for g in CATALOG],
        "stored_prose": 0,
    }


def assert_catalog_covers(names: Iterable[str], *, path: Optional[str] = None) -> None:
    known = {g.name for g in (gates_for_path(path) if path else CATALOG)}
    missing = [n for n in names if n not in known]
    if missing:
        raise AssertionError(f"gate catalog missing: {missing}")


def catalog_fingerprint() -> str:
    import hashlib
    payload = json.dumps([g.to_dict() for g in CATALOG], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "GateSpec",
    "CATALOG",
    "gates_for_path",
    "sev1_gates",
    "sev2_gates",
    "catalog_dict",
    "assert_catalog_covers",
    "catalog_fingerprint",
]
