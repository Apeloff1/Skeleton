"""Source-authored, deterministic playable 2D grid scene world for offline studios.

Implements real grid movement and proximity-bound quest interactions, distinct
from native target-genre mechanics. No network, provider or external assets.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_story_html import story_source
from .studio_ecosystem_quest import StudioQuestError

WIDTH=18
HEIGHT=12
SPAWN=(1,1)
TARGET=(WIDTH-4,HEIGHT-4)

_SCRIPT="""
"use strict";
const world=JSON.parse(document.getElementById("world-source").textContent);
const canvas=document.getElementById("view");
const ctx=canvas.getContext("2d");
const hud=document.getElementById("hud");
const choicesEl=document.getElementById("choices");
const historyEl=document.getElementById("history");
const stepsEl=document.getElementById("steps");
let stageIndex=0;
let player={x:1,y:1};
let steps=0;
const choices=[];
function text(tag,value){const el=document.createElement(tag);el.textContent=value;return el;}
function current(){return world.stages[stageIndex];}
function nearMarker(){
 return !!current() && Math.abs(player.x-world.target[0])+
                           Math.abs(player.y-world.target[1])<=1;
}
function draw(){
 ctx.fillStyle="#101b29";ctx.fillRect(0,0,canvas.width,canvas.height);
 const stage=current();
 if(!stage){
   hud.textContent="All source-authored stages completed (sandbox only).";
   choicesEl.replaceChildren();historyEl.textContent=JSON.stringify(choices);
   return;
 }
 const cells=world.maps[stageIndex];
 for(let y=0;y<world.height;y++){
   for(let x=0;x<world.width;x++){
     ctx.fillStyle=cells[y][x]==="#"?"#34495a":(x+y)%2?"#1e3949":"#244454";
     ctx.fillRect(x*40+1,y*40+1,38,38);
   }
 }
 ctx.fillStyle="#ebc66f";
 ctx.fillRect(world.target[0]*40+9,world.target[1]*40+9,22,22);
 ctx.fillStyle="#62d7c1";
 ctx.beginPath();ctx.arc(player.x*40+20,player.y*40+20,13,0,Math.PI*2);ctx.fill();
 hud.textContent="Scene "+(stageIndex+1)+"/"+world.stages.length+
   ": "+stage.scene_id+". Objective: reach marker, choose an authored action.";
 stepsEl.textContent="Moves: "+steps+"; marker object: "+stage.objects[0];
 choicesEl.replaceChildren();
 if(nearMarker()){
   choicesEl.append(text("h2","Nearby object: "+stage.objects[0]));
   for(const choice of stage.alternatives){
     const button=text("button",choice);button.type="button";
     button.addEventListener("click",()=>choose(choice));choicesEl.append(button);
   }
 }
 historyEl.textContent=JSON.stringify(choices);
}
function move(dx,dy){
 if(!current())return;
 const x=player.x+dx,y=player.y+dy;
 if(x<0||x>=world.width||y<0||y>=world.height)return;
 if(world.maps[stageIndex][y][x]==="#")return;
 player.x=x;player.y=y;steps++;draw();
}
function choose(choice){
 const stage=current();
 if(!stage||!nearMarker()||!stage.alternatives.includes(choice))return;
 choices.push([stage.id,choice]);
 stageIndex++;player={x:1,y:1};draw();
}
const keys={ArrowUp:[0,-1],ArrowDown:[0,1],ArrowLeft:[-1,0],
 ArrowRight:[1,0],w:[0,-1],s:[0,1],a:[-1,0],d:[1,0]};
