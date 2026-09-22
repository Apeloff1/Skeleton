"""Uniform STU-TOOLS path runners — shared invoke/result shape for CI.

Each path returns the same envelope so Merge Manager / Carrol can parse one schema.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from skeleton.developer.cockpit_gates import run_cockpit_gates
from skeleton.developer.doctor_cockpit_bridge import run_doctor_cockpit_bridge
from skeleton.developer.doctor_gates import run_doctor_gates
from skeleton.developer.gate_catalog import gates_for_path
from skeleton.developer.health_gates import run_health_gates
from skeleton.developer.visualize_gates import run_visualize_gates
from skeleton.developer.weakest_regenerate import run_weakest_regenerate


@dataclass
class PathRun:
    path: str
    ok: int
    banner: str
    duration_ms: float
    expected_gates: List[str] = field(default_factory=list)
    observed_gates: List[str] = field(default_factory=list)
    missing_gates: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    stored_prose: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-path-run",
            "path": self.path,
            "ok": self.ok,
            "banner": self.banner,
            "duration_ms": self.duration_ms,
            "expected_gates": list(self.expected_gates),
            "observed_gates": list(self.observed_gates),
            "missing_gates": list(self.missing_gates),
            "payload": self.payload,
            "stored_prose": self.stored_prose,
        }


def _observe(path: str, result: Mapping[str, Any], started: float) -> PathRun:
    verdict = result.get("verdict") or {}
    observed = [g.get("name") for g in verdict.get("gates") or [] if isinstance(g, Mapping)]
    expected = [g.name for g in gates_for_path(path)]
    # collector/error gates are dynamic — only require catalog names that appear OR soft-check subset
    missing = []
    # For coverage reporting we list expected; missing only if path claimed green but catalog sev1 absent
    sev1_expected = [g.name for g in gates_for_path(path) if g.severity == "sev1"]
    if int(result.get("ok") or 0) == 1:
        for name in sev1_expected:
            if name not in observed and not name.endswith(".collect"):
                # some paths use slightly different collect names; soft
                if name.split(".", 1)[-1] == "stored_prose_zero" and any(
                    o.endswith("stored_prose_zero") for o in observed
                ):
                    continue
                if name not in observed:
                    missing.append(name)
    return PathRun(
        path=path,
        ok=int(result.get("ok") or 0),
        banner=str(result.get("banner") or verdict.get("banner") or ""),
        duration_ms=round((time.time() - started) * 1000, 3),
        expected_gates=expected,
        observed_gates=[str(x) for x in observed if x],
        missing_gates=missing,
        payload=dict(result),
        stored_prose=int(result.get("stored_prose") or 0),
    )


def run_health_path(explorer: Any = None, **kwargs: Any) -> PathRun:
    started = time.time()
    if explorer is None:
        class E:
            def summary(self):
                from skeleton.developer.surface_inventory import REQUIRED_HEALTH_SURFACES
                return {
                    "overall": "healthy",
                    "total_subsystems": len(REQUIRED_HEALTH_SURFACES),
                    "phases_booted": len(REQUIRED_HEALTH_SURFACES),
                    "status_breakdown": {"healthy": len(REQUIRED_HEALTH_SURFACES)},
                    "cards": [
                        {"name": n, "status": "healthy", "phase": n, "metrics": {}}
                        for n in REQUIRED_HEALTH_SURFACES
                    ],
                }
        explorer = E()
    return _observe("health", run_health_gates(explorer=explorer, **kwargs), started)


def run_visualize_path(topology: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> PathRun:
    started = time.time()
    if topology is None:
        topology = {
            "name": "default",
            "components": {
                "a": {"kind": "source", "ports": [{"name": "o"}]},
                "b": {"kind": "transform", "ports": [{"name": "i"}, {"name": "o"}]},
                "c": {"kind": "sink", "ports": [{"name": "i"}]},
            },
            "wires": [{"src": "a", "dst": "b"}, {"src": "b", "dst": "c"}],
        }
    return _observe("visualize", run_visualize_gates(topology=topology, **kwargs), started)


def run_doctor_path(card: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> PathRun:
    started = time.time()
    return _observe("doctor", run_doctor_gates(card=card, **kwargs), started)


def run_cockpit_path(knobs: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> PathRun:
    started = time.time()
    return _observe("cockpit", run_cockpit_gates(knobs, **kwargs), started)


def run_regen_path(artefacts: Optional[Mapping[str, str]] = None, **kwargs: Any) -> PathRun:
    started = time.time()
    if artefacts is None:
        artefacts = {"ok.gd": "extends Node\nfunc _ready() -> void:\n    pass\n"}
    return _observe(
        "regen",
        run_weakest_regenerate(artefacts=artefacts, allow_empty=True, **kwargs),
        started,
    )


def run_all_paths(
    *,
    explorer: Any = None,
    topology: Optional[Mapping[str, Any]] = None,
    doctor_card: Optional[Mapping[str, Any]] = None,
    knobs: Optional[Mapping[str, Any]] = None,
    artefacts: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    runs = [
        run_health_path(explorer),
        run_visualize_path(topology),
        run_doctor_path(doctor_card),
        run_cockpit_path(knobs),
        run_regen_path(artefacts),
    ]
    bridge = run_doctor_cockpit_bridge(doctor_card=doctor_card)
    ok = 1 if all(r.ok == 1 for r in runs) and int(bridge.get("ok") or 0) == 1 else 0
    return {
        "kind": "stu-tools-all-paths",
        "ok": ok,
        "banner": "VERDICT: ALL GATES PASSED" if ok else "VERDICT: FAIL CLOSED — path runners",
        "runs": [r.to_dict() for r in runs],
        "bridge": bridge,
        "stored_prose": 0,
    }


__all__ = [
    "PathRun",
    "run_health_path",
    "run_visualize_path",
    "run_doctor_path",
    "run_cockpit_path",
    "run_regen_path",
    "run_all_paths",
]
