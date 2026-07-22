"""
🧲 PHYSICS-WIRE — bake a deterministic physics engine into a generated game (Segment V.2).

Retrofits a working HTML5 game with a tiny, self-contained Verlet physics engine
(`window.PHYSICS`): gravity, AABB collision detection + minimal-translation resolution,
restitution/friction, grounded detection, and a `shatter()` destruction helper. The LLM
pass rewires the game's movement/collision so entities are driven by the engine; we then
DETERMINISTICALLY inject it into <head>.

Mirrors routes/playable_sentience.py (LLM rewrite → runnability gate → deterministic
inject → persist with version++ + edit_trail). The engine is fully guarded so the game
never breaks even if a call site is missing.
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

# ── deterministic Verlet physics engine injected into <head> ──
_PHYSICS_ENGINE = (
    "<script id=\"__physics\">"
    "window.PHYSICS=(function(){var G=0.5;"
    "function B(o){o=o||{};this.x=o.x||0;this.y=o.y||0;this.px=this.x-(o.vx||0);this.py=this.y-(o.vy||0);"
    "this.w=o.w||10;this.h=o.h||10;this.m=(o.m==null?1:o.m);this.restitution=(o.restitution==null?0.3:o.restitution);"
    "this.friction=(o.friction==null?0.98:o.friction);this.static=!!o.static;this.grounded=false;}"
    "B.prototype.setVel=function(vx,vy){this.px=this.x-vx;this.py=this.y-vy;};"
    "B.prototype.vel=function(){return{x:this.x-this.px,y:this.y-this.py};};"
    "B.prototype.applyForce=function(fx,fy){this.x+=fx/this.m;this.y+=fy/this.m;};"
    "B.prototype.integrate=function(dt,gravity){if(this.static)return;dt=dt||1;"
    "var vx=(this.x-this.px)*this.friction,vy=(this.y-this.py)*this.friction;"
    "this.px=this.x;this.py=this.y;this.x+=vx;this.y+=vy+(gravity==null?G:gravity)*dt;this.grounded=false;};"
    "function aabb(a,b){return Math.abs(a.x-b.x)*2<(a.w+b.w)&&Math.abs(a.y-b.y)*2<(a.h+b.h);}"
    "function resolve(a,b){if(!aabb(a,b))return false;"
    "var ox=(a.w+b.w)/2-Math.abs(a.x-b.x),oy=(a.h+b.h)/2-Math.abs(a.y-b.y);"
    "if(ox<oy){var s=a.x<b.x?-1:1;if(!a.static)a.x+=s*ox*(b.static?1:0.5);if(!b.static)b.x-=s*ox*(a.static?1:0.5);"
    "if(!a.static)a.px=a.x+(a.x-a.px)*-a.restitution;}"
    "else{var t=a.y<b.y?-1:1;if(!a.static)a.y+=t*oy*(b.static?1:0.5);if(!b.static)b.y-=t*oy*(a.static?1:0.5);"
    "if(t<0){a.grounded=true;}else{b.grounded=true;}"
    "if(!a.static)a.py=a.y+(a.y-a.py)*-a.restitution;}return true;}"
    "function shatter(x,y,n){var out=[];for(var i=0;i<(n||12);i++){out.push(new B({x:x,y:y,"
    "vx:(Math.random()-0.5)*6,vy:-Math.random()*5,w:3,h:3,restitution:0.4}));}return out;}"
    "return{Body:function(o){return new B(o);},integrate:function(b,dt,g){b.integrate(dt,g);},"
    "resolve:resolve,aabb:aabb,shatter:shatter,gravity:G,version:1};})();"
    "</script>"
)

_PHYSICS_SYS = _GAME_SYS + (
    "\n\nYou are in PHYSICS-WIRE MODE on an existing, working HTML5 game. A tiny deterministic Verlet "
    "physics engine is preloaded globally as `window.PHYSICS`. Give the game real, stable physics by "
    "driving its dynamic entities through physics bodies:\n"
    "  • Create a body per dynamic entity: `entity.body = window.PHYSICS.Body({x, y, w, h, "
    "restitution:0.3, friction:0.98});` (use {static:true} for ground/platforms/walls).\n"
    "  • Each frame: `window.PHYSICS.integrate(entity.body, dt, gravity)` then resolve collisions "
    "against solids `window.PHYSICS.resolve(entity.body, solid.body)` and read back "
    "`entity.x=entity.body.x; entity.y=entity.body.y;` Use `entity.body.grounded` to gate jumps and "
    "`entity.body.setVel(vx,vy)` for input-driven motion.\n"
    "  • Optionally use `window.PHYSICS.shatter(x,y,n)` for destruction/debris on impactful events.\n"
    "ALWAYS guard each call (`if(window.PHYSICS && entity.body){...}`) and KEEP the original movement as a "
    "fallback so the game never breaks. Preserve ALL controls, scoring, win/lose and runnability — improve "
    "the FEEL (gravity/bounce/collision), not the rules. Do NOT redefine window.PHYSICS. Keep it a single "
    "self-contained runnable HTML file. Return the FULL updated HTML document.")


async def _do_physics(pid: str) -> dict:
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not doc or not doc.get("html"):
        return {"error": "not found", "applied": False}
    prev_score = int(doc.get("playability_score") or 0)
    prompt = (
        f"ORIGINAL BRIEF:\n{doc.get('brief', '')}\n\n"
        "Give this game deterministic physics via window.PHYSICS (gravity + AABB collision + "
        "restitution/friction + grounded) as instructed, with guards + fallbacks. Return the FULL "
        f"updated single-file HTML:\n{doc['html'][:16000]}"
    )
    try:
        routed = await asyncio.to_thread(_llm_in_thread, prompt, _PHYSICS_SYS, _GAME_ENSEMBLE)
    except Exception:
        return {"playable_id": pid, "applied": False, "error": "physics model unavailable"}
    new_html, removed = _sanitize(_extract_html(routed.get("content", "")))
    val = _validate(new_html)
    floor = max(PLAYABILITY_THRESHOLD, prev_score - 15)
    if not new_html or val["score"] < floor:
        return {"playable_id": pid, "applied": False, "score": val["score"],
                "missing": val.get("missing", []), "prev_score": prev_score}
    final_html = inject_into_head(new_html, _PHYSICS_ENGINE)
    trail = doc.get("edit_trail") or []
    trail.append({"n": len(trail) + 1, "kind": "physics",
                  "instruction": "wired deterministic Verlet physics (gravity + collision)",
                  "score": val["score"], "model": routed.get("model"),
                  "at": datetime.now(timezone.utc).isoformat()})
    version = int(doc.get("version") or 1) + 1
    await _db.playables.update_one({"playable_id": pid}, {"$set": {
        "html": final_html, "bytes": len(final_html), "status": "ready",
        "playability_score": val["score"], "intricacy": val.get("intricacy"),
        "edit_trail": trail, "version": version, "sanitized": removed,
        "has_physics": True, "edited_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"playable_id": pid, "applied": True, "kind": "physics", "version": version,
            "score": val["score"], "raw_path": f"/api/playable/{pid}/raw"}


@router.post("/{pid}/apply-physics/async")
async def apply_physics_async(pid: str):
    """🧲 Give this game deterministic physics (gravity + AABB collision + restitution).
    Async; poll /job/{job_id} (result carries applied, version, score)."""
    from core.anti_farm import allow
    if not allow(f"physics:{pid}", rate_per_sec=0.2, burst=4):
        return {"error": "rate_limited", "detail": "Too many physics runs on this game — slow down."}
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "physics", "parent_id": pid,
        "created_at": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(_run_job(job_id, _do_physics(pid)))
    return {"job_id": job_id, "job_status": "running"}