document.addEventListener("keydown",event=>{
 if(event.target instanceof HTMLButtonElement)return;
 const delta=keys[event.key];
 if(delta){event.preventDefault();move(delta[0],delta[1]);}
});
document.querySelectorAll("[data-dx]").forEach(button=>{
 button.addEventListener("click",()=>move(Number(button.dataset.dx),
                                          Number(button.dataset.dy)));
});
document.getElementById("restart").addEventListener("click",()=>{
 stageIndex=0;player={x:1,y:1};steps=0;choices.length=0;draw();
});
draw();
"""
_CSS="""
:root{color-scheme:dark;background:#111e2b;color:#eef5fb;font:16px system-ui}
body{max-width:960px;margin:auto;padding:clamp(12px,3vw,32px)}
canvas{max-width:100%;height:auto;border:3px solid #85b3c3;display:block}
button{font:inherit;background:#174b69;color:#fff;border:2px solid #84bbd0;
padding:12px;border-radius:8px;margin:4px;cursor:pointer}
button:focus-visible{outline:3px solid #f6c965}#choices{min-height:90px}
.controls{display:grid;grid-template-columns:repeat(3,70px);gap:4px}
.controls button{margin:0}small{color:#baccdb}pre{white-space:pre-wrap}
"""

def _cell(seed: bytes, x: int, y: int) -> bool:
    digest=sha256(seed+bytes((x,y))).digest()
    return digest[0]<33


def _reachable(rows: list[str]) -> bool:
    queue=deque([SPAWN])
    seen={SPAWN}
    while queue:
        x,y=queue.popleft()
        if (x,y)==TARGET:
            return True
        for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if (0<=nx<WIDTH and 0<=ny<HEIGHT and rows[ny][nx]!="#"
                    and (nx,ny) not in seen):
                seen.add((nx,ny));queue.append((nx,ny))
    return False


def playable_world_source(documents: Mapping[str, Any]) -> dict[str, object]:
    source=story_source(documents)
    maps=[]
    for stage in source["stages"]:
        seed=sha256((source["source_digest"]+":"+stage["id"]).encode("utf-8")).digest()
        rows=[]
        for y in range(HEIGHT):
            row=[]
            for x in range(WIDTH):
                border=x==0 or y==0 or x==WIDTH-1 or y==HEIGHT-1
                # Always preserve a guaranteed, visible traversable route
                # along the northern row and then south to the scene marker.
                corridor=(y==1 and 1<=x<=TARGET[0]) or (
                    x==TARGET[0] and 1<=y<=TARGET[1])
                blocked=border or (not corridor and _cell(seed,x,y))
                row.append("#" if blocked else ".")
            rows.append("".join(row))
        if not _reachable(rows):
            raise StudioQuestError("procedural scene sealed the authored marker")
        maps.append(rows)
    return {"schema":"skeleton.game_builder.offline_walkable_world.v1",
            "project_id":source["project_id"],
            "source_digest":source["source_digest"],
            "width":WIDTH,"height":HEIGHT,"spawn":list(SPAWN),
            "target":list(TARGET),"maps":maps,"stages":source["stages"],
            "target_genre_runtime_implemented":False,"release_certified":False}


def render_playable_world_html(documents: Mapping[str, Any]) -> bytes:
    source=playable_world_source(documents)
    payload=json.dumps(source,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False)
    payload=payload.replace("<",r"\u003c").replace(">",r"\u003e").replace("&",r"\u0026")
    html=(
      "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none';"
      " script-src 'unsafe-inline'; style-src 'unsafe-inline';"
      " base-uri 'none'; form-action 'none'\"><title>Original walkable studio</title>"
      "<style>"+_CSS+"</style></head><body><h1>Walkable original studio prototype</h1>"
      "<p>Arrow keys/WASD or controls move. Reach gold object to select an action.</p>"
      "<p id='hud' role='status' aria-live='polite'></p>"
      "<canvas id='view' width='720' height='480' role='img' "
      "aria-label='Top-down maze with turquoise player and gold interaction marker'></canvas>"
      "<small id='steps'></small><div class='controls' aria-label='Movement buttons'>"
      "<span></span><button type='button' data-dx='0' data-dy='-1'>Up</button><span></span>"
      "<button type='button' data-dx='-1' data-dy='0'>Left</button>"
      "<button type='button' data-dx='0' data-dy='1'>Down</button>"
      "<button type='button' data-dx='1' data-dy='0'>Right</button></div>"
      "<section id='choices' aria-live='polite'></section>"
      "<button id='restart' type='button'>Restart</button>"
      "<h2>Sandbox decisions</h2><pre id='history'></pre>"
      "<script type='application/json' id='world-source'>"+payload+"</script>"
      "<script>"+_SCRIPT+"</script></body></html>"
    )
    return html.encode("utf-8")
