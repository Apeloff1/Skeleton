"""Forge quality gates + bounded polish loop for forge artefacts.

Ported from Apeloff1/Prood ``backend/core/forge_quality.py`` (and the
one-tap polish sequencing idea from ``playable_polish.py``), adapted to
Skeleton's forge surface:

- Deterministic quality gates on forged item/blueprint dicts
- 0–1 gate score + 0–100 production score with a production threshold
- Persist verdicts via ``organism.quality_state``
- Bounded polish loop that patches failed gates then re-evaluates,
  composing with ``BlueprintValidator`` / ``attempt_repair`` when useful

Does **not** own VerificationLoop or materialise-verify paths.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Optional, Sequence, Set, Union

from skeleton.forge.eras import ERA_IDS
from skeleton.organism.quality_state import append_quality

# Quality-control bar: an item must score ≥ this (0-100) to enter production.
PRODUCTION_THRESHOLD = 95

# Default polish bound — keep the improve/repair loop small (S–M scope).
DEFAULT_MAX_ROUNDS = 3

GddStages = Union[Set[str], Sequence[str]]


def fidelity_floor(stage_index: int) -> float:
    """The visual-fidelity bar rises as the snowball escalates."""
    return round(0.72 + max(0, int(stage_index)) * 0.02, 3)


def era_compliance(item: Mapping[str, Any], era_key: str | None) -> Dict[str, Any]:
    """Validate a forged item against Skeleton era ids (Prood-shaped gate)."""
    key = (era_key or "").strip()
    skin = item.get("skin") or {}
    if not key:
        return {
            "era": "",
            "passed": False,
            "failed": ["era_missing"],
            "checks": [{"name": "era_known", "passed": False}],
        }
    known = key in ERA_IDS
    tagged = (skin.get("era") == key) if isinstance(skin, Mapping) else False
    checks = [
        ("era_known", known),
        ("era_tagged", tagged or not bool(skin)),
    ]
    # Soft envelope when Prood-style skin budgets are present.
    if isinstance(skin, Mapping) and "palette" in skin:
        palette = skin.get("palette") or []
        checks.append(("palette_bounded", isinstance(palette, list) and len(palette) <= 32))
    if isinstance(skin, Mapping) and "poly_budget" in skin:
        try:
            poly = int(skin.get("poly_budget") or 0)
        except (TypeError, ValueError):
            poly = -1
        checks.append(("poly_nonneg", poly >= 0))
    failed = [n for n, ok in checks if not ok]
    return {
        "era": key,
        "passed": not failed,
        "failed": failed,
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
    }


def _behaviour_ok(item: Mapping[str, Any]) -> bool:
    """Accept Prood JS, Godot GDScript, or Skeleton blueprint systems with behaviour."""
    code = item.get("code") or ""
    if isinstance(code, str) and ("export const" in code or "func " in code or "extends " in code):
        return True
    files = item.get("files")
    if isinstance(files, Mapping):
        for path, src in files.items():
            text = src if isinstance(src, str) else ""
            if str(path).endswith(".gd") and ("func " in text or "extends " in text):
                return True
            if str(path).endswith((".js", ".ts", ".mjs")) and "export const" in text:
                return True
    systems = item.get("systems")
    if isinstance(systems, list) and systems:
        for sys in systems:
            if isinstance(sys, Mapping) and (sys.get("behaviour") or sys.get("code") or sys.get("id")):
                return True
    components = item.get("components")
    if isinstance(components, Mapping) and components:
        return True
    if isinstance(components, list) and components:
        return True
    return False


def evaluate(
    item: Mapping[str, Any],
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages: GddStages = (),
    regions: Sequence[str] = (),
    era: str | None = None,
) -> Dict[str, Any]:
    """Run quality gates against one forged artefact. Pure & deterministic."""
    skin = item.get("skin") if isinstance(item.get("skin"), Mapping) else {}
    placement = item.get("placement") if isinstance(item.get("placement"), Mapping) else {}
    floor = fidelity_floor(stage_index)
    gdd_set = set(gdd_stages or ())
    region_list = list(regions or ())

    grade_raw = item.get("grade", 0)
    try:
        grade = int(grade_raw)
    except (TypeError, ValueError):
        grade = 0

    fidelity_raw = skin.get("fidelity", 0) if skin else item.get("fidelity", 0)
    try:
        fidelity = float(fidelity_raw or 0)
    except (TypeError, ValueError):
        fidelity = 0.0

    region = placement.get("region") if placement else item.get("region")
    stage = item.get("stage")

    gates: List[Dict[str, Any]] = [
        {
            "name": "grade_escalation",
            "passed": grade > int(stage_floor_grade),
            "detail": f"grade {grade} > floor {stage_floor_grade}",
        },
        {
            "name": "fidelity_floor",
            "passed": fidelity >= floor,
            "detail": f"fidelity {fidelity} ≥ {floor}",
        },
        {
            "name": "behaviour_code",
            "passed": _behaviour_ok(item),
            "detail": "ships executable behaviour",
        },
        {
            "name": "placement_valid",
            "passed": bool(region) and (not region_list or region in region_list),
            "detail": f"region {region!r} in Vault world",
        },
        {
            "name": "gdd_parity",
            "passed": (not gdd_set) or (stage in gdd_set),
            "detail": f"stage {stage!r} present in GDD",
        },
    ]

    era_key = era or (skin.get("era") if skin else None) or item.get("era")
    if era_key:
        comp = era_compliance(item, str(era_key))
        gates.append(
            {
                "name": "era_compliance",
                "passed": bool(comp["passed"]),
                "detail": (
                    f"fits {comp['era']} envelope"
                    if comp["passed"]
                    else "violates: " + ", ".join(comp["failed"])
                ),
            }
        )

    passed_n = sum(1 for g in gates if g["passed"])
    score = round(passed_n / len(gates), 3) if gates else 0.0
    failed = [g["name"] for g in gates if not g["passed"]]
    gate_ratio = passed_n / len(gates) if gates else 0.0
    grade_norm = min(1.0, max(0.0, grade / 5.0))
    production_score = round(100 * (0.7 * gate_ratio + 0.15 * min(1.0, fidelity) + 0.15 * grade_norm))
    all_passed = passed_n == len(gates)
    return {
        "passed": all_passed,
        "score": score,
        "production_score": production_score,
        "production_ready": all_passed and production_score >= PRODUCTION_THRESHOLD,
        "gates": gates,
        "failed_gates": failed,
        "fidelity_floor": floor,
        "verdict": (
            "folded into gamefiles"
            if all_passed
            else "rejected: " + ", ".join(failed)
        ),
    }


def summarize(verdicts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate quality across a batch of forged items."""
    if not verdicts:
        return {
            "count": 0,
            "accepted": 0,
            "rejected": 0,
            "avg_score": 0.0,
            "avg_production_score": 0.0,
            "production_ready": 0,
            "gate_pass_rate": {},
            "all_passed": True,
            "all_production_ready": True,
        }
    total = len(verdicts)
    accepted = sum(1 for v in verdicts if v.get("passed"))
    prod_ready = sum(1 for v in verdicts if v.get("production_ready"))
    first_gates = list(verdicts[0].get("gates") or [])
    gate_names = [g.get("name") for g in first_gates if g.get("name")]
    rates: Dict[str, float] = {}
    for name in gate_names:
        ok = sum(
            1
            for v in verdicts
            for g in (v.get("gates") or [])
            if g.get("name") == name and g.get("passed")
        )
        rates[str(name)] = round(ok / total, 3)
    return {
        "count": total,
        "accepted": accepted,
        "rejected": total - accepted,
        "avg_score": round(sum(float(v.get("score") or 0) for v in verdicts) / total, 3),
        "avg_production_score": round(
            sum(float(v.get("production_score") or 0) for v in verdicts) / total, 1
        ),
        "production_ready": prod_ready,
        "gate_pass_rate": rates,
        "all_passed": accepted == total,
        "all_production_ready": prod_ready == total,
    }


