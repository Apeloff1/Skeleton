"""Polish scorecard — batch + single-artefact FE payloads for forge quality.

Turns ``forge_quality`` verdicts + ``quality_rubric`` into a stable scorecard
shape a cockpit/FE panel can render without recomputing gates. Also aggregates
phase-gate band status when a forge manifest is available.

Extend-only: does not own materialise / VerificationLoop / cortex.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from skeleton.forge.forge_quality import (
    PRODUCTION_THRESHOLD,
    evaluate,
    summarize,
)
from skeleton.forge.quality_rubric import (
    compare_rubrics,
    rubric_from_item,
    suggest_next_actions,
)


def _skin_fidelity(item: Mapping[str, Any]) -> float:
    skin = item.get("skin") if isinstance(item.get("skin"), Mapping) else {}
    try:
        return float((skin or {}).get("fidelity") or item.get("fidelity") or 0)
    except (TypeError, ValueError):
        return 0.0


def _grade(item: Mapping[str, Any]) -> int:
    try:
        return int(item.get("grade") or 0)
    except (TypeError, ValueError):
        return 0


def _era_of(item: Mapping[str, Any], era: str | None) -> Optional[str]:
    if era:
        return era
    skin = item.get("skin") if isinstance(item.get("skin"), Mapping) else {}
    return (skin or {}).get("era") or item.get("era")


def _region_of(item: Mapping[str, Any]) -> Any:
    placement = item.get("placement")
    if isinstance(placement, Mapping):
        return placement.get("region")
    return item.get("region")


def round_history(result: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Per-round trace from a polish_loop result.

    ``polish_loop`` reports ``rounds`` as an executed-round count and the
    trace under ``round_history``; older payloads carried the list in
    ``rounds``. Accept both.
    """
    hist = result.get("round_history")
    if isinstance(hist, list):
        return hist
    rounds = result.get("rounds")
    return rounds if isinstance(rounds, list) else []


