"""Self-contained graphical game level studio built from a playable blueprint.

Users edit, preview, undo/redo, inspect route validity, load/export JSON and
download a complete standalone HTML build. No server or subscription required.
"""
from __future__ import annotations
import json
from html import escape

from .game_knowledge_design import GameBlueprint
from .game_playable_builder import build_playable_web_game

def generate_level_studio(blueprint:GameBlueprint, *,
                          game_html:str|None=None)->str:
    game=game_html or build_playable_web_game(blueprint).html
    initial=json.dumps({
        "grid":blueprint.grid,"title":blueprint.title,
        "width":blueprint.width,"height":blueprint.height,
    },ensure_ascii=True).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    template=json.dumps(game,ensure_ascii=True).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    page=r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Game Knowledge Studio</title>
<style>
:root{color-scheme:dark;font:16px system-ui}
*{box-sizing:border-box}body{margin:0;color:#ebf5ff;background:#101925}
header{padding:16px 24px;background:#1c293a;display:flex;flex-wrap:wrap;
align-items:center;gap:12px;border-bottom:1px solid #426080}
header h1{margin:0;font-size:20px;margin-right:auto}
button,select{background:#314c68;color:#fff;border:1px solid #789ac1;
padding:10px;border-radius:8px;font:inherit;cursor:pointer}
button:hover{background:#42698a}
button:focus-visible,select:focus-visible{outline:3px solid #e6cb71}
main{display:grid;grid-template-columns:minmax(320px,1fr) minmax(320px,1fr);
gap:14px;padding:14px}
article{background:#1b2a3c;border-radius:12px;padding:16px;min-width:0}
h2{margin-top:0;font-size:18px}
canvas{background:#0d1725;border:1px solid #6684a0;max-width:100%;
image-rendering:pixelated;touch-action:none}
iframe{width:100%;height:440px;border:1px solid #6684a0;border-radius:8px;background:#101827}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
#status{margin-top:9px;font-size:14px;min-height:22px;color:#b3dcff}
.info{font-size:14px;color:#b9c9d6;line-height:1.5}
@media(max-width:900px){main{grid-template-columns:1fr}}
</style></head><body>
<header><h1>Original Game Studio</h1>
<button id="undo">Undo</button><button id="redo">Redo</button>
<button id="preview">Play Preview</button><button id="save-html">Export Game HTML</button>
<button id="save-json">Export Map</button>
<button id="load-json">Import Map</button>
<input id="file" type="file" accept=".json,application/json" hidden>
</header><main>
<article><h2>Interactive Level Editor</h2>
<div class="toolbar"><label for="tool">Brush </label>
<select id="tool">
<option value="#">Solid Wall</option><option value=".">Open Space</option>
<option value="C">Collectible</option><option value="E">Enemy</option>
<option value="^">Hazard</option><option value="P">Player Start</option>
<option value="G">Goal</option>
</select>
<label for="mode">Mode </label><select id="mode">
<option value="paint">Paint</option><option value="fill">Flood Fill</option>
</select>
</div>
<canvas id="editor" aria-label="Editable game-level tile grid" tabindex="0"></canvas>
<div id="status" role="status" aria-live="polite"></div>
<p class="info">Select a brush, then click or drag to edit. Player and goal remain unique.
Every edit is checked against a route from spawn to exit. Keyboard: Ctrl+Z
undo, Ctrl+Y redo. Preview shows the exact edited level; export saves a
working standalone game. Imported map files are treated as data.</p>
</article>
<article><h2>Live Playable Preview</h2><iframe title="Original game preview" id="game" sandbox="allow-scripts"></iframe>
<p class="info">The preview is a real Canvas game: move A/D, jump Space,
attack J, dash Shift when enabled, restart R and pause P.</p></article>
</main>
<script>
"use strict";
const model=__INITIAL__;
const gameTemplate=__TEMPLATE__;
const canvas=document.getElementById("editor");
const ctx=canvas.getContext("2d");
const W=model.width,H=model.height,S=18;
canvas.width=W*S;canvas.height=H*S;
let grid=model.grid.map(x=>x.split(""));
let history=[snapshot()],cursor=0,dragging=false;
let lastGood="";
const colors={"#":"#506985",".":"#122438","P":"#70bbff",
 "G":"#83eab3","C":"#ffd46b","E":"#ef7988","^":"#c9546f"};
const message=(text,bad=false)=>{
  const el=document.getElementById("status");
  el.textContent=text;el.style.color=bad?"#ffc1c6":"#b3dcff";
};
function snapshot(){return grid.map(row=>row.join(""))}
function coordinates(event){
  const bounds=canvas.getBoundingClientRect();
  return [Math.floor((event.clientX-bounds.left)*W/bounds.width),
          Math.floor((event.clientY-bounds.top)*H/bounds.height)];
}
function find(symbol){
  for(let y=0;y<H;y++)for(let x=0;x<W;x++)if(grid[y][x]===symbol)return [x,y];
  return null;
}
function walkable(x,y){
  return x>=0&&x<W&&y>=0&&y<H&&grid[y][x]!=="#";
}
function routeLength(){
  const start=find("P"),end=find("G");
  if(!start||!end)return -1;
  const q=[[...start,0]],seen=new Set([start.join(",")]);
  for(let i=0;i<q.length&&q.length<=W*H;i++){
    const [x,y,d]=q[i];
    if(x===end[0]&&y===end[1])return d;
    for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){
      const xx=x+dx,yy=y+dy,k=xx+","+yy;
      if(walkable(xx,yy)&&!seen.has(k)){seen.add(k);q.push([xx,yy,d+1])}
    }
  }return -1;
}
function valid(){
  const text=snapshot().join("");
  return (text.match(/P/g)||[]).length===1 &&
    (text.match(/G/g)||[]).length===1 && routeLength()>=0;
}
function redraw(){
  for(let y=0;y<H;y++)for(let x=0;x<W;x++){
    const symbol=grid[y][x];
    ctx.fillStyle=colors[symbol]||"#f0f";ctx.fillRect(x*S,y*S,S-1,S-1);
    if(symbol==="^"){ctx.fillStyle="#fff";ctx.fillText("!",x*S+5,y*S+13)}
    if(symbol==="C"){ctx.fillStyle="#422f15";ctx.fillRect(x*S+7,y*S+7,5,5)}
  }
  message("Map: "+W+" × "+H+"  |  Route: "+routeLength()+" tiles  |  "
    +grid.flat().filter(x=>x==="C").length+" collectibles");
}
function commit(rows){
  const old=grid;grid=rows;
  if(!valid()){grid=old;message("Edit rejected: unreachable goal or missing start",true);return}
  const next=snapshot();if(next.join("")===old.map(r=>r.join("")).join(""))return;
  history=history.slice(0,cursor+1);
  history.push(next);if(history.length>200)history.shift();
  cursor=history.length-1;redraw();
}
function paint(x,y){
  if(x<0||x>=W||y<0||y>=H)return;
  const item=document.getElementById("tool").value;
  const rows=grid.map(row=>row.slice());
  const previous=rows[y][x];
  if(item==="P"||item==="G"){
    for(const row of rows)for(let i=0;i<row.length;i++)
      if(row[i]===item)row[i]=".";
  }else if(previous==="P"||previous==="G")return;
  if(document.getElementById("mode").value==="fill"&&item!=="P"&&item!=="G"){
    const source=rows[y][x],q=[[x,y]],seen=new Set();
    while(q.length){
      const [cx,cy]=q.pop(),key=cx+","+cy;
      if(seen.has(key)||cx<0||cy<0||cx>=W||cy>=H||rows[cy][cx]!==source)continue;
      seen.add(key);rows[cy][cx]=item;
      if(seen.size>W*H)return;
      for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]])
        q.push([cx+dx,cy+dy]);
    }
  }else rows[y][x]=item;
  commit(rows);
}
canvas.addEventListener("pointerdown",event=>{
  dragging=true;canvas.setPointerCapture(event.pointerId);
  paint(...coordinates(event));
});
canvas.addEventListener("pointermove",event=>{
  if(dragging&&document.getElementById("mode").value==="paint")
    paint(...coordinates(event));
});
["pointerup","pointercancel","lostpointercapture"].forEach(kind=>
  canvas.addEventListener(kind,()=>dragging=false));
function undo(){
  if(cursor>0){cursor--;grid=history[cursor].map(x=>x.split(""));redraw()}
}
function redo(){
  if(cursor+1<history.length){cursor++;grid=history[cursor].map(x=>x.split(""));redraw()}
}
document.getElementById("undo").onclick=undo;
document.getElementById("redo").onclick=redo;
document.addEventListener("keydown",event=>{
  if(event.ctrlKey&&event.code==="KeyZ"){event.preventDefault();undo()}
  if(event.ctrlKey&&event.code==="KeyY"){event.preventDefault();redo()}
});
function buildScene(){
  const entities=[],collision=[];
  const roles={P:"player",G:"goal",C:"collectible",E:"enemy",
               "^":"hazard"};
  for(let y=0;y<H;y++){
    const row=[];
    for(let x=0;x<W;x++){
      const marker=grid[y][x];row.push(Number(marker==="#"));
      if(roles[marker])entities.push({id:roles[marker]+"-"+x+"-"+y,
        type:roles[marker],x:x*32,y:y*32,width:32,height:32});
    }collision.push(row);
  }
  return {entities,collision,width:W,height:H};
}
function buildHtml(){
  const scene=buildScene();
  const regex=/const scene=\{[^\n]*\};/;
  const match=gameTemplate.match(regex);
  if(!match)throw Error("Missing game-scene injection point");
  // The fixed executable code is locally generated. Imported scene tiles
  // cannot inject script or alter the functions executing in the preview.
  const baseline=JSON.parse(match[0].slice("const scene=".length,-1));
  const payload=JSON.stringify({...baseline,...scene})
    .replace(/</g,"\\u003c").replace(/>/g,"\\u003e");
  return gameTemplate.replace(regex,"const scene="+payload+";");
}
function refreshPreview(){
  try{
    document.getElementById("game").srcdoc=buildHtml();
    message("Playable preview refreshed");
  }catch(err){message(err.message,true)}
}
document.getElementById("preview").onclick=refreshPreview;
function download(data,name,mime){
  const blob=new Blob([data],{type:mime});
  const url=URL.createObjectURL(blob);
  const link=document.createElement("a");link.href=url;link.download=name;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.getElementById("save-html").onclick=()=>{
  try{download(buildHtml(),"original-game.html","text/html;charset=utf-8")}
  catch(err){message(err.message,true)}
};
document.getElementById("save-json").onclick=()=>{
  download(JSON.stringify({schema:"skeleton.original.level_editor.v1",
    title:model.title,grid:snapshot()},null,2),"game-level.json","application/json");
};
document.getElementById("load-json").onclick=()=>document.getElementById("file").click();
document.getElementById("file").onchange=async event=>{
  const file=event.target.files?.[0];if(!file)return;
  if(file.size>1000000){message("File exceeds size limit",true);return}
  try{
    const content=JSON.parse(await file.text());
    if(content.schema!=="skeleton.original.level_editor.v1"||
      !Array.isArray(content.grid)||content.grid.length!==H||
      content.grid.some(row=>typeof row!=="string"||row.length!==W||
        /[^#.PCGE^]/.test(row)))throw Error("Invalid map format");
    commit(content.grid.map(row=>row.split("")));
  }catch(err){message("Map import rejected: "+err.message,true)}
};
redraw();
refreshPreview();
</script></body></html>'''
    return page.replace("__INITIAL__",initial).replace("__TEMPLATE__",template)
