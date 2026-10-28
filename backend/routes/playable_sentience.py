"""
👾 SENTIENCE-WIRE — bake living-NPC AI into a generated game (Segment III).

Retrofits a working HTML5 game with a tiny, self-contained NPC "brain" engine:
episodic MEMORY (NPCs remember what the player did), a BELIEF/GOAL state, and a
hybrid UTILITY-AI + behaviour selection (attack / chase / flee / patrol). The LLM
pass rewires the game's enemy/NPC update logic to drive each agent through
`window.SENTIENCE`; we then DETERMINISTICALLY inject the engine into <head>.

Mirrors routes/playable_artwire.py (LLM rewrite → runnability gate → deterministic
inject → persist with version++ + edit_trail). The engine is fully guarded so the
game never breaks even if a call site is missing.
"""
from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter

from routes.playable import (
    _db, _GAME_SYS, _GAME_ENSEMBLE, PLAYABILITY_THRESHOLD,
    _sanitize, _extract_html, _validate, _llm_in_thread, _run_job,
)
from routes.playable_htmlutils import inject_into_head

router = APIRouter(prefix="/api/playable", tags=["playable"])

# ── the deterministic, self-contained NPC-brain engine injected into <head> ──
_SENTIENCE_ENGINE = (
    "<script id=\"__sentience\">"
    "window.SENTIENCE=(function(){"
    "function A(o){o=o||{};this.id=o.id||(Math.random().toString(36).slice(2));"
    "this.memory=[];this.beliefs={threat:0,lastPlayer:null,health:(o.health==null?1:o.health),mood:'calm'};"
    "this.goals=o.goals||['patrol'];this.state='patrol';this.home=o.home||null;this.t=0;}"
    "A.prototype.remember=function(ev,data){this.memory.push({t:this.t,ev:ev,data:data||null});"
    "if(this.memory.length>40)this.memory.shift();return this;};"
    "A.prototype.recall=function(ev){for(var i=this.memory.length-1;i>=0;i--){if(this.memory[i].ev===ev)return this.memory[i];}return null;};"
    "A.prototype.perceive=function(p){this.t++;if(p){if(p.health!=null)this.beliefs.health=p.health;"
    "var d=(p.dist==null?9999:p.dist),r=(p.range==null?320:p.range);"
    "if(p.x!=null){this.beliefs.lastPlayer={x:p.x,y:p.y,seenAt:this.t};}"
    "this.beliefs.threat=Math.max(0,Math.min(1,1-d/r));"
    "if(p.damaged){this.remember('hurt',p.damaged);}}return this;};"
    # utility scoring over candidate actions -> picks a behaviour
    "A.prototype.decide=function(w){w=w||{};var b=this.beliefs;"
    "var s={attack:(b.threat>0.7?1:0)*(w.attack==null?1:w.attack),"
    "chase:(b.threat>0.2?b.threat:0)*(w.chase==null?0.9:w.chase),"
    "flee:(b.health<0.3?1:0)*(w.flee==null?1:w.flee),"
    "patrol:0.18*(w.patrol==null?1:w.patrol)};"
    "var best='patrol',bv=-1;for(var k in s){if(s[k]>bv){bv=s[k];best=k;}}"
    "this.state=best;this.beliefs.mood=(best==='flee'?'afraid':best==='attack'?'aggressive':best==='chase'?'alert':'calm');"
    "return best;};"
    "A.prototype.toward=function(x,y,spd){var lp=this.beliefs.lastPlayer;if(!lp)return{x:0,y:0};"
    "var dx=(this.state==='flee'?-1:1)*(lp.x-x),dy=(this.state==='flee'?-1:1)*(lp.y-y);"
    "var m=Math.hypot(dx,dy)||1;spd=spd||1;return{x:dx/m*spd,y:dy/m*spd};};"
    "return{Agent:function(o){return new A(o);},version:1};})();"
    "</script>"
)

