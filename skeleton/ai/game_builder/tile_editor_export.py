"""Self-contained visual editor for original authored 2D playable game worlds.

Edits remain untrusted browser-local data until admitted by authored_tiles.py
and verified by the canonical Python game simulation. No network, filesystem
overwrite, source-code injection or automatic publication is authorized.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape

from .playable_export import _safe_script_json, _sha256_csp
from .playable_world import PlayableWorld

_CSS = r"""
:root{font:16px/1.45 system-ui,sans-serif;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#101d29;color:#eaf6f4}
header{background:#17313e;border-bottom:1px solid #466a71;padding:1rem 1.5rem}
h1{margin:.1rem 0;font-size:clamp(1.3rem,3.2vw,2rem)}
main{max-width:1250px;margin:auto;padding:1rem;display:grid;gap:1rem}
p{margin:.35rem 0 .8rem}
section{background:#142d39;border:1px solid #46606d;border-radius:.8rem;padding:1rem}
button{font:inherit;background:#205061;border:1px solid #84cbbb;color:#f4fffb;
border-radius:.5rem;padding:.45rem .7rem;cursor:pointer;min-height:42px}
button:focus-visible,canvas:focus-visible,textarea:focus-visible,select:focus-visible{
outline:3px solid #ffcd72;outline-offset:2px}
button[aria-pressed=true]{background:#92d6b6;color:#10242e;font-weight:700}
button:disabled{opacity:.45;cursor:not-allowed}
.toolbar{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}
label{font-weight:600}
select{background:#1b3b4d;color:white;font:inherit;border:1px solid #79b2ae;
border-radius:.5rem;padding:.5rem}
#board{width:100%;height:auto;max-height:67vh;object-fit:contain;display:block;
image-rendering:pixelated;touch-action:none;outline:1px solid #79b2ae;border-radius:.3rem;
background:#111e28;cursor:crosshair}
.palette{display:grid;grid-template-columns:repeat(auto-fit,minmax(115px,1fr));gap:.4rem}
.status{min-height:2rem;color:#ffe4a0;font-weight:600}
#map-text{font:14px/1.12 ui-monospace,SFMono-Regular,monospace;width:100%;
min-height:195px;background:#0b212c;color:#ddf1e6;padding:.7rem;white-space:pre;
border:1px solid #57777d;border-radius:.4rem}
.columns{display:grid;gap:1rem}
@media(min-width:930px){.columns{grid-template-columns:1fr 300px}}
.stats{font-variant-numeric:tabular-nums}
.small{color:#c4d6d8;font-size:.9rem}
kbd{border:1px solid #9cafb5;border-radius:.25rem;padding:0 .3rem}
"""
_JS = r"""
"use strict";
const DOCUMENT = __SAFE_EDITOR_JSON__;
const intent = DOCUMENT.intent;
const original = DOCUMENT.levels.map(level=>level.rows.slice());
let levels = original.map(rows=>rows.slice());
let current=0, brush="#", cursor=[1,1], undo=[], dirty=false, proof=[];
const canvas=document.getElementById("board"), ctx=canvas.getContext("2d");
const status=document.getElementById("status");
const textMap=document.getElementById("map-text");
const levelSelect=document.getElementById("level");
const stats=document.getElementById("stats");
const FILE_LIMIT=100000, MAX_UNDO=100;
const moves=[["up",0,-1],["left",-1,0],["right",1,0],["down",0,1]];
const paintColors={"#":"#406479",".":"#1d3948","S":"#f1dc82",
 "G":"#ecaa5f","C":"#78f0cf","H":"#ed7890"};
function announce(message){status.textContent=message;}
function key(x,y){return x+","+y;}
function map(){return levels[current];}
function pointOf(event){
 const box=canvas.getBoundingClientRect();
 const x=Math.floor((event.clientX-box.left)/box.width*intent.width);
 const y=Math.floor((event.clientY-box.top)/box.height*intent.height);
 return [Math.max(0,Math.min(intent.width-1,x)),
  Math.max(0,Math.min(intent.height-1,y))];
}
function snapshot(){
 undo.push(levels.map(rows=>rows.slice()));
 if(undo.length>MAX_UNDO)undo.shift();
}
function restore(){
 if(!undo.length)return;
 levels=undo.pop();
 dirty=true;announce("Undo applied.");render();
}
function apply(x,y,tile){
 if(!" #.SGCH".includes(tile)||tile===" ")return;
 if(x<=0||y<=0||x>=intent.width-1||y>=intent.height-1){
  announce("The sealed world boundary cannot be edited.");return;
 }
 const rows=map();
 if(rows[y][x]===tile)return;
 const markerCount=rows.join("").split(tile).length-1;
 if(tile==="C"&&markerCount>=intent.collectibles_per_level){
  announce("Collectible budget reached. Remove a crystal first.");return;
 }
 if(tile==="H"&&markerCount>=intent.hazards_per_level){
  announce("Hazard budget reached. Remove a hazard first.");return;
 }
 snapshot();
 if(tile==="S"||tile==="G"){
  const old=rows.findIndex(r=>r.includes(tile));
  if(old>=0){
   const xx=rows[old].indexOf(tile);
   rows[old]=rows[old].slice(0,xx)+"."+rows[old].slice(xx+1);
  }
 }
 rows[y]=rows[y].slice(0,x)+tile+rows[y].slice(x+1);
 dirty=true;proof=[];cursor=[x,y];announce("Changed cell "+(x+1)+","+(y+1)+".");
 render();
}
function draw(){
 const w=intent.width,h=intent.height,size=28;
 canvas.width=w*size;canvas.height=h*size;
 const rows=map();
 for(let y=0;y<h;y++){
  for(let x=0;x<w;x++){
   const cell=rows[y][x];
   ctx.fillStyle=paintColors[cell]||"#111";
   ctx.fillRect(x*size,y*size,size,size);
   ctx.strokeStyle="#b8d9e53b";ctx.strokeRect(x*size+.5,y*size+.5,size-1,size-1);
   if(cell==="S"||cell==="G"||cell==="C"||cell==="H"){
    ctx.fillStyle=cell==="C"||cell==="H"?"#102c38":"#1c2c3b";
    ctx.font="bold 19px system-ui";ctx.textAlign="center";ctx.textBaseline="middle";
    ctx.fillText(cell,x*size+size/2,y*size+size/2);
   }
  }
 }
 if(proof.length){
  ctx.fillStyle="#b4ffd94d";
  for(const [x,y] of proof)ctx.fillRect(x*size+7,y*size+7,size-14,size-14);
 }
 ctx.strokeStyle="#ffffff";ctx.lineWidth=2;
 ctx.strokeRect(cursor[0]*size+2,cursor[1]*size+2,size-4,size-4);
}
function statsFor(rows){
 const text=rows.join("");
 const count=t=>text.split(t).length-1;
 return {starts:count("S"),exits:count("G"),items:count("C"),hazards:count("H")};
}
function validate(rows){
 if(!Array.isArray(rows)||rows.length!==intent.height)return "Level height mismatch";
 if(rows.some(row=>typeof row!=="string"||row.length!==intent.width||
   /[^#.SGCH]/.test(row)))return "Invalid tiles or row lengths";
 if(rows[0]!=="#".repeat(intent.width)||
    rows[rows.length-1]!=="#".repeat(intent.width)||
    rows.some(row=>row[0]!=="#"||row[row.length-1]!=="#"))
    return "All outside borders must remain walls";
 const s=statsFor(rows);
 if(s.starts!==1||s.exits!==1)return "Exactly one spawn and one exit required";
 if(s.items!==intent.collectibles_per_level)return "Crystal count must match intent";
 if(s.hazards>intent.hazards_per_level)return "Too many hazards";
 return "";
}
function bfs(rows,visual){
 const bad=validate(rows);if(bad)return {error:bad,path:[]};
 const items=[],h=rows.length,w=rows[0].length;
 let start=[],goal=[];
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){
  const t=rows[y][x];
  if(t==="S")start=[x,y];
  if(t==="G")goal=[x,y];
  if(t==="C")items.push([x,y]);
 }
 const bits=new Map(items.map((p,i)=>[key(...p),1<<i]));
 const mask=(1<<items.length)-1;
 const root=[start[0],start[1],0];
 const packed=(x,y,m)=>m*w*h+y*w+x;
 const visited=new Set([packed(...root)]);
 const nodes=[{x:root[0],y:root[1],m:0,parent:-1}];
 let end=-1;
 // Bounded by the canonical small-grid and collectible bitset maxima.
 for(let front=0;front<nodes.length;front++){
  const n=nodes[front];
  if(n.x===goal[0]&&n.y===goal[1]&&n.m===mask){end=front;break;}
  for(const [,dx,dy] of moves){
   const x=n.x+dx,y=n.y+dy;
   if(x<0||y<0||x>=w||y>=h||"#H".includes(rows[y][x]))continue;
   const m=n.m|(bits.get(key(x,y))||0), k=packed(x,y,m);
   if(visited.has(k))continue;
   visited.add(k);nodes.push({x,y,m,parent:front});
  }
  if(nodes.length>41*41*64)return {error:"Solver state budget exceeded",path:[]};
 }
 if(end<0)return {error:"No hazard-free route visiting every crystal and exit",path:[]};
 const points=[];let index=end;
 while(index!==-1){const n=nodes[index];points.push([n.x,n.y]);index=n.parent;}
 points.reverse();
 if(visual)proof=points;
 return {error:"",path:points};
}
function checkAll(){
 for(let i=0;i<levels.length;i++){
  const answer=bfs(levels[i],false);
  if(answer.error)return {error:"Level "+(i+1)+": "+answer.error,total:0};
 }
 return {error:"",total:levels.length};
}
function render(){
 levelSelect.value=String(current);
 document.querySelectorAll("[data-tile]").forEach(b=>{
  b.setAttribute("aria-pressed",String(b.dataset.tile===brush));
 });
 const s=statsFor(map());
 stats.textContent="Crystals "+s.items+"/"+intent.collectibles_per_level+
  " · Hazards "+s.hazards+"/"+intent.hazards_per_level+
  " · Start "+s.starts+" · Exit "+s.exits+
  " · Unsaved edits "+(dirty?"yes":"no");
 textMap.value=map().join("\n");draw();
}
function verifyCurrent(){
 proof=[];
 const answer=bfs(map(),true);
 announce(answer.error?"Invalid: "+answer.error:
  "Locally solvable: "+(answer.path.length-1)+" safe turns. Python still verifies on import.");
 render();
}
function uploadText(){
 const lines=textMap.value.trim().split(/\r?\n/);
 if(lines.length!==intent.height||
    lines.some(l=>l.length!==intent.width)){
  announce("Text map does not match declared dimensions.");return;
 }
 const error=validate(lines);
 if(error){announce(error);return;}
 snapshot();levels[current]=lines;proof=[];dirty=true;
 announce("Text edits applied. Revalidate before publishing.");render();
}
function download(){
 const valid=checkAll();
 if(valid.error){announce(valid.error+" — export blocked.");return;}
 const source={schema:"skeleton.game_builder.authored_tiles.v1",
  intent,levels:levels.map(rows=>rows.slice())};
 const raw=JSON.stringify(source,null,2);
 if(new TextEncoder().encode(raw).byteLength>FILE_LIMIT){
  announce("Authored document is too large to export.");return;
 }
 const url=URL.createObjectURL(new Blob([raw],{type:"application/json"}));
 const link=document.createElement("a");
 link.href=url;link.download=intent.project_id+"-authored.json";
 document.body.append(link);link.click();link.remove();
 URL.revokeObjectURL(url);announce("Exported reviewed-design candidate. Import with Python for canonical proof.");
}
async function importFile(file){
 if(!file||file.size>FILE_LIMIT){announce("Import missing or exceeds 100 KB.");return;}
 let data;
 try{data=JSON.parse(await file.text());}
 catch{announce("Invalid JSON file.");return;}
 if(!data||typeof data!=="object"||Array.isArray(data)||
    Object.keys(data).sort().join()!=="intent,levels,schema"||
    data.schema!=="skeleton.game_builder.authored_tiles.v1"||
    JSON.stringify(data.intent)!==JSON.stringify(intent)||
    !Array.isArray(data.levels)||data.levels.length!==intent.levels){
    announce("Import schema or project identity mismatch.");return;
 }
 for(let i=0;i<data.levels.length;i++){
  const error=validate(data.levels[i]);
  if(error){announce("Rejected level "+(i+1)+": "+error);return;}
 }
 snapshot();levels=data.levels.map(rows=>rows.slice());dirty=true;proof=[];
 announce("Authored map imported. Verify every level.");render();
}
for(let i=0;i<intent.levels;i++){
 const option=document.createElement("option");
 option.value=String(i);option.textContent="Level "+(i+1);
 levelSelect.append(option);
}
levelSelect.addEventListener("change",()=>{
 current=Number(levelSelect.value);proof=[];render();
});
canvas.addEventListener("pointerdown",event=>{
 if(event.button!==0)return;
 const [x,y]=pointOf(event);apply(x,y,brush);canvas.focus();
});
canvas.addEventListener("keydown",event=>{
 const arrows={ArrowUp:[0,-1],ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowDown:[0,1]};
 if(Object.hasOwn(arrows,event.key)){
  event.preventDefault();const [x,y]=arrows[event.key];
  cursor=[Math.max(0,Math.min(intent.width-1,cursor[0]+x)),
          Math.max(0,Math.min(intent.height-1,cursor[1]+y))];draw();
 }else if(event.key==="Enter"||event.key===" "){
  event.preventDefault();apply(cursor[0],cursor[1],brush);
 }
});
document.querySelectorAll("[data-tile]").forEach(button=>{
 button.addEventListener("click",()=>{brush=button.dataset.tile;render();});
});
document.getElementById("undo").addEventListener("click",restore);
document.getElementById("verify").addEventListener("click",verifyCurrent);
document.getElementById("apply-text").addEventListener("click",uploadText);
document.getElementById("export").addEventListener("click",download);
document.getElementById("import").addEventListener("change",event=>{
 importFile(event.target.files[0]);event.target.value="";
});
document.getElementById("reset").addEventListener("click",()=>{
 if(!confirm("Reset every level back to its original generated layout?"))return;
 snapshot();levels=original.map(rows=>rows.slice());proof=[];dirty=true;current=0;
 announce("Original generated layouts restored.");render();
});
window.addEventListener("beforeunload",event=>{
 if(dirty){event.preventDefault();event.returnValue="";}
});
announce("Edit geometric worlds locally. Export for trusted Python validation.");
render();
"""

@dataclass(frozen=True, slots=True)
class TileEditorHTML:
    content: bytes
    source_sha256: str


def render_tile_editor(world: PlayableWorld, *, authorized: bool) -> TileEditorHTML:
    if not authorized:
        raise PermissionError("offline game editor rendering requires authorization")
    if not isinstance(world, PlayableWorld):
        raise TypeError("typed playable world required")
    game = {
        "intent": world.intent.to_payload(),
        "levels": [{"rows": list(level.rows)} for level in world.levels],
    }
    js = _JS.replace("__SAFE_EDITOR_JSON__", _safe_script_json(game))
    csp = (
        "default-src 'none'; script-src '" + _sha256_csp(js)
        + "'; style-src '" + _sha256_csp(_CSS)
        + "'; img-src 'none'; font-src 'none'; connect-src 'none'; "
        + "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
    )
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="'
        + escape(csp, quote=True) + '">'
        '<title>' + escape(world.intent.title, quote=True)
        + ' — Original game editor</title><style>' + _CSS + '</style></head><body>'
        '<header><h1>' + escape(world.intent.title)
        + ' — Original level editor</h1>'
        '<p>Private, offline, geometry-only creation. No source scripts or external assets.</p>'
        '</header><main><section><div class="toolbar">'
        '<label for="level">Active level</label><select id="level"></select>'
        '<button id="undo" type="button">Undo change</button>'
        '<button id="reset" type="button">Reset to generated world</button>'
        '<button id="verify" type="button">Show safe route</button>'
        '<button id="export" type="button">Export authored JSON</button>'
        '<label for="import">Import authored JSON</label>'
        '<input id="import" type="file" accept=".json,application/json">'
        '</div><p id="status" class="status" role="status" aria-live="polite"></p>'
        '<div class="columns"><div>'
        '<canvas id="board" tabindex="0" role="img" aria-label="Editable geometric tile map.'
        ' Use arrows to focus a cell and Enter to paint with the selected brush."></canvas>'
        '<p id="stats" class="stats"></p>'
        '</div><div><h2>Paint tiles</h2><div class="palette">'
        + "".join(
            '<button type="button" data-tile="' + escape(tile, quote=True)
            + '" aria-pressed="false">' + escape(label) + '</button>'
            for tile, label in (
                ("#", "Wall"), (".", "Floor"), ("S", "Spawn"),
                ("G", "Exit"), ("C", "Crystal"), ("H", "Hazard")
            )
        )
        + '</div><p class="small">Click/tap a square, or focus the canvas,'
        ' navigate with arrows and paint with Enter. Draw a new original game'
        ' level with exactly one spawn, one exit and the required collectibles.</p>'
        '<label for="map-text">Accessible text-grid editor</label>'
        '<textarea id="map-text" spellcheck="false" aria-label="Grid rows"></textarea>'
        '<button id="apply-text" type="button">Apply text grid</button>'
        '</div></div></section><section><h2>Production handoff</h2>'
        '<p>Offline safe-route previews are advisory. The Python game builder'
        ' independently validates exact tile geometry, rights and gameplay'
        ' before generating verified HTML and Godot source projects.</p>'
        '<p>Run the documented dual_runtime_cli with --authored-world,'
        ' --human-reviewed, and external operator authorization.'
        ' Save your edited JSON before closing this tab.</p>'
        '</section></main><script>' + js + '</script></body></html>'
    )
    data = html.encode("utf-8")
    if len(data) > 500_000:
        raise ValueError("offline editor exceeds 500 KB source limit")
    return TileEditorHTML(data, sha256(data).hexdigest())


__all__ = ["TileEditorHTML", "render_tile_editor"]
