"""
⚒️ EXTENDED SNOWBALL FORGES (part A) — four of the eight deferred stages from
memory/NEXT_FORK_TOP_PRIORITY.md §2.5. Registers into game_kb's forge maps at
boot so the stages are forgeable/refinable/approvable through the existing
/api/pipeline endpoints, reusing game_kb._llm_json — which already carries the
≥95 gate, retry loop and (via game_kb_polish) the targeted polish fallback.

Imported at boot via routes/quality_control.py. Never edits game_kb.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from routes.playable import _db
from routes.game_kb import (
    _llm_json, _with_instruction, _FORGES, _APPROVABLE, _DOWNSTREAM, _STAGE_ART,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _kb_context(pid: str, keys: tuple[str, ...], limit: int = 1800) -> str:
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, **{f"artifacts.{k}": 1 for k in keys}})
    arts = (kb or {}).get("artifacts") or {}
    return json.dumps({k: arts.get(k) for k in keys if arts.get(k)})[:limit]


async def _game_brief(pid: str) -> dict | None:
    return await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1})


async def _store(pid: str, artifact: str, data: dict) -> None:
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {f"artifacts.{artifact}": data, "updated_at": _now(), "game_id": pid}},
        upsert=True)


# ── 1. QUALITY FORGE — holistic QA/polish (juice, game-feel, a11y, bug list) ──
_QUALITY_SYS = (
    "You are a holistic game-quality director (juice, game feel, accessibility, polish). "
    "Output ONLY valid minified JSON (no prose, no markdown) for a quality_pass with these "
    "required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive): "
    "juice (array of {element, effect, implementation} — screen shake, hit-stop, particles, "
    "tweening), game_feel (object {responsiveness, feedback_loops, weight, notes}), "
    "accessibility (array of {feature, standard, implementation}), bug_risks (array of "
    "{risk, severity, repro_hint, fix}), polish_checklist (array of {item, priority, effort}). "
    "Ground everything in the provided spec, mechanics and existing QA report."
)


async def _forge_quality(pid: str, instruction: str = "") -> dict:
    g = await _game_brief(pid)
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "quality_pass"}
    ctx = await _kb_context(pid, ("core_specs", "mechanics_config", "qa_report"))
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"upstream KB: {ctx}\n\nProduce quality_pass.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _QUALITY_SYS,
                                   "juice", pid=pid, stage="qa")
    if not data:
        return {"ok": False, "error": "quality pass generation failed", "artifact": "quality_pass"}
    await _store(pid, "quality_pass", data)
    return {"ok": True, "artifact": "quality_pass",
            "summary": f"{len(data.get('juice', []))} juice elements · "
                       f"{len(data.get('polish_checklist', []))} checklist items",
            "keys": list(data.keys()), "model": routed.get("model")}


# ── 2. FINE TUNING FORGE — numeric balance (curves, drop rates, difficulty) ──
_TUNING_SYS = (
    "You are a balance & economy tuning designer. Output ONLY valid minified JSON (no prose, "
    "no markdown) for a tuning_config with these required keys, PLUS one extra top-level "
    "'options' array (see the EXHAUSTIVE directive): curves (array of {name, formula, points, "
    "rationale}), drop_rates (array of {item, base_rate, pity_timer, notes}), difficulty_knobs "
    "(array of {knob, min, max, default, step, player_facing}), economy (object {sources, sinks, "
    "inflation_guard}), target_metrics (object {session_length_min, retention_levers, skill_floor}). "
    "Every number must be justified against the provided mechanics + spec."
)


async def _forge_tuning(pid: str, instruction: str = "") -> dict:
    g = await _game_brief(pid)
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "tuning_config"}
    ctx = await _kb_context(pid, ("core_specs", "mechanics_config"))
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"upstream KB: {ctx}\n\nProduce tuning_config.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _TUNING_SYS,
                                   "curves", pid=pid, stage="mechanics")
    if not data:
        return {"ok": False, "error": "tuning generation failed", "artifact": "tuning_config"}
    await _store(pid, "tuning_config", data)
    return {"ok": True, "artifact": "tuning_config",
            "summary": f"{len(data.get('curves', []))} curves · "
                       f"{len(data.get('difficulty_knobs', []))} knobs",
            "keys": list(data.keys()), "model": routed.get("model")}


# ── 3. CRITTER & BESTIARY FORGE — enemies/creatures ──────────────────────────
_CRITTER_SYS = (
    "You are a creature & encounter designer. Output ONLY valid minified JSON (no prose, no "
    "markdown) for a bestiary with these required keys, PLUS one extra top-level 'options' "
    "array (see the EXHAUSTIVE directive): creatures (array of {name, role, stats {hp, speed, "
    "damage, defense}, abilities, behavior, lore}), spawn_tables (array of {zone, entries: array "
    "of {creature, weight, min_level, max_level}}), bosses (array of {name, phases, mechanics, "
    "rewards}), ecology (object {food_chains, territoriality, notes}). Consistent with the "
    "provided lore, mechanics and tuning."
)


async def _forge_critters(pid: str, instruction: str = "") -> dict:
    g = await _game_brief(pid)
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "bestiary"}
    ctx = await _kb_context(pid, ("core_specs", "lore_graph", "mechanics_config", "tuning_config"))
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"upstream KB: {ctx}\n\nProduce bestiary.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _CRITTER_SYS,
                                   "creatures", pid=pid, stage="world")
    if not data:
        return {"ok": False, "error": "bestiary generation failed", "artifact": "bestiary"}
    await _store(pid, "bestiary", data)
    return {"ok": True, "artifact": "bestiary",
            "summary": f"{len(data.get('creatures', []))} creatures · "
                       f"{len(data.get('bosses', []))} bosses",
            "keys": list(data.keys()), "model": routed.get("model")}


# ── 4. NATURE FORGE — flora/biomes/weather/ecology ───────────────────────────
_NATURE_SYS = (
    "You are a biome & ecosystem designer. Output ONLY valid minified JSON (no prose, no "
    "markdown) for a nature_config with these required keys, PLUS one extra top-level 'options' "
    "array (see the EXHAUSTIVE directive): biomes (array of {name, climate, terrain, palette}), "
    "flora (array of {species, biome, rarity, use}), weather (array of {type, biome, effects, "
    "frequency}), ecology (object {cycles, interactions, resource_nodes}), transitions (array of "
    "{from_biome, to_biome, blend_rule}). Consistent with the provided lore + world."
)


async def _forge_nature(pid: str, instruction: str = "") -> dict:
    g = await _game_brief(pid)
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "nature_config"}
    ctx = await _kb_context(pid, ("core_specs", "lore_graph", "procedural_config"))
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"upstream KB: {ctx}\n\nProduce nature_config.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _NATURE_SYS,
                                   "biomes", pid=pid, stage="world")
    if not data:
        return {"ok": False, "error": "nature config generation failed", "artifact": "nature_config"}
    await _store(pid, "nature_config", data)
    return {"ok": True, "artifact": "nature_config",
            "summary": f"{len(data.get('biomes', []))} biomes · "
                       f"{len(data.get('flora', []))} flora species",
            "keys": list(data.keys()), "model": routed.get("model")}


# ── Registration (part A) ────────────────────────────────────────────────────
_A_FORGES = {
    "quality": _forge_quality,
    "tuning": _forge_tuning,
    "critters": _forge_critters,
    "nature": _forge_nature,
}
_FORGES.update(_A_FORGES)
_APPROVABLE.update(_A_FORGES.keys())
_STAGE_ART.update({
    "quality": "quality_pass", "tuning": "tuning_config",
    "critters": "bestiary", "nature": "nature_config",
})
_DOWNSTREAM.update({
    "quality_pass": ["qa_report"],
    "tuning_config": ["physics_system", "procedural_config", "qa_report"],
    "bestiary": ["quest_db", "procedural_config", "qa_report"],
    "nature_config": ["procedural_config"],
})

EXTENDED_STAGES_A = sorted(_A_FORGES.keys())
