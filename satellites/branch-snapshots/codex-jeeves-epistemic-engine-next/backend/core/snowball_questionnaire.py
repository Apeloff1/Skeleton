"""
╔════════════════════════════════════════════════════════════════════════╗
║  SNOWBALL QUESTIONNAIRE — proves every step matches the locked choices. ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Walks the snowball result + choice ledger and answers a checklist of    ║
║  conformance questions (each with expected vs actual). The overall       ║
║  conformance % tells you whether every step corresponds to the choices   ║
║  the game was started with.                                              ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from typing import Any

from core import eras as eras_mod


def _q(qid: str, question: str, expected: Any, actual: Any, passed: bool) -> dict:
    return {"id": qid, "question": question, "expected": expected,
            "actual": actual, "passed": bool(passed)}


def build(manifest: dict) -> dict:
    """Answer the conformance questionnaire from a snowball manifest."""
    aw = manifest.get("awareness") or {}
    ladder = manifest.get("ladder") or []
    totals = manifest.get("totals") or {}
    storage = manifest.get("storage") or {}
    cap = manifest.get("capacity") or {}
    era = eras_mod.get_era(manifest.get("era"))
    items: list[dict] = []

    # ── global conformance ──
    items.append(_q("era_locked", "Is the chosen era locked into the ledger?",
                    manifest.get("era"), aw.get("era"),
                    aw.get("era") == manifest.get("era")))
    items.append(_q("genre_locked", "Is the chosen genre tracked for the game?",
                    manifest.get("genre"), aw.get("genre"),
                    aw.get("genre") == manifest.get("genre")))
    items.append(_q("every_stage_logged",
                    "Did every snowball stage log a choice?",
                    manifest.get("stages"), len(aw.get("stages_done", [])),
                    len(aw.get("stages_done", [])) == manifest.get("stages")))
    items.append(_q("gdd_parity_every_step",
                    "Was GDD↔gamefile parity held on every step?",
                    True, manifest.get("parity_locked"),
                    bool(manifest.get("parity_locked"))))
    floors = [r["grade_floor"] for r in ladder]
    floors_escalate = all(floors[i] <= floors[i + 1] for i in range(len(floors) - 1))
    items.append(_q("grade_escalates",
                    "Does each stage escalate above the previous grade floor?",
                    True, floors_escalate, floors_escalate))
    gf = totals.get("gamefiles", 0) or 0
    assets = totals.get("assets", 0) or 0
    per_item = (assets / gf) if gf else 0
    assets_ok = assets > 0 and gf > 0 and assets % gf == 0 and per_item <= len(era["asset_types"])
    items.append(_q("assets_era_appropriate",
                    "Does every gamefile get a uniform, era-bounded asset pack?",
                    f"≤ {len(era['asset_types'])}/gamefile", int(per_item), assets_ok))
    items.append(_q("within_capacity",
                    "Are forged assets within the era's outshine capacity?",
                    f"≤ {era['asset_capacity']}", cap.get("assets_forged"),
                    int(cap.get("assets_forged", 0)) <= era["asset_capacity"]))
    items.append(_q("storage_tracked",
                    "Is storage tracked against the era cap?",
                    storage.get("cap_label"), storage.get("used_label"),
                    "used_pct" in storage))

    # ── per-stage conformance (snowball: built on prior stages) ──
    for i, r in enumerate(ladder):
        if i == 0:
            ok = True
            exp, act = "foundation stage", "ok"
        else:
            ok = len(r.get("built_on", [])) == i
            exp, act = f"built on {i} prior stage(s)", f"built on {len(r.get('built_on', []))}"
        items.append(_q(f"stage_{r['stage']}_snowball",
                        f"Lv{r['level']} · does '{r['stage']}' build on prior stages?",
                        exp, act, ok))

    passed = sum(1 for it in items if it["passed"])
    # ── per-choice conformance: every advanced choice reflected every step ──
    cg = manifest.get("choice_gates") or {}
    for g in cg.get("gates", []):
        items.append(_q(f"choice_{g['key']}",
                        f"Is '{g['label']}' ({g['want']}) reflected in every {' & '.join(g['reflected_in'])}?",
                        g["want"], g["detail"], g["passed"]))
    passed = sum(1 for it in items if it["passed"])
    return {
        "build_id": manifest.get("build_id"),
        "era": manifest.get("era"),
        "choices_gated": cg.get("choices_gated", 0),
        "items": items,
        "passed": passed,
        "total": len(items),
        "conformance_pct": round(100 * passed / max(1, len(items))),
        "all_conformant": passed == len(items),
    }
