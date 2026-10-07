"""
🏛️ FACTIONS-WIRE — bake a LIVE faction/world-events sim into a generated game (III.4 → in-game).

Injects a tiny, deterministic client-side faction engine (`window.FACTIONS`): N rival
factions with a relationship matrix that drifts over time, forming alliances and
declaring wars and emitting world-EVENTS. The LLM pass wires the game to tick the sim
and surface those events as on-screen banners / light gameplay modifiers, giving the
world a living political backdrop. Mirrors the other wire passes (gate → inject → persist).
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

_FACTIONS_ENGINE = (
    "<script id=\"__factions\">"
    "window.FACTIONS=(function(){"
    "var P=['Iron','Crimson','Azure','Golden','Shadow','Verdant','Storm','Sun','Frost','Ember'];"
    "var K=[['Empire','\\uD83C\\uDFDB\\uFE0F'],['Clans','\\uD83E\\uDE93'],['Guild','\\u2692\\uFE0F'],"
    "['Order','\\u271D\\uFE0F'],['Nomads','\\uD83D\\uDC0E'],['Dynasty','\\uD83D\\uDC51'],"
    "['Syndicate','\\uD83C\\uDFAD'],['Horde','\\uD83D\\uDC80']];"
    "function rng(s){s=s|0;return function(){s=(s*1103515245+12345)&0x7fffffff;return s/0x7fffffff;};}"
    "function init(o){o=o||{};var PR=(typeof window!=='undefined'&&window.__FACTION_PRESET)||{};"
    "var nm=o.names||PR.names||[];var n=Math.max(3,Math.min(o.n||(nm.length||5),8));var r=rng(o.seed||PR.seed||1337);"
    "var f=[];for(var i=0;i<n;i++){var k=K[i%K.length];"
    "f.push({id:i,name:nm[i]||(P[(i*3+((r()*P.length)|0))%P.length]+' '+k[0]),icon:k[1],"
    "power:50+((r()*50)|0),allies:[],wars:[]});}"
    "var rel=[];for(var a=0;a<n;a++){rel.push([]);for(var b=0;b<n;b++){rel[a][b]=((r()*120)|0)-40;}}"
    "return{f:f,rel:rel,t:0,r:r,events:[]};}"
    "function tick(st){if(!st)return[];st.t++;var n=st.f.length,r=st.r,ev=[];"
    "var a=(r()*n)|0,b=(r()*n)|0;if(a!==b){st.rel[a][b]+=((r()*30)|0)-12;st.rel[b][a]=st.rel[a][b];"
    "if(st.rel[a][b]>=55&&st.f[a].allies.indexOf(b)<0){st.f[a].allies.push(b);st.f[b].allies.push(a);"
    "ev.push({k:'alliance',t:st.f[a].icon+' '+st.f[a].name+' allies with '+st.f[b].name});}"
    "else if(st.rel[a][b]<=-50&&st.f[a].wars.indexOf(b)<0){st.f[a].wars.push(b);st.f[b].wars.push(a);"
    "ev.push({k:'war',t:'\\u2694\\uFE0F '+st.f[a].name+' declares war on '+st.f[b].name});}}"
    "for(var i=0;i<n;i++){st.f[i].power+=st.f[i].allies.length-st.f[i].wars.length*2;}"
    "if(ev.length){st.events=st.events.concat(ev);}return ev;}"
    "function dominant(st){return st&&st.f?st.f.slice().sort(function(x,y){return y.power-x.power;})[0]:null;}"
    "return{init:init,tick:tick,dominant:dominant,version:1};})();"
    "</script>"
)

_FACTIONS_SYS = _GAME_SYS + (
    "\n\nYou are in FACTIONS-WIRE MODE on an existing, working HTML5 game. A deterministic live "
    "faction simulation is preloaded globally as `window.FACTIONS`. Give the world a living political "
    "backdrop WITHOUT changing core gameplay:\n"
    "  • On start: `var WORLD = window.FACTIONS.init({n:5, seed:1234});`\n"
    "  • Periodically advance it — e.g. every few seconds or on level/score milestones: "
    "`var evs = window.FACTIONS.tick(WORLD);` and for each returned event show a brief, non-blocking "
    "on-screen BANNER/toast with `ev.t` (auto-dismiss after ~3s; never pause or block input).\n"
    "  • Optionally let the dominant faction `window.FACTIONS.dominant(WORLD)` flavour the HUD (e.g. a "
    "small 'Ruling power: <icon> <name>' label) or apply a TINY cosmetic modifier. Keep it ambient.\n"
    "ALWAYS guard each call (`if(window.FACTIONS){...}`). Do NOT redefine window.FACTIONS, do NOT block "
    "the game loop, and KEEP all controls, collision, scoring, win/lose and runnability intact. Keep it a "
    "single self-contained runnable HTML file. Return the FULL updated HTML document.")


async def _do_factions(pid: str, world_id: str | None = None) -> dict:
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not doc or not doc.get("html"):
        return {"error": "not found", "applied": False}
    prev_score = int(doc.get("playability_score") or 0)
    prompt = (
        f"ORIGINAL BRIEF:\n{doc.get('brief', '')}\n\n"
        "Add a living faction/world-events backdrop via window.FACTIONS (init/tick/dominant) with "
        "non-blocking event banners as instructed, with guards. Return the FULL updated single-file "
        f"HTML:\n{doc['html'][:16000]}"
    )
    try:
        routed = await asyncio.to_thread(_llm_in_thread, prompt, _FACTIONS_SYS, _GAME_ENSEMBLE)
    except Exception:
        return {"playable_id": pid, "applied": False, "error": "factions model unavailable"}
    new_html, removed = _sanitize(_extract_html(routed.get("content", "")))
    val = _validate(new_html)
    floor = max(PLAYABILITY_THRESHOLD, prev_score - 15)
    if not new_html or val["score"] < floor:
        return {"playable_id": pid, "applied": False, "score": val["score"],
                "missing": val.get("missing", []), "prev_score": prev_score}
    preset = ""
    if world_id:
        import json as _json
        w = await _db.worldforge_worlds.find_one(
            {"world_id": world_id}, {"_id": 0, "pois": 1, "seed": 1, "name": 1})
        names = [p.get("name") for p in ((w or {}).get("pois") or []) if p.get("name")][:8]
        if names:
            preset = ("<script>window.__FACTION_PRESET=" + _json.dumps(
                {"names": names, "seed": int((w or {}).get("seed") or 1337),
                 "world": (w or {}).get("name")}) + ";</script>")
    final_html = inject_into_head(new_html, preset + _FACTIONS_ENGINE)
    trail = doc.get("edit_trail") or []
    trail.append({"n": len(trail) + 1, "kind": "factions",
                  "instruction": "wired live faction/world-events backdrop",
                  "score": val["score"], "model": routed.get("model"),
                  "at": datetime.now(timezone.utc).isoformat()})
    version = int(doc.get("version") or 1) + 1
    await _db.playables.update_one({"playable_id": pid}, {"$set": {
        "html": final_html, "bytes": len(final_html), "status": "ready",
        "playability_score": val["score"], "intricacy": val.get("intricacy"),
        "edit_trail": trail, "version": version, "sanitized": removed,
        "has_factions": True, "edited_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"playable_id": pid, "applied": True, "kind": "factions", "version": version,
            "score": val["score"], "raw_path": f"/api/playable/{pid}/raw"}


@router.post("/{pid}/apply-factions/async")
async def apply_factions_async(pid: str, world_id: str | None = None):
    """🏛️ Add a live faction/world-events backdrop (alliances, wars, ruling power) to this game.
    Optional ?world_id seeds faction names from that Worldforge world's POIs.
    Async; poll /job/{job_id} (result carries applied, version, score)."""
    from core.anti_farm import allow
    if not allow(f"factions:{pid}", rate_per_sec=0.2, burst=4):
        return {"error": "rate_limited", "detail": "Too many factions runs on this game — slow down."}
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "factions", "parent_id": pid,
        "world_id": world_id, "created_at": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(_run_job(job_id, _do_factions(pid, world_id)))
    return {"job_id": job_id, "job_status": "running"}