def persist_quality(
    verdict: Mapping[str, Any],
    *,
    artefact_id: str = "",
    surface: str = "forge",
    root=None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist a forge-quality verdict onto the organism quality log."""
    meta = dict(metadata or {})
    meta.setdefault("kind", "forge_quality")
    meta.setdefault("artefact_id", artefact_id)
    meta.setdefault("production_score", verdict.get("production_score"))
    meta.setdefault("production_ready", verdict.get("production_ready"))
    meta.setdefault("failed_gates", list(verdict.get("failed_gates") or []))
    entry = {
        "kind": "quality",
        "surface": surface,
        "accepted": bool(verdict.get("passed")),
        "reason": str(verdict.get("verdict") or ("accepted" if verdict.get("passed") else "rejected")),
        "score": float(verdict.get("score") or 0.0),
        "weakest_path": artefact_id or ",".join(verdict.get("failed_gates") or [])[:120],
        "summary": {
            "production_score": int(verdict.get("production_score") or 0),
            "production_ready": int(bool(verdict.get("production_ready"))),
            "gate_count": len(verdict.get("gates") or []),
            "failed_count": len(verdict.get("failed_gates") or []),
        },
        "metadata": meta,
        "evidence": {
            "gates": list(verdict.get("gates") or []),
            "failed_gates": list(verdict.get("failed_gates") or []),
            "fidelity_floor": verdict.get("fidelity_floor"),
        },
    }
    return append_quality(entry, root=root)


def improve_against_gates(
    item: MutableMapping[str, Any],
    verdict: Mapping[str, Any],
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages: GddStages = (),
    regions: Sequence[str] = (),
    era: str | None = None,
) -> List[Dict[str, Any]]:
    """Deterministic one-shot patches for failed quality gates. Mutates ``item``."""
    actions: List[Dict[str, Any]] = []
    failed = set(verdict.get("failed_gates") or [])
    floor = fidelity_floor(stage_index)
    gdd_list = list(gdd_stages or ())
    region_list = list(regions or ())
    era_key = era or item.get("era")

    if "grade_escalation" in failed:
        target = int(stage_floor_grade) + 1
        item["grade"] = max(int(item.get("grade") or 0), target)
        actions.append({"gate": "grade_escalation", "action": f"raised grade to {item['grade']}"})

    if "fidelity_floor" in failed:
        skin = dict(item.get("skin") or {})
        skin["fidelity"] = max(float(skin.get("fidelity") or 0), floor)
        item["skin"] = skin
        actions.append({"gate": "fidelity_floor", "action": f"raised fidelity to {skin['fidelity']}"})

    if "behaviour_code" in failed:
        code = item.get("code") or ""
        if not isinstance(code, str) or not code.strip():
            item["code"] = "export const behaviour = { tick() {} };\n"
            actions.append({"gate": "behaviour_code", "action": "stubbed export const behaviour"})
        elif "export const" not in code and "func " not in code:
            item["code"] = code.rstrip() + "\nexport const behaviour = { tick() {} };\n"
            actions.append({"gate": "behaviour_code", "action": "appended export const behaviour"})

    if "placement_valid" in failed:
        placement = dict(item.get("placement") or {})
        if region_list:
            placement["region"] = region_list[0]
        elif not placement.get("region"):
            placement["region"] = "default"
        item["placement"] = placement
        actions.append({"gate": "placement_valid", "action": f"set region {placement['region']!r}"})

    if "gdd_parity" in failed:
        if gdd_list:
            item["stage"] = gdd_list[0]
            actions.append({"gate": "gdd_parity", "action": f"set stage {item['stage']!r}"})
        elif not item.get("stage"):
            item["stage"] = "stage_0"
            actions.append({"gate": "gdd_parity", "action": "set stage 'stage_0'"})

    if "era_compliance" in failed and era_key:
        skin = dict(item.get("skin") or {})
        skin["era"] = str(era_key)
        item["skin"] = skin
        item["era"] = str(era_key)
        if "palette" in skin and isinstance(skin["palette"], list) and len(skin["palette"]) > 32:
            skin["palette"] = list(skin["palette"][:32])
        if "poly_budget" in skin:
            try:
                if int(skin.get("poly_budget") or 0) < 0:
                    skin["poly_budget"] = 0
            except (TypeError, ValueError):
                skin["poly_budget"] = 0
        actions.append({"gate": "era_compliance", "action": f"tagged era {era_key!r}"})

    # Gates clear but production score still below bar — nudge grade/fidelity.
    if not failed and not bool(verdict.get("production_ready")):
        skin = dict(item.get("skin") or {})
        try:
            fid = float(skin.get("fidelity") or 0)
        except (TypeError, ValueError):
            fid = 0.0
        if fid < 1.0:
            skin["fidelity"] = round(min(1.0, max(fid, floor, 0.95)), 3)
            item["skin"] = skin
            actions.append({"gate": "production_score", "action": f"raised fidelity to {skin['fidelity']}"})
        try:
            grade = int(item.get("grade") or 0)
        except (TypeError, ValueError):
            grade = 0
        if grade < 5:
            item["grade"] = 5
            actions.append({"gate": "production_score", "action": "raised grade to 5"})

    return actions


def polish_loop(
    item: Mapping[str, Any],
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages: GddStages = (),
    regions: Sequence[str] = (),
    era: str | None = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    production_threshold: int = PRODUCTION_THRESHOLD,
    persist: bool = True,
    artefact_id: str = "",
    root=None,
    repair_files: Optional[Callable[..., Dict[str, Any]]] = None,
    compose_blueprint_validator: bool = True,
) -> Dict[str, Any]:
    """Bounded improve/repair loop against quality thresholds.

    Each round: evaluate → stop if production-ready → patch failed gates
    (and optionally run ``attempt_repair`` on embedded ``files``) → re-evaluate.
    Composes with ``BlueprintValidator`` when the artefact looks like a blueprint.
    """
    working: Dict[str, Any] = deepcopy(dict(item))
    rounds: List[Dict[str, Any]] = []
    max_rounds = max(1, int(max_rounds))
    threshold = int(production_threshold)

    blueprint_validation: Optional[Dict[str, Any]] = None
    if compose_blueprint_validator and _looks_like_blueprint(working):
        from skeleton.forge.validators import BlueprintValidator

        blueprint_validation = BlueprintValidator().validate(working).to_dict()

    final_verdict: Dict[str, Any] = {}
    for i in range(max_rounds):
        verdict = evaluate(
            working,
            stage_index=stage_index,
            stage_floor_grade=stage_floor_grade,
            gdd_stages=gdd_stages,
            regions=regions,
            era=era,
        )
        # Honour caller threshold override for production_ready in-loop.
        production_ready = bool(verdict["passed"]) and int(verdict["production_score"]) >= threshold
        verdict = dict(verdict)
        verdict["production_ready"] = production_ready

        round_actions: List[Dict[str, Any]] = []
        file_repair: Optional[Dict[str, Any]] = None
        if not production_ready:
            round_actions = improve_against_gates(
                working,
                verdict,
                stage_index=stage_index,
                stage_floor_grade=stage_floor_grade,
                gdd_stages=gdd_stages,
                regions=regions,
                era=era,
            )
            if repair_files and isinstance(working.get("files"), Mapping):
                file_repair = repair_files(
                    working["files"],
                    request=f"forge-quality polish round {i + 1}",
                    root=root,
                )
                if file_repair.get("files"):
                    working["files"] = dict(file_repair["files"])
                    if file_repair.get("actions"):
                        round_actions.append(
                            {
                                "gate": "file_repair",
                                "action": f"{len(file_repair['actions'])} file repair action(s)",
                            }
                        )

        after = evaluate(
            working,
            stage_index=stage_index,
            stage_floor_grade=stage_floor_grade,
            gdd_stages=gdd_stages,
            regions=regions,
            era=era,
        )
        after = dict(after)
        after["production_ready"] = bool(after["passed"]) and int(after["production_score"]) >= threshold

        rounds.append(
            {
                "round": i + 1,
                "before": verdict,
                "actions": round_actions,
                "file_repair_ok": None if file_repair is None else int(bool(file_repair.get("ok"))),
                "after": after,
            }
        )
        final_verdict = after
        if after.get("production_ready"):
            break
        if not round_actions and file_repair is None:
            break

    persisted = None
    if persist:
        persisted = persist_quality(
            final_verdict,
            artefact_id=artefact_id or str(working.get("id") or working.get("name") or "forge-artefact"),
            root=root,
            metadata={
                "polish_rounds": len(rounds),
                "production_threshold": threshold,
            },
        )

    return {
        "kind": "forge-quality-polish",
        "ok": int(bool(final_verdict.get("production_ready"))),
        "passed": bool(final_verdict.get("passed")),
        "production_ready": bool(final_verdict.get("production_ready")),
        "score": final_verdict.get("score"),
        "production_score": final_verdict.get("production_score"),
        "rounds": rounds,
        "round_count": len(rounds),
        "item": working,
        "quality": final_verdict,
        "blueprint_validation": blueprint_validation,
        "persisted": persisted,
        "stored_prose": 0,
    }


def evaluate_and_persist(
    item: Mapping[str, Any],
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages: GddStages = (),
    regions: Sequence[str] = (),
    era: str | None = None,
    artefact_id: str = "",
    root=None,
) -> Dict[str, Any]:
    """Evaluate once and persist — convenience for forge materialise hooks."""
    verdict = evaluate(
        item,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
    )
    row = persist_quality(
        verdict,
        artefact_id=artefact_id or str(item.get("id") or item.get("name") or ""),
        root=root,
    )
    return {"quality": verdict, "persisted": row}


def _looks_like_blueprint(item: Mapping[str, Any]) -> bool:
    return "systems" in item and ("name" in item or "version" in item)


__all__ = [
    "PRODUCTION_THRESHOLD",
    "DEFAULT_MAX_ROUNDS",
    "fidelity_floor",
    "era_compliance",
    "evaluate",
    "summarize",
    "persist_quality",
    "improve_against_gates",
    "polish_loop",
    "evaluate_and_persist",
]
