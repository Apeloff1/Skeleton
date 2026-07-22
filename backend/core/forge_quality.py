"""
╔════════════════════════════════════════════════════════════════════════╗
║  FORGE QUALITY GATES — every forge must clear escalating quality bars.   ║
║  ────────────────────────────────────────────────────────────────────  ║
║  A deterministic gate engine applied to EVERY forged gamefile/item. A    ║
║  gamefile is only folded into the Vault when it clears all gates:        ║
║                                                                        ║
║    • grade_escalation — grade strictly above the running stage floor     ║
║    • fidelity_floor   — visual fidelity above the (rising) Vault bar      ║
║    • behaviour_code   — ships executable behaviour                        ║
║    • placement_valid  — placed in a real Vault region                     ║
║    • gdd_parity       — its stage is represented in the escalating GDD    ║
║                                                                        ║
║  Returns a pass/fail verdict, a 0-1 quality score and per-gate detail.   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from typing import Any

# Quality-control bar: an item must score ≥ this (0-100) to enter production.
PRODUCTION_THRESHOLD = 95


def fidelity_floor(stage_index: int) -> float:
    """The visual-fidelity bar RISES as the snowball escalates."""
    return round(0.72 + stage_index * 0.02, 3)


def evaluate(item: dict, *, stage_index: int, stage_floor_grade: int,
             gdd_stages: set[str] | list[str], regions: list[str],
             era: str | None = None) -> dict:
    """Run all quality gates against one forged item. Pure & deterministic."""
    skin = item.get("skin") or {}
    placement = item.get("placement") or {}
    floor = fidelity_floor(stage_index)
    gdd_set = set(gdd_stages)

    gates = [
        {"name": "grade_escalation",
         "passed": int(item.get("grade", 0)) > int(stage_floor_grade),
         "detail": f"grade {item.get('grade')} > floor {stage_floor_grade}"},
        {"name": "fidelity_floor",
         "passed": float(skin.get("fidelity", 0)) >= floor,
         "detail": f"fidelity {skin.get('fidelity')} ≥ {floor}"},
        {"name": "behaviour_code",
         "passed": "export const" in (item.get("code") or ""),
         "detail": "ships executable behaviour"},
        {"name": "placement_valid",
         "passed": bool(placement.get("region")) and placement.get("region") in regions,
         "detail": f"region {placement.get('region')!r} in Vault world"},
        {"name": "gdd_parity",
         "passed": item.get("stage") in gdd_set,
         "detail": f"stage {item.get('stage')!r} present in GDD"},
    ]
    # ── era compliance: item must fit the chosen era's technical envelope ──
    era_key = era or skin.get("era")
    if era_key:
        from core import eras as _eras
        comp = _eras.era_compliance(item, era_key)
        gates.append({
            "name": "era_compliance",
            "passed": comp["passed"],
            "detail": f"fits {comp['era']} envelope" if comp["passed"]
            else "violates: " + ", ".join(comp["failed"]),
        })
    passed_n = sum(1 for g in gates if g["passed"])
    score = round(passed_n / len(gates), 3)
    failed = [g["name"] for g in gates if not g["passed"]]
    # ── PRODUCTION SCORE (0-100) — quality control bar for production ──
    gate_ratio = passed_n / len(gates)
    fidelity = float(skin.get("fidelity", 0))
    grade_norm = int(item.get("grade", 0)) / 5.0
    production_score = round(100 * (0.7 * gate_ratio + 0.15 * fidelity + 0.15 * grade_norm))
    return {
        "passed": passed_n == len(gates),
        "score": score,
        "production_score": production_score,
        "production_ready": passed_n == len(gates) and production_score >= PRODUCTION_THRESHOLD,
        "gates": gates,
        "failed_gates": failed,
        "fidelity_floor": floor,
        "verdict": "folded into gamefiles" if passed_n == len(gates)
        else "rejected: " + ", ".join(failed),
    }


def summarize(verdicts: list[dict]) -> dict:
    """Aggregate quality across a batch of forged items."""
    if not verdicts:
        return {"count": 0, "accepted": 0, "rejected": 0, "avg_score": 0.0,
                "avg_production_score": 0.0, "production_ready": 0,
                "gate_pass_rate": {}, "all_passed": True, "all_production_ready": True}
    total = len(verdicts)
    accepted = sum(1 for v in verdicts if v["passed"])
    prod_ready = sum(1 for v in verdicts if v.get("production_ready"))
    gate_names: list[str] = [g["name"] for g in verdicts[0]["gates"]]
    rates: dict[str, float] = {}
    for name in gate_names:
        ok = sum(1 for v in verdicts for g in v["gates"] if g["name"] == name and g["passed"])
        rates[name] = round(ok / total, 3)
    return {
        "count": total,
        "accepted": accepted,
        "rejected": total - accepted,
        "avg_score": round(sum(v["score"] for v in verdicts) / total, 3),
        "avg_production_score": round(sum(v.get("production_score", 0) for v in verdicts) / total, 1),
        "production_ready": prod_ready,
        "gate_pass_rate": rates,
        "all_passed": accepted == total,
        "all_production_ready": prod_ready == total,
    }
