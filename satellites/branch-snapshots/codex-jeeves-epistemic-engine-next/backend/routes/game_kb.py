"""
🗄️ CENTRAL GAME KNOWLEDGE BASE + STAGE FORGES (build-to-spec).

Implements the flowchart's central DB/orchestrator: each pipeline stage produces a
concrete ARTIFACT file that is stored in `game_kb` keyed by game_id, and downstream
stages read upstream artifacts for consistency. This module ships two LLM "forges"
that were missing as real artifacts:

  • Questionnaire/Spec  → core_specs.json   (logline, pillars, core loop, GDD outline)
  • Mechanics & Systems → mechanics_config.json (loops, progression curves, balance)

WorldForge (lore_graph) and Asset Genesis (asset manifest) already exist; the Studio
Pipeline tracker (routes/playable_pipeline.py) reads this KB to mark stages done.

Doctrine: LLM runs off the event loop via the shared `_llm_in_thread` helper inside
the async-job pattern (`_run_job` → playable_jobs, polled at /api/playable/job/{id}).
"""
from __future__ import annotations

import json
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from routes.playable import _db, _GAME_ENSEMBLE, _llm_in_thread, _run_job
from core.director_agent import director  # SOTA Item 14 — Director facade wiring
from core.stage_vault import vault_for_stage

router = APIRouter(prefix="/api/pipeline", tags=["Studio Pipeline"])

_EDITABLE = {"core_specs", "lore_graph", "quest_db", "mechanics_config",
             "procedural_config", "build_manifest", "launch_manifest"}

# Stages that participate in the Iterate-&-Refine approval loop (the flowchart's red arrows).
_APPROVABLE = {"questionnaire", "spec", "world", "narrative", "mechanics", "procedural",
               "tileset", "assets", "implementation", "qa", "build", "cinematics", "physics"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _with_instruction(prompt: str, instruction: str) -> str:
    """Fold a creator's natural-language refinement note into a forge prompt
    (the 'chat' half of Iterate & Refine)."""
    note = (instruction or "").strip()
    if not note:
        return prompt
    return (prompt + "\n\nCREATOR REFINEMENT (apply precisely, keep everything else "
            "consistent): " + note[:600])



# Artifact key each forge stage writes (for the "review existing files" augmentation).
_STAGE_ART = {
    "questionnaire": "questionnaire", "spec": "core_specs", "world": "lore_graph",
    "narrative": "quest_db", "mechanics": "mechanics_config", "physics": "physics_system",
    "procedural": "procedural_config", "tileset": "tileset", "assets": "asset_manifest",
    "qa": "qa_report", "build": "build_manifest", "cinematics": "camera_director",
    "launch": "launch_manifest",
}


async def _augment_for_forge(pid: str, stage: str) -> str:
    """Shared per-stage augmentation: SCAN the game's files, REVIEW everything built so
    far, and LOAD the knowledge vault — so every forge reviews files and augments the
    game on each step instead of starting blind."""
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1})
    code = _parse_game_code((g or {}).get("html") or "")
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    arts = (kb or {}).get("artifacts") or {}
    built = [k for k in arts.keys() if not k.startswith("_")]
    parts = ["=== EXISTING GAME FILES (review and BUILD ON these — augment, don't restart) ==="]
    parts.append(f"Gameplay code signals: perspective={code['perspective']}, "
                 f"entities={code['entities']}, states={code['states']}, "
                 f"canvas={code['has_canvas']}, three_js={code['uses_threejs']}")
    parts.append(f"Artifacts already built: {built or '(none yet — this is an early stage)'}")
    try:
        v = vault_for_stage(stage)
        doms = ", ".join(d["name"] for d in v.get("domains", [])) or "general"
        parts.append(f"KNOWLEDGE VAULT for this stage — domains: {doms}")
        if v.get("tips"):
            parts.append("Vault tips: " + " | ".join(v["tips"][:4]))
    except Exception:
        pass
    return "\n".join(parts)


_EXHAUSTIVE_DIRECTIVE = (
    "BE EXHAUSTIVE — match a 100-phase AAA production pipeline in breadth and depth. "
    "You MUST add ONE extra top-level key 'options': an array (5+ entries) where each entry is "
    "{area, choices:[{option, pros, cons, recommended (bool)}]} giving 2-4 ALTERNATIVES for every "
    "major design decision in this stage; mark the strongest choice recommended=true. "
    "Cover edge cases, variations, difficulty/accessibility options, and failure modes. "
    "This 'options' key is REQUIRED in addition to the schema keys. "
    "Prefer richer, fully-specified output over terse output. Never leave a section thin.")


