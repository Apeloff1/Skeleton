"""
🎨 AESTHETICS-WIRE — neural-style post-FX + adaptive audio for a generated game (Segment IV).

Retrofits a working HTML5 game with two self-contained engines injected into <head>:
  • `window.NEURAL_FX`  — a canvas post-processing + juice layer (vignette, CRT scanlines,
    bloom-ish glow, screen-shake, particle bursts) applied each frame for a richer look.
  • `window.ADAPTIVE_AUDIO` — a WebAudio procedural soundtrack whose intensity tracks game
    state (danger/score/health) + one-shot SFX (hit/pickup/lose), with autoplay-policy
    resume on first interaction.

The LLM pass wires these into the render loop + key game events; we then DETERMINISTICALLY
inject the engines. Mirrors playable_artwire (rewrite → gate → inject → persist). Engines
are fully guarded so the game never breaks if a call site is missing.
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

_NEURAL_FX = (
    "window.NEURAL_FX=(function(){var shake=0;"
    "function postProcess(ctx,o){o=o||{};var cv=ctx&&ctx.canvas;if(!cv)return;try{"
    "var g=ctx.createRadialGradient(cv.width/2,cv.height/2,Math.min(cv.width,cv.height)*0.28,"
    "cv.width/2,cv.height/2,Math.max(cv.width,cv.height)*0.78);"
    "g.addColorStop(0,'rgba(0,0,0,0)');g.addColorStop(1,'rgba(0,0,0,'+(o.vignette==null?0.34:o.vignette)+')');"
    "ctx.save();ctx.fillStyle=g;ctx.fillRect(0,0,cv.width,cv.height);ctx.restore();}catch(e){}"
    "if(o.scanlines){ctx.save();ctx.globalAlpha=0.07;ctx.fillStyle='#000';"
    "for(var y=0;y<cv.height;y+=3){ctx.fillRect(0,y,cv.width,1);}ctx.restore();}"
    "if(o.grade){ctx.save();ctx.globalCompositeOperation='overlay';ctx.globalAlpha=0.10;"
    "ctx.fillStyle=o.grade;ctx.fillRect(0,0,cv.width,cv.height);ctx.restore();}}"
    "function glow(ctx,fn,color,blur){if(!ctx)return fn&&fn();ctx.save();ctx.shadowColor=color||'#7df';"
    "ctx.shadowBlur=blur||16;if(fn)fn();ctx.restore();}"
    "function addShake(a){shake=Math.max(shake,a||6);}"
    "function applyShake(ctx){if(ctx&&shake>0.3){var dx=(Math.random()-0.5)*shake,dy=(Math.random()-0.5)*shake;"
    "ctx.translate(dx,dy);shake*=0.88;}}"
    "function P(){this.p=[];}"
    "P.prototype.burst=function(x,y,n,color){for(var i=0;i<(n||10);i++){this.p.push({x:x,y:y,"
    "vx:(Math.random()-0.5)*5,vy:(Math.random()-0.5)*5,life:1,c:color||'#fff'});}};"
    "P.prototype.update=function(ctx){for(var i=this.p.length-1;i>=0;i--){var q=this.p[i];"
    "q.x+=q.vx;q.y+=q.vy;q.vy+=0.06;q.life-=0.03;if(q.life<=0){this.p.splice(i,1);continue;}"
    "if(ctx){ctx.save();ctx.globalAlpha=Math.max(0,q.life);ctx.fillStyle=q.c;ctx.fillRect(q.x,q.y,3,3);ctx.restore();}}};"
    "return{postProcess:postProcess,glow:glow,addShake:addShake,applyShake:applyShake,"
    "Particles:function(){return new P();},version:1};})();"
)

_ADAPTIVE_AUDIO = (
    "window.ADAPTIVE_AUDIO=(function(){var ctx=null,master=null,intensity=0,started=false;"
    "function ensure(){if(ctx)return ctx;try{var AC=window.AudioContext||window.webkitAudioContext;"
    "ctx=new AC();master=ctx.createGain();master.gain.value=0.10;master.connect(ctx.destination);}catch(e){ctx=null;}return ctx;}"
    "function note(t,f,dur,gain){if(!ctx)return;try{var o=ctx.createOscillator(),g=ctx.createGain();"
    "o.type=intensity>0.6?'sawtooth':'sine';o.frequency.value=f;g.gain.setValueAtTime(0,t);"
    "g.gain.linearRampToValueAtTime(gain,t+0.01);g.gain.exponentialRampToValueAtTime(0.0001,t+dur);"
    "o.connect(g);g.connect(master);o.start(t);o.stop(t+dur);}catch(e){}}"
    "function loop(){if(!ctx||!started)return;var t=ctx.currentTime;var bpm=88+intensity*78;var step=60/bpm/2;"
    "var base=110*(1+Math.floor(intensity*3));note(t,base,step*0.9,0.05+intensity*0.10);"
    "if(intensity>0.45)note(t,base*1.5,step*0.5,0.03+intensity*0.06);"
    "setTimeout(loop,step*1000);}"
    "function start(){if(started)return;ensure();if(!ctx)return;started=true;loop();}"
    "function setIntensity(v){intensity=Math.max(0,Math.min(1,(+v)||0));}"
    "function sfx(type){ensure();if(!ctx)return;var t=ctx.currentTime;"
    "var f=type==='hit'?170:type==='pickup'?680:type==='lose'?70:type==='win'?880:440;"
    "note(t,f,0.14,0.18);if(type==='pickup')note(t+0.06,f*1.5,0.10,0.12);}"
    "try{['pointerdown','keydown','touchstart'].forEach(function(e){window.addEventListener(e,function(){"
    "ensure();if(ctx&&ctx.state==='suspended'){try{ctx.resume();}catch(_){}}start();});});}catch(e){}"
    "return{start:start,setIntensity:setIntensity,sfx:sfx,version:1};})();"
)

_AESTHETICS_ENGINE = (
    "<script id=\"__aesthetics\">" + _NEURAL_FX + _ADAPTIVE_AUDIO + "</script>"
)

_AESTHETICS_SYS = _GAME_SYS + (
    "\n\nYou are in AESTHETICS-WIRE MODE on an existing, working HTML5 game. Two engines are "
    "preloaded globally: `window.NEURAL_FX` (canvas post-FX + juice) and `window.ADAPTIVE_AUDIO` "
    "(procedural adaptive soundtrack + SFX). Upgrade the look & feel WITHOUT changing gameplay:\n"
    "  • In the render loop, wrap the world draw so screen-shake applies: "
    "`ctx.save(); window.NEURAL_FX.applyShake(ctx); /* ...draw world... */ ctx.restore();` and AFTER "
    "drawing the world each frame call "
    "`window.NEURAL_FX.postProcess(ctx,{vignette:0.34, scanlines:true});`\n"
    "  • Keep ONE persistent particle system "
    "`var FX = window.NEURAL_FX.Particles();`, call `FX.update(ctx)` each frame, and "
    "`FX.burst(x,y,12,color)` + `window.NEURAL_FX.addShake(7)` on impactful events (explosions, hits).\n"
    "  • Audio: call `window.ADAPTIVE_AUDIO.start()` on first input; each frame "
    "`window.ADAPTIVE_AUDIO.setIntensity(dangerOrSpeed01)` from a 0..1 game-state signal; and "
    "`window.ADAPTIVE_AUDIO.sfx('hit'|'pickup'|'lose'|'win')` on the matching events.\n"
    "ALWAYS guard each call (`if(window.NEURAL_FX){...}` / `if(window.ADAPTIVE_AUDIO){...}`). Do NOT "
    "redefine these globals. Preserve ALL controls, collision, scoring, win/lose and runnability. "
    "Keep it a single self-contained runnable HTML file. Return the FULL updated HTML document.")



async def _do_aesthetics(pid: str) -> dict:
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not doc or not doc.get("html"):
        return {"error": "not found", "applied": False}
    prev_score = int(doc.get("playability_score") or 0)
    prompt = (
        f"ORIGINAL BRIEF:\n{doc.get('brief', '')}\n\n"
        "Upgrade this game's aesthetics via window.NEURAL_FX (post-FX + particles + shake) and "
        "window.ADAPTIVE_AUDIO (adaptive music + SFX) as instructed, with guards. Return the FULL "
        f"updated single-file HTML:\n{doc['html'][:16000]}"
    )
    try:
        routed = await asyncio.to_thread(_llm_in_thread, prompt, _AESTHETICS_SYS, _GAME_ENSEMBLE)
    except Exception:
        return {"playable_id": pid, "applied": False, "error": "aesthetics model unavailable"}
    new_html, removed = _sanitize(_extract_html(routed.get("content", "")))
    val = _validate(new_html)
    floor = max(PLAYABILITY_THRESHOLD, prev_score - 15)
    if not new_html or val["score"] < floor:
        return {"playable_id": pid, "applied": False, "score": val["score"],
                "missing": val.get("missing", []), "prev_score": prev_score}
    final_html = inject_into_head(new_html, _AESTHETICS_ENGINE)
    trail = doc.get("edit_trail") or []
    trail.append({"n": len(trail) + 1, "kind": "aesthetics",
                  "instruction": "wired neural post-FX + adaptive audio",
                  "score": val["score"], "model": routed.get("model"),
                  "at": datetime.now(timezone.utc).isoformat()})
    version = int(doc.get("version") or 1) + 1
    await _db.playables.update_one({"playable_id": pid}, {"$set": {
        "html": final_html, "bytes": len(final_html), "status": "ready",
        "playability_score": val["score"], "intricacy": val.get("intricacy"),
        "edit_trail": trail, "version": version, "sanitized": removed,
        "has_aesthetics": True, "edited_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"playable_id": pid, "applied": True, "kind": "aesthetics", "version": version,
            "score": val["score"], "raw_path": f"/api/playable/{pid}/raw"}


@router.post("/{pid}/apply-aesthetics/async")
async def apply_aesthetics_async(pid: str):
    """🎨 Add neural post-FX (bloom/vignette/CRT/particles/shake) + adaptive WebAudio music to
    this game. Async; poll /job/{job_id} (result carries applied, version, score)."""
    from core.anti_farm import allow
    if not allow(f"aesthetics:{pid}", rate_per_sec=0.2, burst=4):
        return {"error": "rate_limited", "detail": "Too many aesthetics runs on this game — slow down."}
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "aesthetics", "parent_id": pid,
        "created_at": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(_run_job(job_id, _do_aesthetics(pid)))
    return {"job_id": job_id, "job_status": "running"}