_SENTIENCE_SYS = _GAME_SYS + (
    "\n\nYou are in SENTIENCE-WIRE MODE on an existing, working HTML5 game. A tiny NPC-brain "
    "engine is preloaded globally as `window.SENTIENCE`. Give the game's enemies / NPCs LIVING "
    "behaviour by driving each through a per-entity agent:\n"
    "  • On spawn: `entity.brain = window.SENTIENCE.Agent({health:1, goals:['patrol']});`\n"
    "  • Each update tick, BEFORE moving the entity: "
    "`entity.brain.perceive({x:player.x, y:player.y, dist:distToPlayer, range:340, "
    "health:entity.hpFraction, damaged:wasHitThisFrame}); var act = entity.brain.decide();`\n"
    "  • Then branch the entity's movement/attack on `act` ('attack'|'chase'|'flee'|'patrol') — "
    "use `entity.brain.toward(entity.x, entity.y, speed)` for chase/flee velocity, attack when "
    "'attack', wander/return-home when 'patrol'. Call `entity.brain.remember('saw_player')` etc "
    "so NPCs build memory, and you may surface mood via `entity.brain.beliefs.mood`.\n"
    "ALWAYS guard usage (`if(window.SENTIENCE && entity.brain){...}`) and KEEP the original "
    "behaviour as a fallback so the game never breaks. Preserve ALL controls, collision, scoring, "
    "win/lose and runnability. Do NOT redefine window.SENTIENCE. Keep it a single self-contained "
    "runnable HTML file. Return the FULL updated HTML document.")



async def _do_sentience(pid: str) -> dict:
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not doc or not doc.get("html"):
        return {"error": "not found", "applied": False}
    prev_score = int(doc.get("playability_score") or 0)
    prompt = (
        f"ORIGINAL BRIEF:\n{doc.get('brief', '')}\n\n"
        "Give this game's NPCs/enemies living AI via window.SENTIENCE (memory + belief/goal "
        "utility behaviour) as instructed, with guards + fallbacks. Return the FULL updated "
        f"single-file HTML:\n{doc['html'][:16000]}"
    )
    try:
        routed = await asyncio.to_thread(_llm_in_thread, prompt, _SENTIENCE_SYS, _GAME_ENSEMBLE)
    except Exception:
        return {"playable_id": pid, "applied": False, "error": "sentience model unavailable"}
    new_html, removed = _sanitize(_extract_html(routed.get("content", "")))
    val = _validate(new_html)
    floor = max(PLAYABILITY_THRESHOLD, prev_score - 15)
    if not new_html or val["score"] < floor:
        return {"playable_id": pid, "applied": False, "score": val["score"],
                "missing": val.get("missing", []), "prev_score": prev_score}
    final_html = inject_into_head(new_html, _SENTIENCE_ENGINE)
    trail = doc.get("edit_trail") or []
    trail.append({"n": len(trail) + 1, "kind": "sentience",
                  "instruction": "wired living-NPC AI (memory + utility behaviour)",
                  "score": val["score"], "model": routed.get("model"),
                  "at": datetime.now(timezone.utc).isoformat()})
    version = int(doc.get("version") or 1) + 1
    await _db.playables.update_one({"playable_id": pid}, {"$set": {
        "html": final_html, "bytes": len(final_html), "status": "ready",
        "playability_score": val["score"], "intricacy": val.get("intricacy"),
        "edit_trail": trail, "version": version, "sanitized": removed,
        "has_sentience": True, "edited_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"playable_id": pid, "applied": True, "kind": "sentience", "version": version,
            "score": val["score"], "raw_path": f"/api/playable/{pid}/raw"}


@router.post("/{pid}/apply-sentience/async")
async def apply_sentience_async(pid: str):
    """👾 Give this game's NPCs living AI (episodic memory + belief/goal utility behaviour).
    Async; poll /job/{job_id} (result carries applied, version, score)."""
    from core.anti_farm import allow
    if not allow(f"sentience:{pid}", rate_per_sec=0.2, burst=4):
        return {"error": "rate_limited", "detail": "Too many sentience runs on this game — slow down."}
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "sentience", "parent_id": pid,
        "created_at": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(_run_job(job_id, _do_sentience(pid)))
    return {"job_id": job_id, "job_status": "running"}
