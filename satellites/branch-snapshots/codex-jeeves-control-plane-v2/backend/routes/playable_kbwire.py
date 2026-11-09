"""
⚙️ KB-WIRE — apply the Central Knowledge Base into the actual game (KB → Implementation).

The flowchart's core arrow: the Implementation stage READS the Knowledge Base. This pass
feeds a game's forged artifacts (mechanics_config.json + core_specs.json + lore_graph.json)
to an LLM that retunes the running game so it reflects the designed systems (balance
params, progression, core loops) and lore (naming/theming/flavour text) — preserving
runnability. Mirrors routes/playable_artwire.py but for SYSTEMS+LORE instead of art.
"""
from __future__ import annotations

import json
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter

from routes.playable import (
    _db, _GAME_SYS, _GAME_ENSEMBLE, PLAYABILITY_THRESHOLD,
    _sanitize, _extract_html, _validate, _llm_in_thread, _run_job,
)

router = APIRouter(prefix="/api/playable", tags=["playable"])

_KB_SYS = _GAME_SYS + (
    "\n\nYou are in KB-SYNC MODE on an existing, working HTML5 game. You are given the game's "
    "design Knowledge Base (core_specs, mechanics_config, lore_graph, quest_db). RETUNE the game "
    "so it faithfully reflects it: apply mechanics_config balance_params + progression_curves to "
    "the relevant gameplay constants (speeds, spawn rates, difficulty ramp, score values), honour "
    "the core_loop/systems, apply lore_graph + core_specs naming/theming to on-screen text/titles/"
    "labels, and weave quest_db content into the game — use its quests as objectives/goals shown to "
    "the player, its character_bibles for NPC/entity names, and its dialogue_trees for intro/flavour/"
    "win-lose text. PRESERVE the control scheme, structure and runnability — change values, labels, "
    "text and tuning, NOT the engine. Keep it a single self-contained runnable HTML file. Return the "
    "FULL updated HTML document.")


async def _do_kbwire(pid: str) -> dict:
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not doc or not doc.get("html"):
        return {"error": "not found", "applied": False}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    arts = (kb or {}).get("artifacts") or {}
    use = {k: arts[k] for k in ("core_specs", "mechanics_config", "lore_graph", "quest_db") if k in arts}
    if not use:
        return {"playable_id": pid, "applied": False,
                "error": "no KB artifacts forged yet (forge spec/mechanics/world/narrative first)"}
    prev_score = int(doc.get("playability_score") or 0)
    kb_ctx = json.dumps(use)[:5000]
    prompt = (f"ORIGINAL BRIEF:\n{doc.get('brief', '')}\n\nKNOWLEDGE BASE:\n{kb_ctx}\n\n"
              "Retune the game to reflect this Knowledge Base, then return the FULL updated "
              f"single-file HTML:\n{doc['html'][:16000]}")
    try:
        routed = await asyncio.to_thread(_llm_in_thread, prompt, _KB_SYS, _GAME_ENSEMBLE)
    except Exception:
        return {"playable_id": pid, "applied": False, "error": "kb-sync model unavailable"}
    new_html, removed = _sanitize(_extract_html(routed.get("content", "")))
    val = _validate(new_html)
    floor = max(PLAYABILITY_THRESHOLD, prev_score - 15)
    if not new_html or val["score"] < floor:
        return {"playable_id": pid, "applied": False, "score": val["score"],
                "missing": val.get("missing", []), "prev_score": prev_score}
    trail = doc.get("edit_trail") or []
    trail.append({"n": len(trail) + 1, "kind": "kbwire",
                  "instruction": f"synced KB: {', '.join(use.keys())}",
                  "score": val["score"], "model": routed.get("model"),
                  "at": datetime.now(timezone.utc).isoformat()})
    version = int(doc.get("version") or 1) + 1
    await _db.playables.update_one({"playable_id": pid}, {"$set": {
        "html": new_html, "bytes": len(new_html), "status": "ready",
        "playability_score": val["score"], "intricacy": val.get("intricacy"),
        "edit_trail": trail, "version": version, "sanitized": removed,
        "kb_applied": True, "kb_applied_at": datetime.now(timezone.utc).isoformat(),
        "edited_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"playable_id": pid, "applied": True, "kind": "kbwire", "version": version,
            "synced": list(use.keys()), "score": val["score"],
            "raw_path": f"/api/playable/{pid}/raw"}


@router.post("/{pid}/apply-kb/async")
async def apply_kb_async(pid: str):
    """⚙️ Retune the game to reflect its forged Knowledge Base (mechanics + lore). Async;
    poll /job/{job_id} (result carries applied, synced[], version)."""
    from core.anti_farm import allow
    if not allow(f"kbwire:{pid}", rate_per_sec=0.2, burst=4):
        return {"error": "rate_limited", "detail": "Too many KB-sync runs on this game — slow down."}
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    arts = (kb or {}).get("artifacts") or {}
    if not any(k in arts for k in ("core_specs", "mechanics_config", "lore_graph", "quest_db")):
        return {"error": "no KB artifacts forged yet (forge spec/mechanics/world first)"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "kbwire", "parent_id": pid,
        "created_at": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(_run_job(job_id, _do_kbwire(pid)))
    return {"job_id": job_id, "job_status": "running"}