async def _llm_json(prompt: str, system: str, required_key: str, attempts: int = 3,
                    pid: str | None = None, stage: str | None = None):
    """Run an LLM forge off the event loop, parse strict JSON, and ENFORCE the ≥95 quality gate:
    inject the quality directive (pre), audit the output (post), and regenerate with auditor
    feedback until it clears 95 (or return the best attempt, flagged). Returns (data|None, routed)."""
    from routes.quality import audit_quality, QUALITY_DIRECTIVE, MIN_QUALITY
    if pid and stage:
        try:
            prompt = (await _augment_for_forge(pid, stage)) + "\n\n" + prompt
        except Exception:
            pass
    sys = system + "\n\n" + QUALITY_DIRECTIVE + "\n\n" + _EXHAUSTIVE_DIRECTIVE
    cur = prompt
    best, best_routed, best_score = None, {}, -1
    _SIM_STAGES = {"physics", "tileset", "cinematics", "procedural"}
    for _ in range(max(1, attempts)):
        routed = await asyncio.to_thread(_llm_in_thread, cur, sys, _GAME_ENSEMBLE)
        data = _extract_json(routed.get("content", ""))
        if not (data and required_key in data):
            continue
        _sim = bool(stage and stage in _SIM_STAGES)
        q = await audit_quality(required_key, json.dumps(data), simulate=_sim, artifact=data)
        data["_quality"] = q
        if q["score"] >= MIN_QUALITY:
            if _sim and q.get("simulation") and pid:
                try:
                    from core.forge_validator import cache_trace
                    cache_trace(pid, stage, q["simulation"])  # Item 25
                except Exception:
                    pass
            return data, routed
        if q["score"] > best_score:
            best, best_routed, best_score = data, routed, q["score"]
        cur = (prompt + f"\n\nYOUR PREVIOUS OUTPUT SCORED {q['score']}/100 — BELOW the required 95. "
               f"Auditor feedback: {q.get('feedback', '')}. Regenerate so EVERY factor is >= 95.")
    return (best, best_routed) if best else (None, best_routed)


