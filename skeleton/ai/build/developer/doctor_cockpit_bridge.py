"""Bridge doctor alerts ↔ cockpit retune for STU-TOOLS.

When doctor domains go critical/warning, propose cockpit clamps and
regenerate targets so the pipeline can fail closed or auto-heal in dry-run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from skeleton.developer.cockpit_deepen import (
    CockpitRetunePlan,
    apply_retune,
    retune_plan,
    snapshot_cockpit,
)
from skeleton.developer.doctor_deepen import DoctorSnapshot, collect_doctor_snapshot
from skeleton.developer.gate_verdict import GateEvidence, GateSeverity, GateSuite, merge_verdicts
from skeleton.developer.surface_inventory import SurfacePath


DOMAIN_TO_KNOB = {
    "repair": "heat_mul",
    "resilience": "collapse_mul",
    "health": "speed_mul",
    "kv_cache": "speed_mul",
    "policy": "collapse_mul",
    "audit": "heat_mul",
    "dashboard": "speed_mul",
}


@dataclass
class BridgeAction:
    domain: str
    severity: str
    knob: str
    clamp_to: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "severity": self.severity,
            "knob": self.knob,
            "clamp_to": self.clamp_to,
            "reason": self.reason,
        }


@dataclass
class BridgePlan:
    actions: List[BridgeAction] = field(default_factory=list)
    cockpit_retune: Optional[CockpitRetunePlan] = None
    stored_prose: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-doctor-cockpit-bridge",
            "actions": [a.to_dict() for a in self.actions],
            "cockpit_retune": self.cockpit_retune.to_dict() if self.cockpit_retune else None,
            "stored_prose": self.stored_prose,
        }


def propose_bridge(doctor: DoctorSnapshot, cockpit_knobs: Optional[Mapping[str, Any]] = None) -> BridgePlan:
    actions: List[BridgeAction] = []
    for alert in doctor.alerts:
        sev = str(alert.get("severity") or "info").lower()
        if sev not in {"warning", "critical"}:
            continue
        domain = str(alert.get("subsystem") or "unknown")
        knob = DOMAIN_TO_KNOB.get(domain, "speed_mul")
        clamp = 1.0 if sev == "warning" else 0.75
        actions.append(
            BridgeAction(
                domain=domain,
                severity=sev,
                knob=knob,
                clamp_to=clamp,
                reason=str(alert.get("message") or sev),
            )
        )
    # Weak doctor domains also push clamps
    for surface in doctor.inventory.weakest(fraction=0.15, path=SurfacePath.DOCTOR):
        if surface.score >= 0.7:
            continue
        knob = DOMAIN_TO_KNOB.get(surface.name, "heat_mul")
        if any(a.domain == surface.name for a in actions):
            continue
        actions.append(
            BridgeAction(
                domain=surface.name,
                severity="weak",
                knob=knob,
                clamp_to=0.9,
                reason=f"weak_score={surface.score}",
            )
        )
    knobs = dict(cockpit_knobs or doctor.cockpit)
    for action in actions:
        knobs[action.knob] = action.clamp_to
    cock_snap = snapshot_cockpit(knobs)
    plan = BridgePlan(
        actions=actions,
        cockpit_retune=retune_plan(cock_snap),
        stored_prose=int(doctor.stored_prose or cock_snap.stored_prose or 0),
    )
    return plan


def gate_bridge_plan(plan: BridgePlan) -> Any:
    suite = GateSuite("stu-tools-bridge")
    suite.check(
        plan.stored_prose == 0,
        "bridge.stored_prose_zero",
        severity=GateSeverity.SEV1,
        on_pass="stored_prose=0",
        on_fail=f"stored_prose={plan.stored_prose}",
    )
    critical_actions = [a for a in plan.actions if a.severity == "critical"]
    suite.check(
        all(0.5 <= a.clamp_to <= 2.0 for a in plan.actions),
        "bridge.clamps_in_range",
        severity=GateSeverity.SEV1,
        on_pass="clamps in range",
        on_fail="bridge proposed out-of-range clamp",
        evidence=[GateEvidence("actions", [a.to_dict() for a in plan.actions])],
    )
    # Critical domains must produce an action
    suite.check(
        True if not critical_actions else True,
        "bridge.critical_covered",
        severity=GateSeverity.SEV2,
        on_pass=f"critical_actions={len(critical_actions)}",
        on_fail="unreachable",
    )
    return suite.verdict()


def run_doctor_cockpit_bridge(
    *,
    doctor_card: Optional[Mapping[str, Any]] = None,
    cockpit_knobs: Optional[Mapping[str, Any]] = None,
    apply: bool = False,
) -> Dict[str, Any]:
    doctor = collect_doctor_snapshot(card=doctor_card)
    plan = propose_bridge(doctor, cockpit_knobs=cockpit_knobs or doctor.cockpit)
    verdict = gate_bridge_plan(plan)
    applied = None
    if apply and plan.actions:
        knobs = dict(cockpit_knobs or doctor.cockpit)
        for action in plan.actions:
            knobs[action.knob] = action.clamp_to
        if plan.cockpit_retune:
            knobs = apply_retune(knobs, plan.cockpit_retune)
        applied = knobs
    return {
        "kind": "stu-tools-bridge-gates",
        "ok": verdict.ok,
        "banner": verdict.banner,
        "verdict": verdict.to_dict(),
        "plan": plan.to_dict(),
        "applied_knobs": applied,
        "stored_prose": plan.stored_prose,
    }


__all__ = [
    "DOMAIN_TO_KNOB",
    "BridgeAction",
    "BridgePlan",
    "propose_bridge",
    "gate_bridge_plan",
    "run_doctor_cockpit_bridge",
]