def gate_chips(verdict: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Compact chips for the FE gate row."""
    chips: List[Dict[str, Any]] = []
    for g in verdict.get("gates") or []:
        name = str(g.get("name") or "")
        passed = bool(g.get("passed"))
        applicable = bool(g.get("applicable", True))
        chips.append({
            "id": name,
            "label": name.replace("_", " "),
            "passed": passed,
            "applicable": applicable,
            "tone": "muted" if not applicable else ("good" if passed else "warn"),
            "detail": str(g.get("detail") or ""),
            "testID": f"gate-chip-{name}",
        })
    return chips


def scorecard_for_item(
    item: Mapping[str, Any],
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions: Sequence[str] = (),
    era: str | None = None,
    artefact_id: str = "",
    polish_rounds: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Single-artefact scorecard ready for ForgePolish panels."""
    verdict = evaluate(
        item,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
    )
    rubric = rubric_from_item(item, verdict)
    actions = suggest_next_actions(rubric)
    rounds = list(polish_rounds or [])
    round_deltas: List[Dict[str, Any]] = []
    for i, rnd in enumerate(rounds):
        before = rnd.get("before") or {}
        after = rnd.get("after") or {}
        # Round payloads from polish_loop carry full verdicts; wrap as mini-rubrics.
        b_rub = rubric_from_item(item, before) if before.get("gates") else {
            "production_score": int(before.get("production_score") or before.get("score") or 0),
            "failed_ordered": list(before.get("failed_gates") or []),
            "production_tier": "unknown",
        }
        a_rub = rubric_from_item(item, after) if after.get("gates") else {
            "production_score": int(after.get("production_score") or after.get("score") or 0),
            "failed_ordered": list(after.get("failed_gates") or []),
            "production_tier": "unknown",
        }
        delta = compare_rubrics(b_rub, a_rub)
        delta["round"] = int(rnd.get("round") or i + 1)
        delta["actions"] = list(rnd.get("actions") or [])
        round_deltas.append(delta)

    return {
        "kind": "forge-polish-scorecard",
        "artefact_id": artefact_id or str(item.get("id") or item.get("name") or ""),
        "title": str(item.get("title") or item.get("name") or artefact_id or "artefact"),
        "grade": _grade(item),
        "fidelity": _skin_fidelity(item),
        "era": _era_of(item, era),
        "stage": item.get("stage"),
        "region": _region_of(item),
        "quality": verdict,
        "rubric": rubric,
        "chips": gate_chips(verdict),
        "next_actions": actions,
        "production_score": int(verdict.get("production_score") or 0),
        "production_ready": bool(verdict.get("production_ready")),
        "production_threshold": PRODUCTION_THRESHOLD,
        "passed": bool(verdict.get("passed")),
        "failed_gates": list(verdict.get("failed_gates") or []),
        "round_deltas": round_deltas,
        "round_count": len(rounds),
        "repair_eligible": bool(verdict.get("failed_gates")) or not bool(verdict.get("production_ready")),
        "stored_prose": 0,
    }


def scorecard_batch(
    items: Sequence[Mapping[str, Any]],
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions: Sequence[str] = (),
    era: str | None = None,
) -> Dict[str, Any]:
    """Batch scorecards + rollup for QC overview panels."""
    cards: List[Dict[str, Any]] = []
    verdicts: List[Dict[str, Any]] = []
    for item in items:
        card = scorecard_for_item(
            item,
            stage_index=stage_index,
            stage_floor_grade=stage_floor_grade,
            gdd_stages=gdd_stages,
            regions=regions,
            era=era,
        )
        cards.append(card)
        verdicts.append(card["quality"])
    rollup = summarize(verdicts)
    ready = [c for c in cards if c["production_ready"]]
    blocked = [c for c in cards if not c["production_ready"]]
    # Aggregate most common failed gates for the QC triage list.
    fail_counts: Dict[str, int] = {}
    for c in blocked:
        for g in c["failed_gates"]:
            fail_counts[g] = fail_counts.get(g, 0) + 1
    triage = sorted(
        [{"gate": k, "count": v} for k, v in fail_counts.items()],
        key=lambda row: (-row["count"], row["gate"]),
    )
    return {
        "kind": "forge-polish-scorecard-batch",
        "count": len(cards),
        "production_ready_count": len(ready),
        "blocked_count": len(blocked),
        "cards": cards,
        "rollup": rollup,
        "triage": triage,
        "production_threshold": PRODUCTION_THRESHOLD,
        "all_production_ready": len(ready) == len(cards) and len(cards) > 0,
        "stored_prose": 0,
    }


def phase_gate_scorecard(manifest: Mapping[str, Any], assets: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Wrap ``phase_gates.build`` as a FE scorecard for the QA/Polish band."""
    from skeleton.forge import phase_gates as pg

    ladder = pg.build(dict(manifest), dict(assets or {}))
    bands = list(ladder.get("bands") or [])
    qa = next((b for b in bands if b.get("band") == "QA / Polish"), None)
    chips = [
        {
            "id": str(b.get("gate") or b.get("band")),
            "label": str(b.get("band") or ""),
            "passed": bool(b.get("passed")),
            "tone": "good" if b.get("passed") else "warn",
            "detail": str(b.get("detail") or ""),
            "testID": f"phase-band-{b.get('band', '').replace(' ', '-').lower()}",
        }
        for b in bands
    ]
    return {
        "kind": "phase-gate-scorecard",
        "all_gates_green": bool(ladder.get("all_gates_green")),
        "pass_pct": int(ladder.get("pass_pct") or 0),
        "bands_passed": int(ladder.get("bands_passed") or 0),
        "bands_total": int(ladder.get("bands_total") or 0),
        "qa_polish": qa,
        "chips": chips,
        "file_plan": ladder.get("file_plan"),
        "ladder": ladder,
        "stored_prose": 0,
    }


def progress_from_polish_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalise a polish_loop / polish_artefact result into FE progress state."""
    rounds = round_history(result)
    steps: List[Dict[str, Any]] = []
    for rnd in rounds:
        after = rnd.get("after") or {}
        steps.append({
            "round": int(rnd.get("round") or len(steps) + 1),
            "production_score": int(after.get("production_score") or 0),
            "passed": bool(after.get("passed")),
            "production_ready": bool(after.get("production_ready")),
            "failed_gates": list(after.get("failed_gates") or []),
            "actions": list(rnd.get("actions") or []),
            "status": (
                "ready" if after.get("production_ready")
                else "improved" if rnd.get("actions")
                else "stalled"
            ),
        })
    return {
        "kind": "polish-loop-progress",
        "ok": int(bool(result.get("ok") or result.get("production_ready"))),
        "production_ready": bool(result.get("production_ready")),
        "production_score": int(result.get("production_score") or 0),
        "round_count": int(result.get("round_count") or len(rounds)),
        "rounds_executed": int(result.get("rounds")) if isinstance(result.get("rounds"), int) else len(rounds),
        "steps": steps,
        "current_round": len(steps),
        "max_rounds": max(len(steps), 1),
        "verdict": (result.get("quality") or {}).get("verdict") if isinstance(result.get("quality"), Mapping) else None,
        "stored_prose": 0,
    }


def empty_scorecard(*, reason: str = "no-artefact") -> Dict[str, Any]:
    """Empty/loading placeholder the FE can render without null checks."""
    return {
        "kind": "forge-polish-scorecard",
        "artefact_id": "",
        "title": "",
        "empty": True,
        "empty_reason": reason,
        "grade": 0,
        "fidelity": 0.0,
        "quality": {"passed": False, "gates": [], "failed_gates": [], "production_score": 0},
        "rubric": {"gates": [], "failed_ordered": [], "production_tier": "reject", "production_score": 0},
        "chips": [],
        "next_actions": [],
        "production_score": 0,
        "production_ready": False,
        "production_threshold": PRODUCTION_THRESHOLD,
        "passed": False,
        "failed_gates": [],
        "round_deltas": [],
        "round_count": 0,
        "repair_eligible": False,
        "stored_prose": 0,
    }


__all__ = [
    "round_history",
    "gate_chips",
    "scorecard_for_item",
    "scorecard_batch",
    "phase_gate_scorecard",
    "progress_from_polish_result",
    "empty_scorecard",
]