def _extract_json(text: str) -> dict | None:
    """Best-effort JSON extraction from an LLM response."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if "```" in s[3:] else s
        s = s.replace("json", "", 1).strip() if s[:4].lower() == "json" else s
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        return None
    try:
        obj = json.loads(s[a:b + 1])
    except Exception:
        return None
    # Unwrap a single-key envelope like {"launch_manifest": {...real artifact...}}
    # that some models emit; our artifacts always have multiple top-level keys.
    if isinstance(obj, dict) and len(obj) == 1:
        inner = next(iter(obj.values()))
        if isinstance(inner, dict) and len(inner) >= 2:
            return inner
    return obj


# ── artifact specs (system prompt + required keys per stage) ─────────────────
_SPEC_SYS = (
    "You are a senior game designer. Output ONLY valid minified JSON (no prose, no "
    "markdown) for a core game specification with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: "
    "title, logline, genre, pillars (array of 3 short strings), core_loop (array of "
    "4-6 short step strings), controls (object of input->action), win_condition, "
    "lose_condition, progression (one sentence), target_feel (one sentence), "
    "gdd_outline (array of 5-8 section title strings). Keep it concrete and buildable.")

_MECH_SYS = (
    "You are a systems designer. Output ONLY valid minified JSON (no prose, no markdown) "
    "for a mechanics_config with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: core_mechanics (array of {name, "
    "description}), progression_curves (array of {stat, curve, notes}), balance_params "
    "(object e.g. {player_speed, spawn_rate, difficulty_ramp, score_values}), systems "
    "(array of {name, rules}), loops (object {moment_to_moment, session, meta}). Ground "
    "it in the provided spec so it is directly implementable.")


async def _forge_spec(pid: str, instruction: str = "") -> dict:
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "core_specs"}
    prompt = (f"Game title: {g.get('title', '')}\nGenre: {g.get('genre', '')}\n"
              f"Brief: {g.get('brief', '')}\n\nProduce core_specs.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _SPEC_SYS, "core_loop", pid=pid, stage="spec")
    if not data:
        return {"ok": False, "error": "spec generation failed", "artifact": "core_specs"}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {f"artifacts.core_specs": data, "updated_at": _now(), "game_id": pid}},
        upsert=True)
    return {"ok": True, "artifact": "core_specs",
            "summary": data.get("logline", "")[:160],
            "keys": list(data.keys()), "model": routed.get("model")}


async def _forge_mechanics(pid: str, instruction: str = "") -> dict:
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "mechanics_config"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts.core_specs": 1})
    spec = ((kb or {}).get("artifacts") or {}).get("core_specs") or {}
    spec_ctx = json.dumps(spec)[:1500] if spec else "(no core_specs yet — infer from brief)"
    prompt = (f"Game: {g.get('title', '')} ({g.get('genre', '')})\nBrief: {g.get('brief', '')}\n"
              f"core_specs: {spec_ctx}\n\nProduce mechanics_config.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _MECH_SYS, "core_mechanics", pid=pid, stage="mechanics")
    if not data:
        return {"ok": False, "error": "mechanics generation failed", "artifact": "mechanics_config"}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {f"artifacts.mechanics_config": data, "updated_at": _now(), "game_id": pid}},
        upsert=True)
    return {"ok": True, "artifact": "mechanics_config",
            "summary": f"{len(data.get('core_mechanics', []))} mechanics, "
                       f"{len(data.get('systems', []))} systems",
            "keys": list(data.keys()), "model": routed.get("model")}


_LORE_SYS = (
    "You are a worldbuilding director. Output ONLY valid minified JSON (no prose) for a "
    "lore_graph with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: setting (one paragraph), regions (array of {name, "
    "biome, description}), factions (array of {name, goal, relationship}), bestiary (array "
    "of {name, threat, behavior}), history (array of 3-5 era strings), map_seeds (array of "
    "3-6 evocative location-name strings). Keep it consistent with the game's genre + spec.")

_QUEST_SYS = (
    "You are a narrative designer. Output ONLY valid minified JSON (no prose) for a quest_db "
    "with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: quests (array of {id, title, objective, reward}), "
    "dialogue_trees (array of {npc, lines: array of strings}), character_bibles (array of "
    "{name, role, personality, arc}), branching_arcs (array of {branch, outcome}). Ground it "
    "in the provided world + spec for consistency.")


async def _forge_world(pid: str, instruction: str = "") -> dict:
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "lore_graph"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts.core_specs": 1})
    spec = ((kb or {}).get("artifacts") or {}).get("core_specs") or {}
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"core_specs: {json.dumps(spec)[:1200] if spec else '(infer)'}\n\nProduce lore_graph.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _LORE_SYS, "regions", pid=pid, stage="world")
    if not data:
        return {"ok": False, "error": "lore generation failed", "artifact": "lore_graph"}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.lore_graph": data, "updated_at": _now(), "game_id": pid}}, upsert=True)
    return {"ok": True, "artifact": "lore_graph",
            "summary": f"{len(data.get('regions', []))} regions, {len(data.get('factions', []))} factions",
            "keys": list(data.keys()), "model": routed.get("model")}


async def _forge_narrative(pid: str, instruction: str = "") -> dict:
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "quest_db"}
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, "artifacts.core_specs": 1, "artifacts.lore_graph": 1})
    arts = (kb or {}).get("artifacts") or {}
    ctx = json.dumps({"spec": arts.get("core_specs"), "lore": arts.get("lore_graph")})[:1800]
    from routes.canon_rag import _recall, recall_block
    recalled = recall_block(await _recall(pid, f"{g.get('title','')} characters factions quests story", 5))
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"context: {ctx}\n{recalled}\n\nProduce quest_db.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _QUEST_SYS, "quests", pid=pid, stage="narrative")
    if not data:
        return {"ok": False, "error": "quest generation failed", "artifact": "quest_db"}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.quest_db": data, "updated_at": _now(), "game_id": pid}}, upsert=True)
    return {"ok": True, "artifact": "quest_db",
            "summary": f"{len(data.get('quests', []))} quests, {len(data.get('character_bibles', []))} characters",
            "keys": list(data.keys()), "model": routed.get("model")}


_QA_SYS = (
    "You are an AI playtester / QA lead. You are given a game's HTML and its design KB. Output "
    "ONLY valid minified JSON (no prose) for a qa_report with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: metrics (object "
    "{pacing, difficulty, clarity, replayability} each an integer 0-100), auto_tune (array of 3-6 "
    "concrete tuning suggestion strings), bugs (array of likely-issue strings, may be empty), "
    "verdict (one short sentence), score (integer 0-100 overall). Base it on the actual code + KB.")


async def _forge_qa(pid: str, instruction: str = "") -> dict:
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "html": 1})
    if not g or not g.get("html"):
        return {"ok": False, "error": "game not ready", "artifact": "qa_report"}
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, "artifacts.core_specs": 1, "artifacts.mechanics_config": 1})
    arts = (kb or {}).get("artifacts") or {}
    ctx = json.dumps({"spec": arts.get("core_specs"), "mechanics": arts.get("mechanics_config")})[:1500]
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nKB: {ctx}\n\n"
              f"GAME HTML (truncated):\n{g['html'][:9000]}\n\nProduce qa_report.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _QA_SYS, "metrics", pid=pid, stage="qa")
    if not data:
        return {"ok": False, "error": "qa generation failed", "artifact": "qa_report"}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.qa_report": data, "updated_at": _now(), "game_id": pid}}, upsert=True)
    return {"ok": True, "artifact": "qa_report",
            "summary": f"score {data.get('score', '?')} · {len(data.get('auto_tune', []))} tune tips, "
                       f"{len(data.get('bugs', []))} bugs",
            "keys": list(data.keys()), "model": routed.get("model")}


async def _forge_build(pid: str, instruction: str = "") -> dict:
    """Build & Export — DETERMINISTIC (no LLM): package the playable into a build_manifest
    and flag the game as exported."""
    import hashlib
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "version": 1, "bytes": 1, "html": 1})
    if not g or not g.get("html"):
        return {"ok": False, "error": "game not ready", "artifact": "build_manifest"}
    asset_kinds = await _db.asset_genesis.distinct("kind", {"game_id": pid})
    checksum = hashlib.sha256((g.get("html") or "").encode("utf-8")).hexdigest()[:16]
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    arts = list(((kb or {}).get("artifacts") or {}).keys())
    files = ["game.html"] + [f"{a}.json" for a in arts] + (["asset_manifest"] if asset_kinds else [])
    manifest = {
        "title": g.get("title", ""), "version": g.get("version", 1),
        "platform": "web/html5", "bytes": g.get("bytes") or len(g.get("html", "")),
        "checksum": checksum, "asset_kinds": asset_kinds, "files": files,
        "kb_artifacts": arts, "exported_at": _now(),
    }
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.build_manifest": manifest, "updated_at": _now(), "game_id": pid}}, upsert=True)
    await _db.playables.update_one(
        {"playable_id": pid}, {"$set": {"exported": True, "exported_at": _now()}})
    return {"ok": True, "artifact": "build_manifest",
            "summary": f"v{manifest['version']} · {len(files)} files · {checksum}",
            "keys": list(manifest.keys())}


# ── Stage 7: PROCEDURAL GENERATION (the flowchart's box #7) ──────────────────
_PROC_SYS = (
    "You are a technical director for procedural content generation (PCG). Output ONLY valid "
    "minified JSON (no prose, no markdown) for a procedural_config with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: "
    "requirements (array of {item, target, rationale} — concrete content the game must generate, "
    "e.g. enemy variety, level count, infinite terrain), generation_rules (array of {name, method, "
    "seed_strategy, consistency_constraint} — HOW content is produced deterministically & stays "
    "consistent with the world/mechanics), optimization (object {lod_strategy, budget: object with "
    "max_entities & draw_calls & memory_mb, culling}), content_management (object {modularity, "
    "streaming, dedup, scale_target}), pcg_systems (array of {system, inputs, outputs}). Ground it "
    "strictly in the provided spec + mechanics + lore so generation is consistent and buildable.")


async def _forge_procedural(pid: str, instruction: str = "") -> dict:
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "procedural_config"}
    kb = await _db.game_kb.find_one(
        {"game_id": pid},
        {"_id": 0, "artifacts.core_specs": 1, "artifacts.mechanics_config": 1, "artifacts.lore_graph": 1})
    arts = (kb or {}).get("artifacts") or {}
    ctx = json.dumps({"spec": arts.get("core_specs"), "mechanics": arts.get("mechanics_config"),
                      "lore": arts.get("lore_graph")})[:1800]
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"upstream KB: {ctx}\n\nProduce procedural_config.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _PROC_SYS, "requirements", pid=pid, stage="procedural")
    if not data:
        return {"ok": False, "error": "procedural generation failed", "artifact": "procedural_config"}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.procedural_config": data, "updated_at": _now(), "game_id": pid}}, upsert=True)
    return {"ok": True, "artifact": "procedural_config",
            "summary": f"{len(data.get('requirements', []))} requirements, "
                       f"{len(data.get('pcg_systems', []))} PCG systems",
            "keys": list(data.keys()), "model": routed.get("model")}


# ── Asset Genesis manifest as a first-class KB artifact (DETERMINISTIC) ──────
async def _forge_assets(pid: str, instruction: str = "") -> dict:
    """Compile the game's generated assets (asset_genesis) into a real asset_manifest
    artifact in the Central KB. No LLM — pure aggregation so assets are a KB feed."""
    REQUIRED = ["character", "enemy", "item", "background"]
    docs = await _db.asset_genesis.find(
        {"game_id": pid},
        {"_id": 0, "asset_id": 1, "kind": 1, "style": 1, "palette": 1, "applied": 1, "created_at": 1}
    ).to_list(length=500)
    kinds = sorted({d.get("kind") for d in docs if d.get("kind")})
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "asset_status": 1})
    missing = [k for k in REQUIRED if k not in kinds]
    manifest = {
        "required_kinds": REQUIRED,
        "generated_kinds": kinds,
        "missing_kinds": missing,
        "asset_count": len(docs),
        "applied": any(d.get("applied") for d in docs),
        "status": (g or {}).get("asset_status") or ("complete" if not missing and docs else
                                                     ("partial" if docs else "none")),
        "assets": [{"asset_id": d.get("asset_id"), "kind": d.get("kind"),
                    "style": d.get("style"), "palette": d.get("palette"),
                    "applied": bool(d.get("applied"))} for d in docs],
        "compiled_at": _now(),
    }
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.asset_manifest": manifest, "updated_at": _now(), "game_id": pid}}, upsert=True)
    return {"ok": True, "artifact": "asset_manifest",
            "summary": f"{len(docs)} assets · {len(kinds)}/4 kinds · {manifest['status']}",
            "keys": list(manifest.keys())}


# ── Stage 10b: LAUNCH PREP (store-readiness + listing copy) ──────────────────
_LAUNCH_SYS = (
    "You are an app-store launch manager. Output ONLY valid minified JSON (no prose, no markdown) "
    "for a launch_manifest with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: store_listing (object {app_name (<=30 chars), "
    "subtitle (<=30 chars), short_description (<=80 chars), full_description (2-3 short paragraphs), "
    "keywords (array of 5-8 strings), category, age_rating}), assets_checklist (array of {item, "
    "spec, required: boolean} covering icon 1024px, feature graphic, screenshots, privacy policy), "
    "compliance (array of short readiness strings). Base the copy on the provided spec — concrete, "
    "marketable, honest.")


async def _forge_launch(pid: str, instruction: str = "") -> dict:
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1, "version": 1, "exported": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "launch_manifest"}
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, "artifacts.core_specs": 1, "artifacts.build_manifest": 1})
    arts = (kb or {}).get("artifacts") or {}
    spec = arts.get("core_specs") or {}
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
              f"core_specs: {json.dumps(spec)[:1400] if spec else '(infer)'}\n\nProduce launch_manifest.json.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _LAUNCH_SYS, "store_listing", pid=pid, stage="launch")
    if not data:
        return {"ok": False, "error": "launch prep failed", "artifact": "launch_manifest"}
    # deterministic readiness signals appended to the LLM copy
    data["build_ready"] = bool(arts.get("build_manifest") or g.get("exported"))
    data["deploy_route"] = "/build-hub"
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.launch_manifest": data, "updated_at": _now(), "game_id": pid}}, upsert=True)
    return {"ok": True, "artifact": "launch_manifest",
            "summary": (data.get("store_listing") or {}).get("app_name", "") + " · store-ready"
                       + ("" if data["build_ready"] else " (build pending)"),
            "keys": list(data.keys()), "model": routed.get("model")}


_CINEMATICS_SYS = (
    "You are a cinematography & camera systems director for video games. Output ONLY valid "
    "minified JSON (no prose, no markdown) for a COMPLETE camera_director system with EXACTLY "
    "these keys: global (object {default_rig, fov, follow {lerp, offset_x, offset_y, offset_z}, "
    "bounds, shake_profile}), rigs (array of 4-8 {id, type one of "
    "[follow,orbit,dolly,crane,pan,handheld,fixed,fps,thirdperson,topdown,isometric], fov, easing, "
    "speed, notes}), scenes (array of {scene, description, shots (array of {shot_id, rig, movement, "
    "target, fov, duration_s, easing, trigger})}), cutscenes (array of {id, beats (array of {camera, "
    "action, duration_s})}), transitions (array of {from, to, type, duration_s}), engine_export "
    "(object {format, fps, coordinate_system, up_axis, notes}). Derive EVERY rig and shot from the "
    "provided game spec, mechanics, world, narrative AND the parsed gameplay code signals so the "
    "camera system is directly implementable in the build's engine config.")


def _parse_game_code(html: str) -> dict:
    """Lightweight static parse of the playable's gameplay code to ground the camera
    director in what actually exists (entities, states, perspective, canvas)."""
    import re
    if not html:
        return {"entities": [], "states": [], "perspective": "unknown", "has_canvas": False}
    h = html[:60000]
    low = h.lower()
    ent = sorted({m.lower() for m in re.findall(
        r'\b(player|enemy|enemies|boss|bullet|projectile|platform|coin|powerup|obstacle|'
        r'tile|level|wall|door|npc|car|ball|paddle|ship|asteroid|block|brick)\b', low)})
    states = sorted({m.lower() for m in re.findall(
        r'(?:state|scene|screen|mode)\s*[=:]\s*[\'"]?(\w+)', low)})[:12]
    if any(k in low for k in ['three.js', 'webgl', 'perspectivecamera', 'z:', '.z =']):
        persp = "3d"
    elif any(k in low for k in ['isometric', 'iso ']):
        persp = "isometric"
    elif any(k in low for k in ['topdown', 'top-down', 'birds-eye']):
        persp = "topdown"
    else:
        persp = "2d"
    return {"entities": ent[:14], "states": states, "perspective": persp,
            "has_canvas": "canvas" in low or "getcontext" in low,
            "uses_threejs": "three" in low and "scene" in low}


async def _forge_cinematics(pid: str, instruction: str = "") -> dict:
    """🎥 Parse the game's files + design artifacts and forge a COMPLETE cinematic
    camera director (rigs, per-scene shot lists, cutscenes, engine export config)."""
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1, "html": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "camera_director"}
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, "artifacts.core_specs": 1, "artifacts.mechanics_config": 1,
                           "artifacts.lore_graph": 1, "artifacts.quest_db": 1})
    arts = (kb or {}).get("artifacts") or {}
    spec = arts.get("core_specs") or {}
    mech = arts.get("mechanics_config") or {}
    world = arts.get("lore_graph") or {}
    quests = arts.get("quest_db") or {}
    code = _parse_game_code(g.get("html") or "")
    prompt = (
        f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
        f"core_specs: {json.dumps(spec)[:900] if spec else '(infer)'}\n"
        f"mechanics: {json.dumps(mech.get('core_mechanics', []))[:700] if mech else '(infer)'}\n"
        f"world_regions: {json.dumps([r.get('name') for r in (world.get('regions') or [])][:8])}\n"
        f"quests: {json.dumps([q.get('title') for q in (quests.get('quests') or [])][:8])}\n"
        f"PARSED GAMEPLAY CODE SIGNALS: perspective={code['perspective']}, "
        f"entities={code['entities']}, states={code['states']}, "
        f"three_js={code['uses_threejs']}, canvas={code['has_canvas']}\n\n"
        f"Produce camera_director.json — a complete, implementable cinematic camera system.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _CINEMATICS_SYS, "scenes", pid=pid, stage="cinematics")
    if not data:
        return {"ok": False, "error": "camera director generation failed", "artifact": "camera_director"}
    data["code_signals"] = code
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.camera_director": data, "updated_at": _now(), "game_id": pid}}, upsert=True)
    n_scenes = len(data.get("scenes") or [])
    n_shots = sum(len(s.get("shots") or []) for s in (data.get("scenes") or []))
    n_rigs = len(data.get("rigs") or [])
    return {"ok": True, "artifact": "camera_director",
            "summary": f"{n_rigs} rigs · {n_scenes} scenes · {n_shots} shots",
            "keys": list(data.keys()), "model": routed.get("model")}


_PHYSICS_SYS = (
    "You are a game physics engineer. Output ONLY valid minified JSON (no prose, no markdown) "
    "for a COMPLETE physics_system with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: world (object {gravity {x,y,z}, "
    "time_step, solver_iterations, units, broadphase}), materials (array of 3-6 {id, friction, "
    "restitution, density, notes}), body_types (array of {id, type one of [static,dynamic,kinematic], "
    "mass, material, notes}), bodies (array mapping each gameplay entity to {entity, body_type, "
    "material, collider one of [box,circle,capsule,polygon,mesh], notes}), collisions (array of "
    "{layer_a, layer_b, response one of [collide,trigger,ignore]}), forces (array of {id, type one of "
    "[gravity,impulse,drag,buoyancy,wind,explosion,thrust], params}), constraints (array of {id, type "
    "one of [hinge,spring,distance,fixed,slider], bodies, params}), tuning (object {feel, gravity_scale, "
    "max_velocity, bounce, friction_global}), engine_export (object {engine, format, fps, units, notes}). "
    "Derive EVERY body, collider and force from the provided game mechanics AND the parsed gameplay "
    "code signals so the physics is directly implementable in the build's engine.")


async def _forge_physics(pid: str, instruction: str = "") -> dict:
    """🧲 Parse the game's files + mechanics and forge a COMPLETE physics system
    (world, materials, bodies, colliders, forces, constraints, tuning, export)."""
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1, "html": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "physics_system"}
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, "artifacts.core_specs": 1, "artifacts.mechanics_config": 1})
    arts = (kb or {}).get("artifacts") or {}
    spec = arts.get("core_specs") or {}
    mech = arts.get("mechanics_config") or {}
    code = _parse_game_code(g.get("html") or "")
    prompt = (
        f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n"
        f"core_specs: {json.dumps(spec)[:800] if spec else '(infer)'}\n"
        f"mechanics: {json.dumps(mech.get('core_mechanics', []))[:700] if mech else '(infer)'}\n"
        f"balance: {json.dumps(mech.get('balance_params', {}))[:400] if mech else ''}\n"
        f"PARSED GAMEPLAY CODE SIGNALS: perspective={code['perspective']}, "
        f"entities={code['entities']}, three_js={code['uses_threejs']}\n\n"
        f"Produce physics_system.json — a complete, implementable physics setup.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _PHYSICS_SYS, "world", pid=pid, stage="physics")
    if not data:
        return {"ok": False, "error": "physics generation failed", "artifact": "physics_system"}
    data["code_signals"] = code
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.physics_system": data, "updated_at": _now(), "game_id": pid}}, upsert=True)
    n_bodies = len(data.get("bodies") or [])
    n_mats = len(data.get("materials") or [])
    n_forces = len(data.get("forces") or [])
    grav = (data.get("world") or {}).get("gravity") or {}
    return {"ok": True, "artifact": "physics_system",
            "summary": f"{n_bodies} bodies · {n_mats} materials · {n_forces} forces · g={grav.get('y', '—')}",
            "keys": list(data.keys()), "model": routed.get("model")}



_QUESTIONNAIRE_SYS = (
    "You are a lead game designer running a creative discovery questionnaire. Output ONLY valid "
    "minified JSON (no prose, no markdown) for a questionnaire artifact with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: "
    "questions (array of 6-10 {q, why}), answers (array of {q, answer} — answer each question "
    "yourself based on the game so far), target_audience, core_fantasy, must_haves (array), "
    "nice_to_haves (array), tone, references (array of short comparable-game strings), open_risks "
    "(array). Ground every answer in the existing game files and artifacts so it augments the game.")


async def _forge_questionnaire(pid: str, instruction: str = "") -> dict:
    """📝 The discovery questionnaire — the FIRST snowball step. Reviews the game files and
    captures intent (audience, core fantasy, must-haves) that seeds every later stage."""
    g = await _db.playables.find_one({"playable_id": pid},
                                     {"_id": 0, "title": 1, "genre": 1, "brief": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "questionnaire"}
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n\n"
              f"Produce questionnaire.json — discovery questions AND your grounded answers.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _QUESTIONNAIRE_SYS,
                                   "answers", pid=pid, stage="questionnaire")
    if not data:
        return {"ok": False, "error": "questionnaire generation failed", "artifact": "questionnaire"}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.questionnaire": data, "updated_at": _now(), "game_id": pid}}, upsert=True)
    return {"ok": True, "artifact": "questionnaire",
            "summary": f"{len(data.get('questions', []))} Qs · audience: {data.get('target_audience', '')[:40]}",
            "keys": list(data.keys()), "model": routed.get("model")}


_TILESET_SYS = (
    "You are a tile artist & level-tooling engineer. Output ONLY valid minified JSON (no prose, no "
    "markdown) for a tileset artifact with these required keys, PLUS one extra top-level 'options' array (see the EXHAUSTIVE directive),: name, tile_size (object {w,h}), "
    "palette (array of hex color strings), tiles (array of 8-20 {id, role one of "
    "[ground,wall,platform,hazard,decor,collectible,water,ladder,door,spawn], color, solid (bool), "
    "notes}), autotiling (array of {rule, applies_to, neighbors, result}), layers (array of {name, "
    "z, purpose}), atlas (object {columns, rows, prompt}). Derive every tile and rule from the "
    "game's mechanics, world and parsed code so the tileset is directly usable by the level builder.")


async def _forge_tileset(pid: str, instruction: str = "") -> dict:
    """🧱 Forge a complete tileset (tiles, palette, autotiling rules, layers, atlas spec) by
    parsing the game's files + world/mechanics so levels can be built on top of it."""
    g = await _db.playables.find_one({"playable_id": pid},
                                     {"_id": 0, "title": 1, "genre": 1, "brief": 1})
    if not g:
        return {"ok": False, "error": "game not found", "artifact": "tileset"}
    prompt = (f"Game: {g.get('title','')} ({g.get('genre','')})\nBrief: {g.get('brief','')}\n\n"
              f"Produce tileset.json — a complete, level-buildable tileset.")
    data, routed = await _llm_json(_with_instruction(prompt, instruction), _TILESET_SYS,
                                   "tiles", pid=pid, stage="tileset")
    if not data:
        return {"ok": False, "error": "tileset generation failed", "artifact": "tileset"}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"artifacts.tileset": data, "updated_at": _now(), "game_id": pid}}, upsert=True)
    ts = data.get("tile_size") or {}
    return {"ok": True, "artifact": "tileset",
            "summary": f"{len(data.get('tiles', []))} tiles · {len(data.get('palette', []))} colors · "
                       f"{ts.get('w','?')}x{ts.get('h','?')}",
            "keys": list(data.keys()), "model": routed.get("model")}


