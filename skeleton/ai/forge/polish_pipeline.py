"""Polish pipeline — orchestrate evaluate → improve → repair → scorecard.

High-level entry used by FE adapters and forge hooks. Composes:

- ``forge_quality.evaluate`` / ``polish_loop`` / ``improve_against_gates``
- ``repair.attempt_repair`` (optional file repair)
- ``quality_rubric`` + ``polish_scorecard`` for FE payloads
- ``phase_gates.build`` when a forge manifest is supplied

Does **not** touch VerificationLoop, materialise-outbox, cortex, or media/LAFS.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from skeleton.forge.forge_quality import (
    DEFAULT_MAX_ROUNDS,
    PRODUCTION_THRESHOLD,
    evaluate,
    improve_against_gates,
    polish_loop,
)
from skeleton.forge.polish_scorecard import (
    empty_scorecard,
    round_history,
    phase_gate_scorecard,
    progress_from_polish_result,
    scorecard_batch,
    scorecard_for_item,
)
from skeleton.forge.quality_rubric import compare_rubrics


def _ctx(
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions: Sequence[str] = (),
    era: str | None = None,
) -> Dict[str, Any]:
    return {
        "stage_index": int(stage_index),
        "stage_floor_grade": int(stage_floor_grade),
        "gdd_stages": gdd_stages,
        "regions": list(regions or ()),
        "era": era,
    }


def inspect_artefact(
    item: Mapping[str, Any] | None,
    **ctx,
) -> Dict[str, Any]:
    """Read-only quality inspect — scorecard + rubric + next actions."""
    if not item:
        return {
            "kind": "forge-polish-inspect",
            "ok": 0,
            "scorecard": empty_scorecard(reason="no-artefact"),
            "stored_prose": 0,
        }
    c = _ctx(**{k: ctx[k] for k in ("stage_index", "stage_floor_grade", "gdd_stages", "regions", "era") if k in ctx})
    card = scorecard_for_item(item, artefact_id=str(item.get("id") or ""), **c)
    return {
        "kind": "forge-polish-inspect",
        "ok": int(bool(card["production_ready"])),
        "scorecard": card,
        "actions": card["next_actions"],
        "stored_prose": 0,
    }


def run_polish(
    item: Mapping[str, Any],
    *,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    production_threshold: int = PRODUCTION_THRESHOLD,
    persist: bool = True,
    artefact_id: str = "",
    root=None,
    use_file_repair: bool = True,
    repair_files: Optional[Callable[..., Dict[str, Any]]] = None,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions: Sequence[str] = (),
    era: str | None = None,
) -> Dict[str, Any]:
    """Full polish pipeline: bounded loop → scorecard → progress payload."""
    if repair_files is None and use_file_repair:
        from skeleton.forge.repair import attempt_repair
        repair_files = attempt_repair

    before_card = scorecard_for_item(
        item,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
        artefact_id=artefact_id,
    )
    result = polish_loop(
        item,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
        max_rounds=max_rounds,
        production_threshold=production_threshold,
        persist=persist,
        artefact_id=artefact_id,
        root=root,
        repair_files=repair_files,
    )
    after_item = result.get("item") or item
    after_card = scorecard_for_item(
        after_item,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
        artefact_id=artefact_id or str(after_item.get("id") or ""),
        polish_rounds=round_history(result),
    )
    progress = progress_from_polish_result(result)
    delta = compare_rubrics(before_card["rubric"], after_card["rubric"])
    return {
        "kind": "forge-polish-pipeline",
        "ok": int(bool(result.get("production_ready"))),
        "production_ready": bool(result.get("production_ready")),
        "production_score": int(result.get("production_score") or 0),
        "before": before_card,
        "after": after_card,
        "progress": progress,
        "delta": delta,
        "polish": result,
        "item": after_item,
        "persisted": result.get("persisted"),
        "stored_prose": 0,
    }


def one_shot_improve(
    item: Mapping[str, Any],
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions: Sequence[str] = (),
    era: str | None = None,
) -> Dict[str, Any]:
    """Single improve_against_gates pass without the full polish loop."""
    working = deepcopy(dict(item))
    verdict = evaluate(
        working,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
    )
    actions = improve_against_gates(
        working,
        verdict,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
    )
    after = evaluate(
        working,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
    )
    return {
        "kind": "forge-polish-one-shot",
        "ok": int(bool(after.get("production_ready"))),
        "before": verdict,
        "after": after,
        "actions": actions,
        "item": working,
        "scorecard": scorecard_for_item(
            working,
            stage_index=stage_index,
            stage_floor_grade=stage_floor_grade,
            gdd_stages=gdd_stages,
            regions=regions,
            era=era,
        ),
        "stored_prose": 0,
    }


def batch_polish(
    items: Sequence[Mapping[str, Any]],
    *,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    production_threshold: int = PRODUCTION_THRESHOLD,
    persist: bool = False,
    root=None,
    use_file_repair: bool = False,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions: Sequence[str] = (),
    era: str | None = None,
) -> Dict[str, Any]:
    """Polish a batch of artefacts; return per-item pipelines + rollup."""
    pipelines: List[Dict[str, Any]] = []
    for item in items:
        pipelines.append(
            run_polish(
                item,
                max_rounds=max_rounds,
                production_threshold=production_threshold,
                persist=persist,
                artefact_id=str(item.get("id") or item.get("name") or ""),
                root=root,
                use_file_repair=use_file_repair,
                stage_index=stage_index,
                stage_floor_grade=stage_floor_grade,
                gdd_stages=gdd_stages,
                regions=regions,
                era=era,
            )
        )
    after_items = [p["item"] for p in pipelines]
    batch = scorecard_batch(
        after_items,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
    )
    ready_n = sum(1 for p in pipelines if p.get("production_ready"))
    return {
        "kind": "forge-polish-batch",
        "ok": int(ready_n == len(pipelines) and len(pipelines) > 0),
        "count": len(pipelines),
        "production_ready_count": ready_n,
        "pipelines": pipelines,
        "batch_scorecard": batch,
        "stored_prose": 0,
    }


def qc_dashboard(
    items: Sequence[Mapping[str, Any]],
    *,
    manifest: Optional[Mapping[str, Any]] = None,
    assets: Optional[Mapping[str, Any]] = None,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions: Sequence[str] = (),
    era: str | None = None,
) -> Dict[str, Any]:
    """QC control-plane payload: batch scorecards + optional phase-gate ladder."""
    batch = scorecard_batch(
        items,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
    )
    phase = phase_gate_scorecard(manifest, assets) if manifest else None
    # Top repair CTAs across the batch (deduped by gate).
    cta_map: Dict[str, Dict[str, Any]] = {}
    for card in batch.get("cards") or []:
        for action in card.get("next_actions") or []:
            gate = str(action.get("gate") or "")
            if gate and gate not in cta_map:
                cta_map[gate] = {**action, "artefact_id": card.get("artefact_id")}
    return {
        "kind": "forge-qc-dashboard",
        "ok": int(bool(batch.get("all_production_ready"))),
        "batch": batch,
        "phase_gates": phase,
        "repair_ctas": list(cta_map.values()),
        "summary": {
            "count": batch.get("count"),
            "ready": batch.get("production_ready_count"),
            "blocked": batch.get("blocked_count"),
            "triage": batch.get("triage"),
            "phase_all_green": (phase or {}).get("all_gates_green") if phase else None,
        },
        "stored_prose": 0,
    }


def repair_cta_payload(
    item: Mapping[str, Any],
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions: Sequence[str] = (),
    era: str | None = None,
) -> Dict[str, Any]:
    """Payload for the FE Repair CTA button (enabled + primary action)."""
    card = scorecard_for_item(
        item,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
    )
    actions = card.get("next_actions") or []
    primary = actions[0] if actions else None
    return {
        "kind": "forge-repair-cta",
        "enabled": bool(card.get("repair_eligible")),
        "label": "Run polish repair" if card.get("repair_eligible") else "Production ready",
        "primary_action": primary,
        "actions": actions,
        "failed_gates": card.get("failed_gates") or [],
        "production_score": card.get("production_score"),
        "production_threshold": PRODUCTION_THRESHOLD,
        "artefact_id": card.get("artefact_id"),
        "testID": "forge-repair-cta",
        "a11yLabel": (
            f"Repair {len(card.get('failed_gates') or [])} failed gates"
            if card.get("repair_eligible")
            else "Artefact is production ready"
        ),
        "stored_prose": 0,
    }


def pipeline_from_polish_artefact(
    item: Mapping[str, Any],
    *,
    root=None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions=(),
    era: str | None = None,
    artefact_id: str = "",
    use_file_repair: bool = True,
) -> Dict[str, Any]:
    """Bridge ``repair.polish_artefact`` into the pipeline scorecard shape."""
    from skeleton.forge.repair import polish_artefact

    raw = polish_artefact(
        item,
        root=root,
        max_rounds=max_rounds,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
        artefact_id=artefact_id,
        use_file_repair=use_file_repair,
    )
    after_item = raw.get("item") or item
    after_card = scorecard_for_item(
        after_item,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
        artefact_id=artefact_id,
        polish_rounds=round_history(raw),
    )
    return {
        "kind": "forge-polish-pipeline",
        "ok": int(bool(raw.get("production_ready") or raw.get("ok"))),
        "production_ready": bool(raw.get("production_ready")),
        "production_score": int(raw.get("production_score") or raw.get("score") or 0),
        "after": after_card,
        "progress": progress_from_polish_result(raw),
        "polish": raw,
        "item": after_item,
        "persisted": raw.get("persisted"),
        "stored_prose": 0,
    }


__all__ = [
    "inspect_artefact",
    "run_polish",
    "one_shot_improve",
    "batch_polish",
    "qc_dashboard",
    "repair_cta_payload",
    "pipeline_from_polish_artefact",
]
