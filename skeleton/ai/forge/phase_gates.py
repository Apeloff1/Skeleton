"""Blueprint phase-gate ladder — 100-phase / 8-band checkpoint gates.

Port of Prood ``backend/core/phase_gates.py``. Advanced blueprints run 100
phases grouped into 8 checkpoint BANDS; each band is guarded by a gate
derived from the forge manifest. A band (and every phase in it) only goes
green when its gate clears — so the ladder cannot drift from locked
choices.

Sits upstream of materialise / LAFS. Self-contained: does **not** import
Prood ``core.eras`` — callers inject ``file_target`` (default 1000) or
pass ``era_file_target``. Off cortex / #25 / Gate hmac / treasury / outbox
/ WORM / chaos rewrites.
"""
from __future__ import annotations

from typing import Any

ADVANCED_PHASES = 100

# Default industry-standard file count when no era target is injected.
DEFAULT_FILE_TARGET = 1000

# Share of the era's total file output produced by each checkpoint band.
# Sums to 1.0.
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


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _gate_status(key: str, m: dict, upstream_ok: bool) -> tuple[bool, str]:
    aw = m.get("awareness") if isinstance(m.get("awareness"), dict) else {}
    ladder = m.get("ladder") if isinstance(m.get("ladder"), list) else []
    if key == "choices_locked":
        logged = _count(aw.get("choices_logged"))
        ok = _text(aw.get("era")) and logged is not None and logged >= 1
        return ok, f"era={aw.get('era')} · {aw.get('choices_logged', 0)} choices logged"
    if key == "world_quality":
        world = next((row for row in ladder if isinstance(row, dict) and row.get("stage") == "world"), None)
        quality = world.get("quality") if isinstance(world, dict) else None
        ok = (
            isinstance(world, dict)
            and world.get("parity_ok") is True
            and isinstance(quality, dict)
            and quality.get("all_passed") is True
        )
        return ok, "world stage QA + parity" if ok else "world stage incomplete"
    if key == "gdd_parity":
        return m.get("parity_locked") is True, f"parity {m.get('parity_pct')}%"
    if key == "grade_escalation":
        floors = []
        for row in ladder:
            if not isinstance(row, dict):
                return False, "grade floors missing"
            floor = row.get("grade_floor")
            if isinstance(floor, bool) or not isinstance(floor, (int, float)):
                return False, "grade floor is not a number"
            floors.append(float(floor))
        if len(floors) < 2:
            return False, "grade floors missing"
        ok = all(floors[i] <= floors[i + 1] for i in range(len(floors) - 1))
        return ok, "grade floors monotonic" if ok else "grade floors are not monotonic"
    if key == "determinism":
        return _text(m.get("plan_hash")), f"plan {str(m.get('plan_hash') or '')[:8]}"
    if key == "storage_tracked":
        st = m.get("storage") if isinstance(m.get("storage"), dict) else {}
        used = st.get("used_pct")
        ok = isinstance(used, (int, float)) and not isinstance(used, bool) and 0 <= float(used) <= 100
        return ok, f"{st.get('used_label')} / {st.get('cap_label')}"
    if key == "capacity":
        cap = m.get("capacity") if isinstance(m.get("capacity"), dict) else {}
        forged = _count(m.get("forged_assets"))
        made = _count(cap.get("assets_forged"))
        room = _count(cap.get("asset_capacity"))
        ok = forged is not None and forged > 0 and made is not None and room is not None and made <= room
        return ok, (f"{forged} forged assets grounded · {cap.get('utilization_pct')}% of cap"
                    if forged else "no forged assets to build from yet")
    if key == "all_green":
        cg = m.get("choice_gates") if isinstance(m.get("choice_gates"), dict) else {}
        ok = upstream_ok and cg.get("all_reflected") is True
        return ok, ("all bands green + every choice reflected" if ok
                    else "upstream gate or a choice gate failing")
    return False, "unknown gate"


def _resolve_file_target(
    *,
    file_target: int | None,
    era_file_target: int | None,
) -> int:
    chosen = file_target if file_target is not None else era_file_target
    if chosen is None:
        return DEFAULT_FILE_TARGET
    if isinstance(chosen, bool) or not isinstance(chosen, int) or chosen < 1:
        raise ValueError("file_target must be a positive integer")
    return chosen


def _era_fields(manifest: dict) -> tuple[str, str]:
    """Fill file_plan era fields from manifest when present, else placeholders."""
    aw = manifest.get("awareness") or {}
    era = manifest.get("era") or aw.get("era") or "unspecified"
    label = manifest.get("era_label") or aw.get("era_label") or era
    return str(era), str(label)


def build(
    manifest: dict,
    assets: dict | None = None,
    *,
    file_target: int | None = None,
    era_file_target: int | None = None,
) -> dict[str, Any]:
    """Compute the 100-phase advanced-mode gate ladder from a forge manifest.

    ``assets`` (optional) carries the build's COMBINED forged-asset inventory
    (``{forged: N, families: [...]}``). The Assets band only goes green when
    real forged assets exist.

    ``file_target`` / ``era_file_target`` inject the era's industry-standard
    file count (no Prood ``core.eras`` dependency). Default: 1000.
    """
    forged_raw = (assets or {}).get("forged", 0)
    if isinstance(forged_raw, bool) or not isinstance(forged_raw, int) or forged_raw < 0:
        raise ValueError("forged asset count must be a non-negative integer")
    forged = forged_raw
    families = (assets or {}).get("families", []) or []
    m = {**manifest, "forged_assets": forged}
    target = _resolve_file_target(
        file_target=file_target, era_file_target=era_file_target
    )
    era_key, era_label = _era_fields(manifest)
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
        band_files = round(target * _BAND_FILE_WEIGHT.get(name, 0.0))
        cum_files += band_files
        bands_out.append({
            "band": name, "gate": key, "description": desc,
            "phase_range": [start, end], "phase_count": end - start + 1,
            "passed": ok, "detail": detail,
            "file_target": band_files,
            "files_produced": 0,
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
            "era": era_key,
            "era_label": era_label,
            "file_target": target,
            "files_produced": files_produced,
            "produced_pct": round(100 * files_produced / max(1, target)),
            "bands": file_bands,
            "basis": "industry-standard shipped file count per era",
        },
        "phases": phases,
    }