_FORGES = {"questionnaire": _forge_questionnaire, "tileset": _forge_tileset, "spec": _forge_spec, "mechanics": _forge_mechanics, "world": _forge_world,
           "narrative": _forge_narrative, "physics": _forge_physics, "procedural": _forge_procedural,
           "assets": _forge_assets, "qa": _forge_qa, "build": _forge_build,
           "cinematics": _forge_cinematics, "launch": _forge_launch}

# ── Dependency & Provenance Graph (schematic: invalidation tracking) ─────────
# which AGENT owns each stage (provenance: agent + timestamp + model)
_AGENT_BY_STAGE = {
    "spec": "QuestionnaireAgent", "world": "WorldForgeAgent", "narrative": "NarrativeQuestAgent",
    "mechanics": "MechanicsSystemsAgent", "procedural": "ProceduralAgent",
    "physics": "PhysicsEngineAgent",
    "assets": "AssetPipelineAgent", "qa": "QAAgent", "build": "BuildAgent",
    "cinematics": "CameraDirectorAgent", "launch": "OrchestratorAgent",
}
# when an artifact (re)generates, these DOWNSTREAM artifacts become stale and must regen
# ("change in WorldEntity → flag dependent Assets/Quests/Levels")
_DOWNSTREAM = {
    "core_specs":       ["lore_graph", "quest_db", "mechanics_config", "procedural_config",
                         "qa_report", "build_manifest", "launch_manifest"],
    "lore_graph":       ["quest_db", "procedural_config", "qa_report", "build_manifest"],
    "quest_db":         ["qa_report", "build_manifest"],
    "mechanics_config": ["physics_system", "procedural_config", "qa_report", "build_manifest"],
    "physics_system":   ["procedural_config", "qa_report", "build_manifest"],
    "procedural_config": ["asset_manifest", "qa_report", "build_manifest"],
    "asset_manifest":   ["build_manifest"],
    "qa_report":        [],
    "build_manifest":   ["camera_director", "launch_manifest"],
    "camera_director":  ["launch_manifest"],
    "launch_manifest":  [],
}


