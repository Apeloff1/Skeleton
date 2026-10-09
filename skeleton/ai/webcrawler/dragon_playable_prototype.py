"""Original playable micro-prototype generation from Dragon Forge specifications.

Produces a self-contained HTML file with keyboard controls and simple
physics. It is deliberately an original abstract prototype rather than a
reproduction of any observed game. All content is generated from fixed
templates and validated numeric parameters; user text is HTML-escaped.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from html import escape
import json

from .dragon_game_forge import GamePrototypeSpec
from .dragon_game_mechanics import Mechanic


@dataclass(frozen=True)
class PlayablePrototype:
    candidate_id: str
    html: str
    content_digest: str
    supported_mechanics: tuple[str, ...]
    deferred_mechanics: tuple[str, ...]


def render_playable_prototype(spec: GamePrototypeSpec, *,
                              authorized: bool) -> PlayablePrototype:
    if not authorized:
        raise PermissionError("prototype rendering requires authorization")
    if not spec.original_assets_required:
        raise ValueError("original asset requirement cannot be disabled")
    if not spec.mechanics or len(spec.mechanics) > 16:
        raise ValueError("invalid prototype mechanics")
    enabled = {item.mechanic for item in spec.mechanics}
    supported = {
        Mechanic.MOVEMENT, Mechanic.PLATFORMING, Mechanic.PHYSICS,
        Mechanic.EXPLORATION, Mechanic.LEVEL_DESIGN,
    }
    implemented = tuple(sorted(m.value for m in enabled & supported))
    deferred = tuple(sorted(m.value for m in enabled - supported))
    title = escape(spec.title[:120])
    goal = escape(spec.design_goal[:400])
    # No third-party scripts, fonts, textures, network calls or embeds.
    config = json.dumps({
        "movement": Mechanic.MOVEMENT in enabled or Mechanic.PLATFORMING in enabled,
        "jump": Mechanic.PLATFORMING in enabled or Mechanic.PHYSICS in enabled,
        "exploration": Mechanic.EXPLORATION in enabled,
        "physics": Mechanic.PHYSICS in enabled,
        "arena": sha256(spec.candidate_id.encode()).digest()[0] % 4,
    }, separators=(",", ":"))
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; form-action 'none'">
<title>""" + title + """</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif}
body{margin:0;background:#152c28;color:#f0f7ee;display:grid;place-items:center;min-height:100vh}
main{width:min(95vw,850px)}canvas{display:block;width:100%;border:2px solid #9bd8b3;border-radius:14px;background:#203c37}
button{margin:8px 6px 8px 0;padding:10px 15px;border:0;border-radius:8px;background:#9bd8b3;color:#17362a}\n.controls{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;margin:10px 0}\n.controls button{min-height:58px;min-width:76px;font-size:18px;touch-action:none;user-select:none}\n@media(pointer:fine){.controls{opacity:.85}}
p{line-height:1.5}small{opacity:.8}
</style></head><body><main>
<h1>""" + title + """</h1><p>""" + goal + """</p>
<p>Move: A/D or arrows. Jump: Space. Restart: R. Explore the original arena. Find all stars if shown, then reach the golden crystal.</p>
<canvas id="game" width="800" height="450" aria-label="Playable original game prototype"></canvas>
<div class="controls" aria-label="Game controls">
<button type="button" data-key="KeyA" aria-label="Move left">◀</button>
<button type="button" data-key="KeyD" aria-label="Move right">▶</button>
<button type="button" data-key="Space" aria-label="Jump">⬆ Jump</button>
<button type="button" id="touchRestart" aria-label="Restart level">↻ Restart</button>
</div>
<p id="status" role="status" aria-live="polite">Ready to explore</p>
<button id="restart" type="button">Restart</button>
<small>Original geometric assets only. No telemetry or external connections.</small>
<script>
"use strict";
const settings = """ + config + """;
const canvas=document.getElementById("game");
const ctx=canvas.getContext("2d");
const status=document.getElementById("status");
const keys=new Set();
const player={x:45,y:330,vx:0,vy:0,w:25,h:32,grounded:false};
const goal={x:715,y:330,w:27,h:30};
const layouts=[
 [{x:175,y:330,w:130,h:15},{x:375,y:275,w:140,h:15},{x:590,y:340,w:110,h:15}],
 [{x:145,y:354,w:120,h:15},{x:325,y:298,w:110,h:15},{x:520,y:322,w:160,h:15}],
 [{x:110,y:315,w:120,h:15},{x:312,y:254,w:125,h:15},{x:565,y:291,w:130,h:15}],
 [{x:200,y:347,w:135,h:15},{x:400,y:300,w:95,h:15},{x:555,y:248,w:175,h:15}]
];
const platforms=[{x:0,y:405,w:800,h:45},...layouts[settings.arena]];
const pad={x:300,y:390,w:64,h:14};
const stars=[{x:145,y:370,w:16,h:16},{x:420,y:240,w:16,h:16},{x:635,y:307,w:16,h:16}];
let secrets=new Set(),won=false;
function reset(){
 player.x=45;player.y=330;player.vx=0;player.vy=0;
 player.grounded=false;won=false;secrets.clear();status.textContent="Explore the level";
}
document.getElementById("restart").addEventListener("click",reset);
document.getElementById("touchRestart").addEventListener("click",reset);
document.querySelectorAll("[data-key]").forEach(button=>{
 const name=button.getAttribute("data-key");
 const down=event=>{event.preventDefault();keys.add(name);};
 const up=event=>{event.preventDefault();keys.delete(name);};
 button.addEventListener("pointerdown",down);
 button.addEventListener("pointerup",up);
 button.addEventListener("pointercancel",up);
 button.addEventListener("lostpointercapture",()=>keys.delete(name));
 button.addEventListener("pointerleave",()=>keys.delete(name));
});
window.addEventListener("keydown",e=>{
 if(["ArrowLeft","ArrowRight","Space","ArrowUp"].includes(e.code))e.preventDefault();
 keys.add(e.code);if(e.code==="KeyR")reset();
});
window.addEventListener("keyup",e=>keys.delete(e.code));
window.addEventListener("blur",()=>keys.clear());
function overlap(a,b){return a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;}
function update(dt){
 if(won)return;
 const horizontal=Number(keys.has("KeyD")||keys.has("ArrowRight"))-
                  Number(keys.has("KeyA")||keys.has("ArrowLeft"));
 const acceleration=settings.movement?0.9:0;
 player.vx=Math.max(-5,Math.min(5,player.vx+horizontal*acceleration*dt));
 if(!horizontal)player.vx*=Math.pow(0.77,dt);
 if(settings.jump&&player.grounded&&(keys.has("Space")||keys.has("ArrowUp"))){
   player.vy=-11.5;player.grounded=false;
 }
 player.vy=Math.min(15,player.vy+0.48*dt);
 const previousBottom=player.y+player.h;
 player.x=Math.max(0,Math.min(800-player.w,player.x+player.vx*dt));
 player.y+=player.vy*dt;
 player.grounded=false;
 for(const platform of platforms){
  if(player.vy>=0&&previousBottom<=platform.y+5&&overlap(player,platform)){
   player.y=platform.y-player.h;player.vy=0;player.grounded=true;
  }
 }
 if(settings.physics&&player.vy>=0&&previousBottom<=pad.y+8&&overlap(player,pad)){
   player.y=pad.y-player.h;player.vy=-13.5;player.grounded=false;
 }
 if(settings.exploration)stars.forEach((star,i)=>{
   if(!secrets.has(i)&&overlap(player,star))secrets.add(i);
 });
 if(player.y>480)reset();
 if(overlap(player,goal)&&(!settings.exploration||secrets.size===stars.length)){
   won=true;status.textContent="Crystal found! Prototype complete.";
 }else if(settings.exploration&&!won){
   status.textContent="Find the 3 stars, then reach the golden crystal: "+secrets.size+"/3";
 }
}
function draw(){
 ctx.clearRect(0,0,800,450);
 ctx.fillStyle="#284d46";ctx.fillRect(0,0,800,450);
 for(let i=0;i<35;i++){
  ctx.fillStyle="#40695d";ctx.fillRect((i*127)%800,(i*83)%350,3,3);
 }
 ctx.fillStyle="#6aa38c";
 for(const platform of platforms)ctx.fillRect(platform.x,platform.y,platform.w,platform.h);
 if(settings.physics){ctx.fillStyle="#f4a261";ctx.fillRect(pad.x,pad.y,pad.w,pad.h);}
 if(settings.exploration){ctx.fillStyle="#c4b5fd";stars.forEach((star,i)=>{
   if(!secrets.has(i))ctx.fillRect(star.x,star.y,star.w,star.h);
 });}
 ctx.fillStyle="#f3cf6a";ctx.fillRect(goal.x,goal.y,goal.w,goal.h);
 ctx.fillStyle="#a3e2b6";ctx.fillRect(player.x,player.y,player.w,player.h);
 ctx.fillStyle="#f9e4c5";ctx.fillRect(player.x+15,player.y+6,4,4);
}
let previous=0,accumulator=0;
function frame(timestamp){
 if(!previous)previous=timestamp;
 accumulator+=Math.min(100,timestamp-previous);
 previous=timestamp;
 while(accumulator>=16.6667){update(1);accumulator-=16.6667;}
 draw();requestAnimationFrame(frame);
}
reset();requestAnimationFrame(frame);
</script></main></body></html>"""
    return PlayablePrototype(
        spec.candidate_id, html, sha256(html.encode()).hexdigest(),
        implemented, deferred,
    )
