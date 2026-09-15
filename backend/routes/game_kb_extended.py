"""
⚒️ EXTENDED SNOWBALL FORGES — the eight deferred stages from
memory/NEXT_FORK_TOP_PRIORITY.md §2.5, registered into game_kb's forge maps at boot.

Design: this module NEVER edits game_kb.py (that file exceeds the safe API
round-trip size). Instead it imports game_kb's ``_FORGES`` / ``_APPROVABLE`` /
``_DOWNSTREAM`` / ``_STAGE_ART`` dicts and REGISTERS new stages into them, reusing
the shared ``_llm_json`` helper — so every extended forge automatically gets the
quality directive, the ≥95 gate, the retry loop AND the polish-pass fallback.

Imported at boot via routes/quality_control.py (already registered in the
declarative registry). Import failures are swallowed so a problem here can
never break boot.
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


# ── 1. QUALITY FORGE — holistic QA/polish pass (juice, game-feel, a11y, bugs) ─
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
    ctx = await _kb_context(pid, ("core_specs", "mechanics_config", "balance_params"))
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


# ── 5. REALISM FORGE — physical/visual realism rules ─────────────────────────
_REALISM_SYS = (
    "You are a realism & plausibility director (lighting, materials, physical believability). "
    "Output ONLY valid minified JSON (no prose, no markdown) for a realism_config with these "
    "required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive): "
    "lighting (object {model, time_of_day, gi_approach, shadow_rules}), materials (array of "
    "{name, pbr {albedo, roughness, metallic}, notes}), plausibility (array of {rule, domain, "
    "enforcement}), scale_reference (object {units, reference_objects}), constraints (array of "
    "{system, realism_tradeoff, chosen}). Consistent with the provided physics + spec."
)


async def _forge_realism(pid: str, instruction: str = "") -> dict:
    g = await _game_brief(pid)
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "realism_config"}
    ctx = await _kb_context(pid, ("core_specs", "physics_system", "mechanics_config"))
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"upstream KB: {ctx}\n\nProduce realism_config.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _REALISM_SYS,
                                   "lighting", pid=pid, stage="physics")
    if not data:
        return {"ok": False, "error": "realism config generation failed", "artifact": "realism_config"}
    await _store(pid, "realism_config", data)
    return {"ok": True, "artifact": "realism_config",
            "summary": f"{len(data.get('materials', []))} materials · "
                       f"{len(data.get('plausibility', []))} plausibility rules",
            "keys": list(data.keys()), "model": routed.get("model")}


# ── 6. FINE MECHANIC FORGE — micro-mechanics & interaction details ───────────
_FINEMECH_SYS = (
    "You are a micro-mechanics designer (input buffering, coyote time, interaction feel). "
    "Output ONLY valid minified JSON (no prose, no markdown) for a fine_mechanics config with "
    "these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive): "
    "input_buffering (object {enabled, window_ms, applies_to}), coyote_time (object {enabled, "
    "window_ms, notes}), interactions (array of {action, timing_windows, forgiveness, feedback}), "
    "assists (array of {assist, default, player_toggle}), edge_cases (array of {case, handling}). "
    "Ground every value in the provided mechanics + physics."
)


async def _forge_fine_mechanics(pid: str, instruction: str = "") -> dict:
    g = await _game_brief(pid)
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "fine_mechanics"}
    ctx = await _kb_context(pid, ("core_specs", "mechanics_config", "physics_system"))
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"upstream KB: {ctx}\n\nProduce fine_mechanics.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _FINEMECH_SYS,
                                   "interactions", pid=pid, stage="mechanics")
    if not data:
        return {"ok": False, "error": "fine mechanics generation failed", "artifact": "fine_mechanics"}
    await _store(pid, "fine_mechanics", data)
    return {"ok": True, "artifact": "fine_mechanics",
            "summary": f"{len(data.get('interactions', []))} interactions · "
                       f"{len(data.get('assists', []))} assists",
            "keys": list(data.keys()), "model": routed.get("model")}


# ── 7. MOVEMENT FORGE — locomotion/traversal ─────────────────────────────────
_MOVEMENT_SYS = (
    "You are a locomotion & traversal designer (accel, jump arcs, dash, climb, swim). Output "
    "ONLY valid minified JSON (no prose, no markdown) for a movement_config with these required "
    "keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive): locomotion "
    "(object {accel, decel, max_speed, turn_rate, air_control}), jump (object {arc, apex_hang_ms, "
    "coyote_ms, buffer_ms, variable_height}), traversal (array of {mode one of "
    "[dash,climb,swim,slide,grapple,glide], params, unlock}), animation_hooks (array of {state, "
    "blend_ms, notes}), feel_targets (object {responsiveness, weight, readability}). Ground every "
    "value in the provided mechanics + physics + fine_mechanics."
)


async def _forge_movement(pid: str, instruction: str = "") -> dict:
    g = await _game_brief(pid)
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "movement_config"}
    ctx = await _kb_context(pid, ("core_specs", "mechanics_config", "physics_system",
                                  "fine_mechanics"))
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"upstream KB: {ctx}\n\nProduce movement_config.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _MOVEMENT_SYS,
                                   "locomotion", pid=pid, stage="mechanics")
    if not data:
        return {"ok": False, "error": "movement config generation failed", "artifact": "movement_config"}
    await _store(pid, "movement_config", data)
    modes = len(data.get("traversal", []))
    return {"ok": True, "artifact": "movement_config",
            "summary": f"locomotion tuned · {modes} traversal modes",
            "keys": list(data.keys()), "model": routed.get("model")}


# ── 8. CITY FORGE — urban/level layout generation ────────────────────────────
_CITY_SYS = (
    "You are an urban & level-layout designer. Output ONLY valid minified JSON (no prose, no "
    "markdown) for a city_layout with these required keys, PLUS one extra top-level 'options' "
    "array (see the EXHAUSTIVE directive): districts (array of {name, theme, density, landmarks}), "
    "roads (array of {name, type, connects}), pois (array of {name, district, purpose, "
    "quest_hooks}), density_rules (object {residential, commercial, industrial, green}), "
    "generation_rules (array of {rule, method, seed_strategy}). Consistent with the provided "
    "lore + nature_config + procedural_config."
)


async def _forge_city(pid: str, instruction: str = "") -> dict:
    g = await _game_brief(pid)
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "city_layout"}
    ctx = await _kb_context(pid, ("core_specs", "lore_graph", "nature_config",
                                  "procedural_config"))
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"upstream KB: {ctx}\n\nProduce city_layout.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _CITY_SYS,
                                   "districts", pid=pid, stage="world")
    if not data:
        return {"ok": False, "error": "city layout generation failed", "artifact": "city_layout"}
    await _store(pid, "city_layout", data)
    return {"ok": True, "artifact": "city_layout",
            "summary": f"{len(data.get('districts', []))} districts · "
                       f"{len(data.get('pois', []))} POIs",
            "keys": list(data.keys()), "model": routed.get("model")}


# ── Registration into game_kb's forge maps (boot-time) ───────────────────────
_NEW_FORGES = {
    "quality": _forge_quality,
    "tuning": _forge_tuning,
    "critters": _forge_critters,
    "nature": _forge_nature,
    "realism": _forge_realism,
    "fine_mechanics": _forge_fine_mechanics,
    "movement": _forge_movement,
    "city": _forge_city,
}
_FORGES.update(_NEW_FORGES)
_APPROVABLE.update(_NEW_FORGES.keys())

_STAGE_ART.update({
    "quality": "quality_pass", "tuning": "tuning_config", "critters": "bestiary",
    "nature": "nature_config", "realism": "realism_config",
    "fine_mechanics": "fine_mechanics", "movement": "movement_config",
    "city": "city_layout",
})

# dependency edges: when these artifacts regenerate, downstream work goes stale
_DOWNSTREAM.update({
    "quality_pass": ["qa_report"],
    "tuning_config": ["physics_system", "procedural_config", "qa_report"],
    "bestiary": ["quest_db", "procedural_config", "qa_report"],
    "nature_config": ["procedural_config", "city_layout"],
    "realism_config": ["camera_director", "asset_manifest"],
    "fine_mechanics": ["movement_config", "qa_report"],
    "movement_config": ["qa_report", "physics_system"],
    "city_layout": ["quest_db", "procedural_config", "build_manifest"],
})

EXTENDED_STAGES = sorted(_NEW_FORGES.keys())
