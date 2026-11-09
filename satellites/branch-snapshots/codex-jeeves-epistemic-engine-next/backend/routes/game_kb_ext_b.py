"""
⚒️ EXTENDED SNOWBALL FORGES (part B) — the remaining four deferred stages from
memory/NEXT_FORK_TOP_PRIORITY.md §2.5. Same registration pattern as part A:
imports game_kb's forge maps and adds stages at boot; reuses game_kb._llm_json
(≥95 gate + retry + polish fallback). Imported at boot via quality_control.
"""
from __future__ import annotations

from routes.game_kb import _llm_json, _with_instruction, _FORGES, _APPROVABLE, _DOWNSTREAM, _STAGE_ART
from routes.game_kb_ext_a import _kb_context, _game_brief, _store


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
    return {"ok": True, "artifact": "movement_config",
            "summary": f"locomotion tuned · {len(data.get('traversal', []))} traversal modes",
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


# ── Registration (part B) ────────────────────────────────────────────────────
_B_FORGES = {
    "realism": _forge_realism,
    "fine_mechanics": _forge_fine_mechanics,
    "movement": _forge_movement,
    "city": _forge_city,
}
_FORGES.update(_B_FORGES)
_APPROVABLE.update(_B_FORGES.keys())
_STAGE_ART.update({
    "realism": "realism_config", "fine_mechanics": "fine_mechanics",
    "movement": "movement_config", "city": "city_layout",
})
_DOWNSTREAM.update({
    "realism_config": ["camera_director", "asset_manifest"],
    "fine_mechanics": ["movement_config", "qa_report"],
    "movement_config": ["qa_report", "physics_system"],
    "city_layout": ["quest_db", "procedural_config", "build_manifest"],
})

EXTENDED_STAGES_B = sorted(_B_FORGES.keys())