async def _stamped(pid: str, stage: str, coro):
    """Run a forge, then record PROVENANCE (agent+model+timestamp) and propagate
    INVALIDATION: mark every downstream artifact stale, and clear this one's stale flag.
    SOTA Item 14/19 — the Director observes every forge: it plans the stage, then
    records the result + reflects on quality (non-breaking; failures are swallowed)."""
    try:
        director.plan_stage(pid, stage)
    except Exception:
        pass
    res = await coro
    if isinstance(res, dict) and res.get("ok"):
        art = res.get("artifact")
        now = _now()
        sets = {f"provenance.{art}": {"agent": _AGENT_BY_STAGE.get(stage, "Agent"),
                                      "model": res.get("model"), "at": now}}
        for d in _DOWNSTREAM.get(art, []):
            sets[f"stale.{d}"] = now
        await _db.game_kb.update_one(
            {"game_id": pid}, {"$set": sets, "$unset": {f"stale.{art}": ""}})
        try:
            q = res.get("quality") or res.get("_quality")
            score = q.get("score") if isinstance(q, dict) else (int(q) if isinstance(q, (int, float)) else None)
            director.record_forge(pid, stage, art, score)
            if score is not None:
                director.reflect_on_quality(pid, {
                    "stage": stage, "score": score,
                    "feedback": q.get("feedback", "") if isinstance(q, dict) else ""})
        except Exception:
            pass
    return res
