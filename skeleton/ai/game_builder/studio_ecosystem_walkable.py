"""Source-authored, deterministic playable 2D grid scene world for offline studios.

Implements real grid movement and proximity-bound quest interactions, distinct
from native target-genre mechanics. No network, provider or external assets.
"""
from __future__ import annotations

from base64 import b64encode
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
let playerHealth=world.starting_health;
const choices=[];
const physicsEvents=[];
const npcTalks=[];
function text(tag,value){const el=document.createElement(tag);el.textContent=value;return el;}
function current(){return world.stages[stageIndex];}
function nearMarker(){
 return !!current() && Math.abs(player.x-world.target[0])+
                           Math.abs(player.y-world.target[1])<=1;
}
function npcReceipt(){
 return {schema:"skeleton.game_builder.offline_npc_contacts.v1",
   project_id:world.project_id,source_digest:world.source_digest,
   events:physicsEvents.map(pair=>pair.slice()),
   contacts:npcTalks.map(talk=>({...talk})),release_certified:false};
}
function walkReceipt(){
 return {schema:"skeleton.game_builder.offline_walk_events.v1",
   project_id:world.project_id,source_digest:world.source_digest,
   events:physicsEvents.map(pair=>pair.slice()),
   external_evidence_verified:false,
   native_genre_runtime_verified:false,release_certified:false};
}
function transcriptReceipt(){
 return {schema:"skeleton.game_builder.offline_story_choices.v1",
   project_id:world.project_id,source_digest:world.source_digest,
   choices:choices.map(pair=>pair.slice()),external_evidence_verified:false,
   native_genre_runtime_verified:false,release_certified:false};
}
function draw(){
 ctx.fillStyle="#101b29";ctx.fillRect(0,0,canvas.width,canvas.height);
 const stage=current();
 if(!stage){
   hud.textContent="All source-authored stages completed (sandbox only).";
   choicesEl.replaceChildren();historyEl.textContent=JSON.stringify(transcriptReceipt(),null,2);
 document.getElementById("walk-history").textContent=JSON.stringify(walkReceipt(),null,2);
 document.getElementById("npc-history").textContent=JSON.stringify(npcReceipt(),null,2);
   return;
 }
 const cells=world.maps[stageIndex];
 const hazardCells=new Set(world.hazards_by_stage[stageIndex].map(c=>c.join(",")));
 for(let y=0;y<world.height;y++){
   for(let x=0;x<world.width;x++){
     ctx.fillStyle=cells[y][x]==="#"?"#34495a":hazardCells.has(x+","+y)?
       "#ad4448":(x+y)%2?"#1e3949":"#244454";
     ctx.fillRect(x*40+1,y*40+1,38,38);
   }
 }
 for(const actor of world.actors){
   const [ax,ay]=actor.patrol_by_stage[stageIndex][steps%2];
   ctx.fillStyle="#9b8ee1";
   ctx.beginPath();ctx.arc(ax*40+20,ay*40+20,10,0,Math.PI*2);ctx.fill();
 }
 ctx.fillStyle="#ebc66f";
 ctx.fillRect(world.target[0]*40+9,world.target[1]*40+9,22,22);
 ctx.fillStyle="#62d7c1";
 ctx.beginPath();ctx.arc(player.x*40+20,player.y*40+20,13,0,Math.PI*2);ctx.fill();
 hud.textContent="Scene "+(stageIndex+1)+"/"+world.stages.length+
   ": "+stage.scene_id+". Objective: reach marker, choose an authored action.";
 stepsEl.textContent="Moves: "+steps+"; health: "+playerHealth+
   "; marker object: "+stage.objects[0];
 if(playerHealth<=0){
   hud.textContent="Character defeated by hazard contact. Restart to try again.";
   choicesEl.replaceChildren();
   historyEl.textContent=JSON.stringify(transcriptReceipt(),null,2);
   document.getElementById("walk-history").textContent=JSON.stringify(walkReceipt(),null,2);
 document.getElementById("npc-history").textContent=JSON.stringify(npcReceipt(),null,2);
   return;
 }
 choicesEl.replaceChildren();
 for(const actor of world.actors){
   const [ax,ay]=actor.patrol_by_stage[stageIndex][steps%2];
   if(Math.abs(ax-player.x)+Math.abs(ay-player.y)<=1){
     const talk=text("button","Talk to "+actor.name);
     talk.type="button";
     talk.addEventListener("click",()=>{
       npcTalks.push({id:actor.id,event_cursor:physicsEvents.length});
       document.getElementById("npc-dialogue").textContent=actor.name+
         " knows: "+actor.knows;
       document.getElementById("npc-history").textContent=
         JSON.stringify(npcReceipt(),null,2);
     });
     choicesEl.append(talk);
   }
 }
 if(nearMarker()){
   choicesEl.append(text("h2","Nearby object: "+stage.objects[0]));
   for(const choice of stage.alternatives){
     const button=text("button",choice);button.type="button";
     button.addEventListener("click",()=>choose(choice));choicesEl.append(button);
   }
 }
 historyEl.textContent=JSON.stringify(transcriptReceipt(),null,2);
 document.getElementById("walk-history").textContent=JSON.stringify(walkReceipt(),null,2);
 document.getElementById("npc-history").textContent=JSON.stringify(npcReceipt(),null,2);
}
function hint(){
 const stage=current();
 const output=document.getElementById("navigation-hint");
 if(!stage){output.textContent="All authored scenes completed";return;}
 const queue=[[player.x,player.y,[]]];
 const visited=new Set([player.x+","+player.y]);
 const moves=[["up",0,-1],["right",1,0],["down",0,1],["left",-1,0]];
 const rows=world.maps[stageIndex];
 for(let i=0;i<queue.length;i++){
   const [x,y,path]=queue[i];
   if(Math.abs(x-world.target[0])+Math.abs(y-world.target[1])<=1){
     output.textContent=path.length?
       "Shortest reachable route: "+path.length+" moves. Next: "+path[0]:
       "Marker is already within interaction distance";
     return;
   }
   for(const [name,dx,dy] of moves){
     const nx=x+dx,ny=y+dy;
     const key=nx+","+ny;
     if(nx>=0&&nx<world.width&&ny>=0&&ny<world.height&&
        rows[ny][nx]!=="#"&&!visited.has(key)){
       visited.add(key);queue.push([nx,ny,path.concat(name)]);
     }
   }
 }
 output.textContent="No navigable marker route from current position";
}
function move(dx,dy){
 if(!current()||playerHealth<=0)return;
 if(Math.abs(dx)+Math.abs(dy)!==1)return;
 const x=player.x+dx,y=player.y+dy;
 if(x<0||x>=world.width||y<0||y>=world.height)return;
 if(world.maps[stageIndex][y][x]==="#")return;
 const direction=dx===1?"right":dx===-1?"left":dy===1?"down":"up";
 physicsEvents.push(["move",direction]);
 player.x=x;player.y=y;steps++;
 if(world.hazards_by_stage[stageIndex].some(c=>c[0]===x&&c[1]===y)){
   playerHealth--;
 }
 draw();
 document.getElementById("navigation-hint").textContent="";
 document.getElementById("npc-dialogue").textContent="";
}
function choose(choice){
 const stage=current();
 if(!stage||playerHealth<=0||!nearMarker()||!stage.alternatives.includes(choice))return;
 choices.push([stage.id,choice]);
 physicsEvents.push(["choose",choice]);
 stageIndex++;player={x:1,y:1};draw();
 document.getElementById("navigation-hint").textContent="";
 document.getElementById("npc-dialogue").textContent="";
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
document.getElementById("hint").addEventListener("click",hint);
document.getElementById("restart").addEventListener("click",()=>{
 stageIndex=0;player={x:1,y:1};steps=0;playerHealth=world.starting_health;
 choices.length=0;physicsEvents.length=0;npcTalks.length=0;draw();
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


def _csp_hash(source: str) -> str:
    return "'sha256-"+b64encode(sha256(source.encode("utf-8")).digest()).decode("ascii")+"'"


def render_playable_world_html(documents: Mapping[str, Any]) -> bytes:
    from .studio_ecosystem_encounters import authored_hazards
    from .studio_ecosystem_npc_patrol import cast_patrols
    source=playable_world_source(documents)
    encounter=authored_hazards(documents)
    source["starting_health"]=encounter["starting_health"]
    source["hazards_by_stage"]=encounter["hazards_by_stage"]
    source["actors"]=cast_patrols(documents)["actors"]
    payload=json.dumps(source,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False)
    payload=payload.replace("<",r"\u003c").replace(">",r"\u003e").replace("&",r"\u0026")
    policy=("default-src 'none'; script-src "+_csp_hash(payload)+" "+
            _csp_hash(_SCRIPT)+"; style-src "+_csp_hash(_CSS)+
            "; base-uri 'none'; form-action 'none'; object-src 'none'")
    html=(
      "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<meta http-equiv='Content-Security-Policy' content=\""+policy+
      "\"><title>Original walkable studio</title>"
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
      "<p id='npc-dialogue' role='status' aria-live='polite'></p>"
      "<button id='hint' type='button'>Show shortest route hint</button>"
      "<p id='navigation-hint' role='status' aria-live='polite'></p>"
      "<button id='restart' type='button'>Restart</button>"
      "<h2>Sandbox decisions</h2><pre id='history'></pre>"
      "<h2>Collision-verified replay input</h2><pre id='walk-history'></pre>"
      "<h2>Verifiable local NPC dialogue contacts</h2><pre id='npc-history'></pre>"
      "<script type='application/json' id='world-source'>"+payload+"</script>"
      "<script>"+_SCRIPT+"</script></body></html>"
    )
    return html.encode("utf-8")
