"""
╔════════════════════════════════════════════════════════════════════════╗
║  PHASE GATES — the 100-phase advanced-mode checkpoint ladder.           ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Advanced builds run 100 phases. They are grouped into 8 checkpoint      ║
║  BANDS, each guarded by a gate derived from the snowball result. A band  ║
║  (and every phase in it) only goes green when its gate clears — so the   ║
║  100-phase build can never drift from the locked choices.                ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from typing import Any

ADVANCED_PHASES = 100

# Share of the era's total file output produced by each checkpoint band. The
# 100-phase build allocates the era's industry-standard file count across the
# bands (asset/world/tileset bands carry the bulk; QA the least). Sums to 1.0.
_BAND_FILE_WEIGHT: dict[str, float] = {
    "Foundation": 0.02,
    "World": 0.18,
    "Narrative": 0.12,
    "Mechanics": 0.10,
    "Procedural": 0.15,
    "Tileset": 0.18,
    "Assets": 0.22,
    "QA / Polish": 0.03,
}

# (band, start_phase, end_phase, gate_key, description)
_BANDS: list[tuple[str, int, int, str, str]] = [
    ("Foundation", 1, 10, "choices_locked", "Era + genre + seed locked into the ledger"),
    ("World", 11, 25, "world_quality", "World stage cleared quality + parity"),
    ("Narrative", 26, 40, "gdd_parity", "GDD↔gamefile parity locked every step"),
    ("Mechanics", 41, 55, "grade_escalation", "Grade floor escalates stage over stage"),
    ("Procedural", 56, 70, "determinism", "Deterministic plan hash present"),
    ("Tileset", 71, 85, "storage_tracked", "Storage tracked against the era cap"),
    ("Assets", 86, 95, "capacity", "Assets within the era's outshine capacity"),
    ("QA / Polish", 96, 100, "all_green", "All upstream bands green"),
]


def _gate_status(key: str, m: dict, upstream_ok: bool) -> tuple[bool, str]:
    aw = m.get("awareness") or {}
    ladder = m.get("ladder") or []
    if key == "choices_locked":
        ok = bool(aw.get("era")) and int(aw.get("choices_logged", 0)) >= 1
        return ok, f"era={aw.get('era')} · {aw.get('choices_logged', 0)} choices logged"
    if key == "world_quality":
        world = next((r for r in ladder if r["stage"] == "world"), None)
        ok = bool(world) and world["parity_ok"] and world["quality"]["all_passed"]
        return ok, "world stage QA + parity" if ok else "world stage incomplete"
    if key == "gdd_parity":
        return bool(m.get("parity_locked")), f"parity {m.get('parity_pct')}%"
    if key == "grade_escalation":
        floors = [r["grade_floor"] for r in ladder]
        ok = all(floors[i] <= floors[i + 1] for i in range(len(floors) - 1))
        return ok, "grade floors monotonic"
    if key == "determinism":
        return bool(m.get("plan_hash")), f"plan {str(m.get('plan_hash'))[:8]}"
    if key == "storage_tracked":
        st = m.get("storage") or {}
        return ("used_pct" in st), f"{st.get('used_label')} / {st.get('cap_label')}"
    if key == "capacity":
        cap = m.get("capacity") or {}
        forged = int(m.get("forged_assets", 0))
        within = int(cap.get("assets_forged", 0)) <= int(cap.get("asset_capacity", 0))
        ok = within and forged > 0
        return ok, (f"{forged} forged assets grounded · {cap.get('utilization_pct')}% of cap"
                    if forged > 0 else "no forged assets to build from yet")
    if key == "all_green":
        cg = m.get("choice_gates") or {}
        choices_ok = cg.get("all_reflected", True)
        ok = upstream_ok and choices_ok
        return ok, ("all bands green + every choice reflected" if ok
                    else "upstream gate or a choice gate failing")
    return False, "unknown gate"


def build(manifest: dict, assets: dict | None = None) -> dict:
    """Compute the 100-phase advanced-mode gate ladder from a snowball manifest.

    ``assets`` (optional) carries the build's COMBINED forged-asset inventory
    ({forged: N, families: [...]}). The 100 phases factor these in BEFORE the
    build — the Assets band only goes green when real forged assets exist, so
    the world is built from the assets, not the other way around."""
    forged = int((assets or {}).get("forged", 0))
    families = (assets or {}).get("families", []) or []
    m = {**manifest, "forged_assets": forged}
    # Era-scaled file output: the 100-phase build produces files up to the
    # chosen era's INDUSTRY-STANDARD count, allocated across the 8 bands.
    from core import eras as _eras
    era_spec = _eras.get_era(manifest.get("era"))
    file_target = int(era_spec["file_count_standard"])
    bands_out: list[dict] = []
    phases: list[dict] = []
    file_bands: list[dict] = []
    upstream_ok = True
    cum_files = 0
    for name, start, end, key, desc in _BANDS:
        # 'all_green' needs the running upstream verdict; others stand alone.
        ok, detail = _gate_status(key, m, upstream_ok)
        if key != "all_green":
            upstream_ok = upstream_ok and ok
        band_files = round(file_target * _BAND_FILE_WEIGHT.get(name, 0.0))
        cum_files += band_files
        bands_out.append({
            "band": name, "gate": key, "description": desc,
            "phase_range": [start, end], "phase_count": end - start + 1,
            "passed": ok, "detail": detail,
            "file_target": band_files,
            "files_produced": band_files if ok else 0,
        })
        file_bands.append({"band": name, "file_target": band_files,
                           "cumulative": cum_files, "passed": ok})
        for p in range(start, end + 1):
            phases.append({"phase": f"p{p:03d}", "band": name, "gate": key,
                           "passed": ok})
    passed = sum(1 for p in phases if p["passed"])
    files_produced = sum(b["files_produced"] for b in bands_out)
    return {
        "mode": "advanced",
        "advanced_phases": ADVANCED_PHASES,
        "bands": bands_out,
        "bands_passed": sum(1 for b in bands_out if b["passed"]),
        "bands_total": len(bands_out),
        "phases_passed": passed,
        "phases_total": len(phases),
        "pass_pct": round(100 * passed / max(1, len(phases))),
        "all_gates_green": all(b["passed"] for b in bands_out),
        "asset_grounded": forged > 0,
        "forged_assets": forged,
        "forged_families": sorted(f for f in families if f),
        "file_plan": {
            "era": era_spec["key"], "era_label": era_spec["label"],
            "file_target": file_target,
            "files_produced": files_produced,
            "produced_pct": round(100 * files_produced / max(1, file_target)),
            "bands": file_bands,
            "basis": "industry-standard shipped file count per era",
        },
        "phases": phases,
    }