@router.post("/{pid}/forge/{stage}/async")
async def forge_stage(pid: str, stage: str):
    """⚒ Forge a stage's artifact into the Central Knowledge Base. Async; poll
    /api/playable/job/{job_id} (result carries ok, artifact, summary, keys)."""
    fn = _FORGES.get(stage)
    if not fn:
        return {"error": f"unknown forge stage '{stage}'", "forgeable": list(_FORGES)}
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"error": "game not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": f"forge:{stage}", "parent_id": pid,
        "created_at": _now()})
    asyncio.create_task(_run_job(job_id, _stamped(pid, stage, fn(pid))))
    return {"job_id": job_id, "job_status": "running", "stage": stage}


# ── Iterate & Refine — chat-refine a stage (the flowchart's red feedback arrow) ──
class RefineBody(BaseModel):
    instruction: str = ""


@router.post("/{pid}/refine/{stage}/async")
async def refine_stage(pid: str, stage: str, body: RefineBody):
    """💬 Re-forge a stage's artifact with a creator's natural-language refinement note.
    Async; poll /api/playable/job/{job_id}."""
    fn = _FORGES.get(stage)
    if not fn:
        return {"error": f"unknown stage '{stage}'", "forgeable": list(_FORGES)}
    note = (body.instruction or "").strip()
    if not note:
        return {"error": "instruction is required to refine"}
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"error": "game not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": f"refine:{stage}", "parent_id": pid,
        "instruction": note[:600], "created_at": _now()})
    # refining a stage invalidates any prior human approval of it
    await _db.game_kb.update_one(
        {"game_id": pid}, {"$unset": {f"approvals.{stage}": ""}})
    asyncio.create_task(_run_job(job_id, _stamped(pid, stage, fn(pid, note))))
    return {"job_id": job_id, "job_status": "running", "stage": stage, "refine": True}


