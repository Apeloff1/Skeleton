"""Quality rubric — weighted gate scoring + grade/fidelity bands for forge polish.

Deterministic companion to ``forge_quality.evaluate``. The rubric owns the
*weights* and *band labels* that turn raw gate pass/fail into a production
scorecard the FE can render; ``forge_quality`` stays the gate engine.

Ported shape from Prood ``backend/core/forge_quality.py`` production scoring
plus Skeleton-native era/behaviour signals. Pure functions only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# Gate weights must sum to 1.0. Production score = 100 * Σ(w_i * pass_i)
# with soft nudges from fidelity + grade (same blend as forge_quality).
GATE_WEIGHTS: Dict[str, float] = {
    "grade_escalation": 0.18,
    "fidelity_floor": 0.20,
    "behaviour_code": 0.22,
    "placement_valid": 0.15,
    "gdd_parity": 0.15,
    "era_compliance": 0.10,
}

# Soft blend for the 0–100 production score (mirrors forge_quality).
BLEND_GATE = 0.70
BLEND_FIDELITY = 0.15
BLEND_GRADE = 0.15

PRODUCTION_THRESHOLD = 95
STAGING_THRESHOLD = 70
DRAFT_THRESHOLD = 40

GRADE_BANDS: Tuple[Tuple[int, int, str], ...] = (
    (0, 0, "prototype"),
    (1, 1, "draft"),
    (2, 2, "staging"),
    (3, 3, "near-production"),
    (4, 4, "production-candidate"),
    (5, 99, "production"),
)

FIDELITY_BANDS: Tuple[Tuple[float, float, str], ...] = (
    (0.0, 0.50, "stub"),
    (0.50, 0.72, "prototype"),
    (0.72, 0.85, "staging"),
    (0.85, 0.95, "near-aaa"),
    (0.95, 1.01, "aaa"),
)

SEVERITY_ORDER = ("critical", "major", "minor", "advisory")


def gate_weight(name: str) -> float:
    return float(GATE_WEIGHTS.get(name, 0.05))


def grade_band(grade: int) -> str:
    g = max(0, int(grade))
    for lo, hi, label in GRADE_BANDS:
        if lo <= g <= hi:
            return label
    return "prototype"


def fidelity_band(fidelity: float) -> str:
    try:
        f = float(fidelity)
    except (TypeError, ValueError):
        f = 0.0
    for lo, hi, label in FIDELITY_BANDS:
        if lo <= f < hi:
            return label
    return "stub"


def production_tier(score: int) -> str:
    s = int(score)
    if s >= PRODUCTION_THRESHOLD:
        return "production"
    if s >= STAGING_THRESHOLD:
        return "staging"
    if s >= DRAFT_THRESHOLD:
        return "draft"
    return "reject"


def _applicable(gate: Mapping[str, Any]) -> bool:
    # forge_quality marks undeclared signals ``applicable: False``; absent key
    # means the gate applies (older verdict shapes).
    return bool(gate.get("applicable", True))


def weighted_gate_score(gates: Sequence[Mapping[str, Any]]) -> float:
    """0–1 weighted pass ratio over applicable gates.

    Unknown gates get a small default weight; gates reported
    ``applicable: False`` are excluded from both numerator and denominator.
    """
    if not gates:
        return 0.0
    total_w = 0.0
    earned = 0.0
    for g in gates:
        if not _applicable(g):
            continue
        name = str(g.get("name") or "")
        w = gate_weight(name)
        total_w += w
        if g.get("passed"):
            earned += w
    if total_w <= 0:
        return 0.0
    return round(earned / total_w, 4)


def blend_production_score(
    *,
    gate_ratio: float,
    fidelity: float,
    grade: int,
) -> int:
    """0–100 production score using the Prood blend."""
    try:
        fid = min(1.0, max(0.0, float(fidelity)))
    except (TypeError, ValueError):
        fid = 0.0
    try:
        grade_norm = min(1.0, max(0.0, int(grade) / 5.0))
    except (TypeError, ValueError):
        grade_norm = 0.0
    ratio = min(1.0, max(0.0, float(gate_ratio)))
    return int(round(100 * (BLEND_GATE * ratio + BLEND_FIDELITY * fid + BLEND_GRADE * grade_norm)))


def gate_severity(name: str, passed: bool) -> str:
    if passed:
        return "advisory"
    critical = {"behaviour_code", "grade_escalation", "fidelity_floor"}
    major = {"placement_valid", "gdd_parity"}
    if name in critical:
        return "critical"
    if name in major:
        return "major"
    return "minor"


def rubric_for_verdict(verdict: Mapping[str, Any], *, grade: int = 0, fidelity: float = 0.0) -> Dict[str, Any]:
    """Build a FE-ready rubric summary from a forge_quality verdict."""
    gates = list(verdict.get("gates") or [])
    weighted = weighted_gate_score(gates)
    raw_prod = verdict.get("production_score")
    if raw_prod is None:
        prod = blend_production_score(gate_ratio=weighted, fidelity=fidelity, grade=grade)
    else:
        prod = int(raw_prod)
    rows: List[Dict[str, Any]] = []
    for g in gates:
        name = str(g.get("name") or "")
        passed = bool(g.get("passed"))
        applicable = _applicable(g)
        rows.append({
            "name": name,
            "passed": passed,
            "applicable": applicable,
            "weight": gate_weight(name),
            "severity": gate_severity(name, passed) if applicable else "advisory",
            "detail": str(g.get("detail") or ""),
            "contribution": round(gate_weight(name) if (passed and applicable) else 0.0, 4),
        })
    failed = [r for r in rows if r["applicable"] and not r["passed"]]
    failed.sort(key=lambda r: SEVERITY_ORDER.index(r["severity"]) if r["severity"] in SEVERITY_ORDER else 99)
    return {
        "kind": "forge-quality-rubric",
        "weighted_score": weighted,
        "production_score": prod,
        "production_tier": production_tier(prod),
        "production_ready": bool(verdict.get("production_ready")) or (
            bool(verdict.get("passed")) and prod >= PRODUCTION_THRESHOLD
        ),
        "grade_band": grade_band(grade),
        "fidelity_band": fidelity_band(fidelity),
        "gates": rows,
        "failed_ordered": [r["name"] for r in failed],
        "not_applicable": [r["name"] for r in rows if not r["applicable"]],
        "critical_failures": [r["name"] for r in failed if r["severity"] == "critical"],
        "weights": dict(GATE_WEIGHTS),
        "thresholds": {
            "production": PRODUCTION_THRESHOLD,
            "staging": STAGING_THRESHOLD,
            "draft": DRAFT_THRESHOLD,
        },
        "stored_prose": 0,
    }


def suggest_next_actions(rubric: Mapping[str, Any], *, max_actions: int = 5) -> List[Dict[str, Any]]:
    """Human/FE actionable next steps ordered by severity."""
    actions: List[Dict[str, Any]] = []
    for name in rubric.get("failed_ordered") or []:
        if name == "grade_escalation":
            actions.append({"gate": name, "action": "raise_grade", "hint": "Bump artefact grade above the stage floor"})
        elif name == "fidelity_floor":
            actions.append({"gate": name, "action": "raise_fidelity", "hint": "Lift skin.fidelity to the stage floor"})
        elif name == "behaviour_code":
            actions.append({"gate": name, "action": "stub_behaviour", "hint": "Ship export const / GDScript func behaviour"})
        elif name == "placement_valid":
            actions.append({"gate": name, "action": "place_region", "hint": "Assign placement.region inside the Vault world"})
        elif name == "gdd_parity":
            actions.append({"gate": name, "action": "align_stage", "hint": "Set stage to a GDD-listed stage key"})
        elif name == "era_compliance":
            actions.append({"gate": name, "action": "tag_era", "hint": "Tag skin.era to the chosen era envelope"})
        else:
            actions.append({"gate": name, "action": "inspect", "hint": f"Inspect failed gate {name}"})
        if len(actions) >= max_actions:
            break
    undeclared = [
        n for n in (rubric.get("not_applicable") or [])
        if n in ("grade_escalation", "fidelity_floor")
    ]
    if not actions and not rubric.get("production_ready") and undeclared:
        # forge_quality never marks an artefact production-ready without a
        # declared grade and fidelity — nudging the score cannot help.
        actions.append({
            "gate": "production_score",
            "action": "declare_signals",
            "hint": "Declare " + " and ".join(
                "grade" if n == "grade_escalation" else "skin.fidelity" for n in undeclared
            ) + " so production gates can apply",
        })
    elif not actions and not rubric.get("production_ready"):
        actions.append({
            "gate": "production_score",
            "action": "nudge_score",
            "hint": "Gates clear but production score below bar — raise grade/fidelity",
        })
    return actions


def compare_rubrics(before: Mapping[str, Any], after: Mapping[str, Any]) -> Dict[str, Any]:
    """Delta between two rubric snapshots (polish round before/after)."""
    b_score = int(before.get("production_score") or 0)
    a_score = int(after.get("production_score") or 0)
    b_failed = set(before.get("failed_ordered") or [])
    a_failed = set(after.get("failed_ordered") or [])
    return {
        "kind": "rubric-delta",
        "score_delta": a_score - b_score,
        "improved": a_score > b_score,
        "gates_cleared": sorted(b_failed - a_failed),
        "gates_regressed": sorted(a_failed - b_failed),
        "still_failing": sorted(a_failed & b_failed),
        "tier_before": before.get("production_tier"),
        "tier_after": after.get("production_tier"),
        "stored_prose": 0,
    }


def rubric_from_item(
    item: Mapping[str, Any],
    verdict: Mapping[str, Any],
) -> Dict[str, Any]:
    skin = item.get("skin") if isinstance(item.get("skin"), Mapping) else {}
    try:
        grade = int(item.get("grade") or 0)
    except (TypeError, ValueError):
        grade = 0
    try:
        fidelity = float((skin or {}).get("fidelity") or item.get("fidelity") or 0)
    except (TypeError, ValueError):
        fidelity = 0.0
    return rubric_for_verdict(verdict, grade=grade, fidelity=fidelity)


__all__ = [
    "GATE_WEIGHTS",
    "BLEND_GATE",
    "BLEND_FIDELITY",
    "BLEND_GRADE",
    "PRODUCTION_THRESHOLD",
    "STAGING_THRESHOLD",
    "DRAFT_THRESHOLD",
    "GRADE_BANDS",
    "FIDELITY_BANDS",
    "gate_weight",
    "grade_band",
    "fidelity_band",
    "production_tier",
    "weighted_gate_score",
    "blend_production_score",
    "gate_severity",
    "rubric_for_verdict",
    "suggest_next_actions",
    "compare_rubrics",
    "rubric_from_item",
]