# ── Iterate & Refine — human approval gate (the flowchart's chat/approvals loop) ──
class ApproveBody(BaseModel):
    approved: bool = True
    note: str = ""


@router.post("/{pid}/approve/{stage}")
async def approve_stage(pid: str, stage: str, body: ApproveBody):
    """✓ Approve (or un-approve) a pipeline stage. Stored in the KB so the Studio
    Pipeline tracker shows which stages have passed human review."""
    if stage not in _APPROVABLE:
        return {"error": f"'{stage}' is not an approvable stage", "approvable": sorted(_APPROVABLE)}
    if body.approved:
        await _db.game_kb.update_one(
            {"game_id": pid},
            {"$set": {f"approvals.{stage}": {"approved": True, "at": _now(),
                                             "note": (body.note or "")[:300]},
                      "game_id": pid}}, upsert=True)
    else:
        await _db.game_kb.update_one({"game_id": pid}, {"$unset": {f"approvals.{stage}": ""}})
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "approvals": 1})
    return {"ok": True, "stage": stage, "approved": body.approved,
            "approvals": (kb or {}).get("approvals") or {}}


@router.get("/{pid}/kb")
async def get_kb(pid: str):
    """The Central Game Knowledge Base for a game: which artifacts exist + summaries."""
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0})
    arts = (kb or {}).get("artifacts") or {}
    # also reflect artifacts owned by other subsystems
    has_world = bool(await _db.worldforge_worlds.find_one(
        {"source": "playable", "source_id": pid}, {"_id": 1}))
    asset_kinds = await _db.asset_genesis.distinct("kind", {"game_id": pid})
    catalogue = [
        {"name": "core_specs", "label": "core_specs.json", "stage": "spec",
         "present": "core_specs" in arts,
         "summary": (arts.get("core_specs") or {}).get("logline", "")[:140]},
        {"name": "lore_graph", "label": "lore_graph.json", "stage": "world",
         "present": ("lore_graph" in arts) or has_world,
         "summary": (f"{len((arts.get('lore_graph') or {}).get('regions', []))} regions"
                     if "lore_graph" in arts else ("WorldForge lore" if has_world else ""))},
        {"name": "quest_db", "label": "quest_DB.json", "stage": "narrative",
         "present": "quest_db" in arts,
         "summary": (f"{len((arts.get('quest_db') or {}).get('quests', []))} quests"
                     if "quest_db" in arts else "")},
        {"name": "mechanics_config", "label": "mechanics_config.json", "stage": "mechanics",
         "present": "mechanics_config" in arts,
         "summary": f"{len((arts.get('mechanics_config') or {}).get('core_mechanics', []))} mechanics"
                    if "mechanics_config" in arts else ""},
        {"name": "procedural_config", "label": "procedural_config.json", "stage": "procedural",
         "present": "procedural_config" in arts,
         "summary": (f"{len((arts.get('procedural_config') or {}).get('requirements', []))} requirements"
                     if "procedural_config" in arts else "")},
        {"name": "asset_manifest", "label": "asset_manifest.json", "stage": "assets",
         "present": ("asset_manifest" in arts) or len(asset_kinds) > 0,
         "summary": ((arts.get("asset_manifest") or {}).get("status", "")
                     + f" · {(arts.get('asset_manifest') or {}).get('asset_count', len(asset_kinds))} assets"
                     if "asset_manifest" in arts else f"{len(asset_kinds)} asset kinds")},
        {"name": "build_manifest", "label": "build_manifest.json", "stage": "build",
         "present": "build_manifest" in arts,
         "summary": (arts.get("build_manifest") or {}).get("checksum", "") if "build_manifest" in arts else ""},
        {"name": "qa_report", "label": "qa_report.json", "stage": "qa",
         "present": "qa_report" in arts,
         "summary": (f"score {(arts.get('qa_report') or {}).get('score', '?')}"
                     if "qa_report" in arts else "")},
        {"name": "camera_director", "label": "camera_director.json", "stage": "cinematics",
         "present": "camera_director" in arts,
         "summary": ((lambda c: f"{len(c.get('rigs', []))} rigs · {len(c.get('scenes', []))} scenes"
                      if c else "")((arts.get("camera_director") or {})))},
        {"name": "launch_manifest", "label": "launch_manifest.json", "stage": "launch",
         "present": "launch_manifest" in arts,
         "summary": ((arts.get("launch_manifest") or {}).get("store_listing") or {}).get("app_name", "")
                    if "launch_manifest" in arts else ""},
    ]
    stale = (kb or {}).get("stale") or {}
    for a in catalogue:
        a["stale"] = a["name"] in stale
    return {"game_id": pid, "artifacts": catalogue,
            "present_count": sum(1 for a in catalogue if a["present"]),
            "total": len(catalogue), "updated_at": (kb or {}).get("updated_at"),
            "approvals": (kb or {}).get("approvals") or {},
            "stale": stale, "provenance": (kb or {}).get("provenance") or {},
            "data": {k: arts.get(k) for k in
                     ("core_specs", "lore_graph", "quest_db", "mechanics_config",
                      "procedural_config", "asset_manifest", "build_manifest",
                      "qa_report", "launch_manifest")},
            "core_specs": arts.get("core_specs"), "mechanics_config": arts.get("mechanics_config")}


class KBEdit(BaseModel):
    data: dict


@router.put("/{pid}/kb/{artifact}")
async def edit_kb(pid: str, artifact: str, body: KBEdit):
    """✏️ Inline-edit a KB artifact — save edited JSON back to the Central Knowledge Base."""
    if artifact not in _EDITABLE:
        return {"error": f"'{artifact}' is not editable", "editable": sorted(_EDITABLE)}
    if not isinstance(body.data, dict) or not body.data:
        return {"error": "data must be a non-empty JSON object"}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {f"artifacts.{artifact}": body.data, "updated_at": _now(), "game_id": pid}},
        upsert=True)
    return {"ok": True, "artifact": artifact, "keys": list(body.data.keys())}
