"""Self-contained offline HTML export for real generated game-builder worlds.

Everything in the interactive game is original template code and geometric
artwork. User-provided text is escaped, no external packages or assets load,
and executable JS is authorized by an exact-content CSP hash.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
import base64
import json
from pathlib import Path

from .contracts import canonical_digest
from .playable_world import PlayableWorld, PlayableWorldError
from .playable_simulation import demonstrate_solvable


class PlayableExportError(ValueError):
    """The game cannot be exported as an original, locally executable bundle."""


_CSS = r"""
:root{color-scheme:dark;font:16px/1.5 system-ui,-apple-system,sans-serif}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:#e9f5ee;background:#0d1c24}
a{color:#92eac7}
button{font:inherit;background:#193e4b;color:#f2fff7;border:1px solid #6fc9ab;
 border-radius:.6rem;padding:.6rem .9rem;cursor:pointer;min-height:44px}
button:hover{background:#24546a}button:focus-visible,summary:focus-visible{
 outline:3px solid #ffe19f;outline-offset:3px}
button:disabled{opacity:.45;cursor:not-allowed}
header{padding:1rem 1.3rem;border-bottom:1px solid #315363;background:#122b36}
h1{margin:0;font-size:clamp(1.4rem,4vw,2.2rem)}
p{margin:.4rem 0 1rem}
main{max-width:1050px;margin:0 auto;padding:1rem;display:grid;gap:1rem}
.surface{border:1px solid #315766;background:#132b36;border-radius:1rem;padding:1rem}
.hud{display:flex;gap:1rem;flex-wrap:wrap;justify-content:space-between;
 font-variant-numeric:tabular-nums}
.hud span{white-space:nowrap}
#screen{display:block;width:100%;height:auto;image-rendering:pixelated;
 background:#16303c;outline:1px solid #52887a;border-radius:.5rem}
#message{font-weight:650;color:#ffe1a2;min-height:1.7rem}
.controls{display:grid;grid-template-columns:repeat(3,minmax(68px,112px));
 grid-template-rows:repeat(2,48px);gap:.4rem;place-content:center}
.controls button[data-action=up]{grid-column:2;grid-row:1}
.controls button[data-action=left]{grid-column:1;grid-row:2}
.controls button[data-action=down]{grid-column:2;grid-row:2}
.controls button[data-action=right]{grid-column:3;grid-row:2}
.toolbar{display:flex;flex-wrap:wrap;gap:.6rem;justify-content:center;margin:1rem 0}
.details{display:grid;gap:.8rem}
details{border:1px solid #355a69;border-radius:.5rem;padding:.7rem}
summary{cursor:pointer;font-weight:650}
.citation{margin:.7rem 0;padding:.7rem;border-left:3px solid #6fc9ab;background:#193742}
.citation small{display:block;word-break:break-word;opacity:.85}
code,pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.35 ui-monospace,monospace}
pre{padding:.7rem;background:#0b1c24;border-radius:.5rem;max-height:300px;overflow:auto}
.tag{font-size:.8rem;border-radius:10rem;background:#2f5260;padding:.2rem .6rem}
.legend{display:flex;flex-wrap:wrap;gap:.75rem;color:#cce5db;font-size:.9rem}
.legend b{font-weight:650}
mark{background:#f3cf68;color:#123}
footer{padding:1.3rem;text-align:center;opacity:.8}
@media(min-width:850px){.play-area{display:grid;grid-template-columns:minmax(0,1fr) 165px;gap:1rem}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important}}
"""

_JS = r"""
"use strict";
const GAME = __SAFE_GAME_JSON__;
const root=document.getElementById("screen");
const ctx=root.getContext("2d",{alpha:false});
const message=document.getElementById("message");
const nodes={
 level:document.getElementById("level"),
 health:document.getElementById("health"),
 score:document.getElementById("score"),
 moves:document.getElementById("moves"),
 items:document.getElementById("items"),
 undo:document.getElementById("undo"),
 progress:document.getElementById("progress"),
};
const palettes={
 forest:{wall:"#285047",floor:"#183a35",border:"#5b967e",goal:"#e2ba57",item:"#9ef9d9",hazard:"#d96e76"},
 space:{wall:"#37426d",floor:"#141f41",border:"#788dd3",goal:"#f5be6b",item:"#8edffd",hazard:"#ec779d"},
 desert:{wall:"#806346",floor:"#463829",border:"#bd946a",goal:"#f6d477",item:"#bbf2bc",hazard:"#e88163"},
 ocean:{wall:"#32617a",floor:"#153448",border:"#7ab7cf",goal:"#f3d180",item:"#ace6ef",hazard:"#fa8495"},
 arcade:{wall:"#60407b",floor:"#241734",border:"#b07de5",goal:"#ffd361",item:"#8cffae",hazard:"#ff699e"}
};
const colors=palettes[GAME.intent.theme];
const keymap={
 ArrowUp:"up",KeyW:"up",ArrowLeft:"left",KeyA:"left",
 ArrowRight:"right",KeyD:"right",ArrowDown:"down",KeyS:"down",
};
const delta={up:[0,-1],left:[-1,0],right:[1,0],down:[0,1]};
const replay=[];
const undoStack=[];
let state;
let notice="";
function poskey(x,y){return x+","+y;}
function currentLevel(){return GAME.levels[state.level];}
function fresh(){
 const start=GAME.levels[0].start;
 return {level:0,x:start[0],y:start[1],collected:[],
  health:GAME.intent.starting_health,steps:0,score:0,status:"playing"};
}
function clone(s){return {...s,collected:s.collected.slice()};}
function emit(text){notice=text;message.textContent=text;}
function reset(){
 state=fresh();replay.length=0;undoStack.length=0;
 emit("Find all crystals, then reach the exit. Each move is one turn.");
 draw();
}
function takeTurn(direction){
 if(!Object.hasOwn(delta,direction)||state.status!=="playing")return;
 const lv=currentLevel();
 const [dx,dy]=delta[direction];
 let nx=state.x+dx,ny=state.y+dy;
 if(nx<0||ny<0||nx>=lv.width||ny>=lv.height
   ||lv.rows[ny][nx]==="#"){nx=state.x;ny=state.y;}
 const before=clone(state);
 undoStack.push(before);
 if(undoStack.length>256)undoStack.shift();
 const tile=lv.rows[ny][nx];
 const entered=nx!==state.x||ny!==state.y;
 state.x=nx;state.y=ny;state.steps++;
 if(tile==="C"&&!state.collected.includes(poskey(nx,ny))){
  state.collected.push(poskey(nx,ny));state.score+=10;
  emit("Crystal collected! "+state.collected.length+" of "+lv.collectibles.length);
 }else if(tile==="H"&&entered){
  state.health--;
  emit("Hazard encountered: 1 health lost.");
 }else if(tile==="#"){
  emit("A wall blocks that move.");
 }else{emit("Continue exploring.");}
 if(state.health<=0){
  state.health=0;state.status="lost";emit("Out of health. Undo or restart to try again.");
 }else if(tile==="G"&&state.collected.length===lv.collectibles.length){
  state.score+=100;
  if(state.level===GAME.levels.length-1){
   state.status="won";
   emit("All levels cleared! A complete original playable game.");
  }else{
   state.level++;
   const entry=currentLevel().start;
   state.x=entry[0];state.y=entry[1];state.collected=[];
   emit("Level complete! Welcome to level "+(state.level+1)+".");
  }
 }else if(tile==="G"){
  emit("Exit locked. Collect all the crystals first.");
 }
 replay.push(direction);
 draw();
}
function undo(){
 if(!undoStack.length)return;
 state=undoStack.pop();
 replay.pop();
 emit("Undid previous turn.");
 draw();
}
function downloadReplay(){
 const data={
  schema:"skeleton.game_builder.browser_actions.v1",
  world_digest:GAME.world_digest,
  project_id:GAME.intent.project_id,
  actions:replay.slice(),
  note:"Unverified client-side actions; replay via trusted Python engine.",
 };
 const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
 const url=URL.createObjectURL(blob);
 const link=document.createElement("a");
 link.href=url;link.download="game-play-replay.json";
 document.body.appendChild(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),0);
 emit("Downloaded local action trace (unverified until replayed).");
}
function drawTile(tile,x,y,size){
 const px=x*size,py=y*size;
 if(tile==="#"){
  ctx.fillStyle=colors.wall;ctx.fillRect(px,py,size,size);
  ctx.strokeStyle=colors.border;
  ctx.strokeRect(px+2,py+2,size-4,size-4);
  return;
 }
 ctx.fillStyle=colors.floor;
 ctx.fillRect(px,py,size,size);
 ctx.strokeStyle="#ffffff14";
 ctx.strokeRect(px+.5,py+.5,size-1,size-1);
 if(tile==="G"){
  const open=state.collected.length===currentLevel().collectibles.length;
  ctx.fillStyle=open?colors.goal:"#647781";
  ctx.fillRect(px+size*.2,py+size*.17,size*.6,size*.66);
  ctx.fillStyle=colors.floor;ctx.fillRect(px+size*.38,py+size*.35,size*.24,size*.30);
 }else if(tile==="C"&&!state.collected.includes(poskey(x,y))){
  ctx.fillStyle=colors.item;
  ctx.beginPath();
  ctx.moveTo(px+size/2,py+size*.15);
  ctx.lineTo(px+size*.78,py+size/2);
  ctx.lineTo(px+size/2,py+size*.86);
  ctx.lineTo(px+size*.22,py+size/2);
  ctx.closePath();ctx.fill();
 }else if(tile==="H"){
  ctx.fillStyle=colors.hazard;
  ctx.beginPath();ctx.moveTo(px+size/2,py+size*.16);
  ctx.lineTo(px+size*.85,py+size*.82);
  ctx.lineTo(px+size*.15,py+size*.82);ctx.closePath();ctx.fill();
  ctx.fillStyle=colors.floor;
  ctx.fillRect(px+size*.46,py+size*.40,size*.08,size*.19);
 }
}
function draw(){
 const lv=currentLevel();
 const size=24;
 root.width=lv.width*size;root.height=lv.height*size;
 for(let y=0;y<lv.height;y++)for(let x=0;x<lv.width;x++){
  drawTile(lv.rows[y][x],x,y,size);
 }
 const px=state.x*size,py=state.y*size;
 ctx.fillStyle="#ffffff";
 ctx.beginPath();ctx.arc(px+size/2,py+size/2,size*.37,0,Math.PI*2);ctx.fill();
 ctx.fillStyle="#112d39";
 ctx.fillRect(px+size*.55,py+size*.38,4,4);
 nodes.level.textContent=(state.level+1)+" / "+GAME.levels.length;
 nodes.health.textContent=state.health+" / "+GAME.intent.starting_health;
 nodes.score.textContent=state.score;
 nodes.moves.textContent=state.steps;
 nodes.items.textContent=state.collected.length+" / "+lv.collectibles.length;
 nodes.undo.disabled=!undoStack.length;
 nodes.progress.textContent=state.status==="won"?"Victory":state.status==="lost"?"Defeat":"Playing";
 root.setAttribute("aria-label",
  "Maze level "+(state.level+1)+". Player at column "+(state.x+1)+
  ", row "+(state.y+1)+". "+state.collected.length+" of "+
  lv.collectibles.length+" crystals collected. Status "+state.status+".");
 const printable=lv.rows.map((row,y)=>
  row.split("").map((ch,x)=>{
   if(x===state.x&&y===state.y)return "@";
   if(ch==="C"&&state.collected.includes(poskey(x,y)))return ".";
   return ch;
  }).join("")).join("\n");
 document.getElementById("text-map").textContent=printable;
}
document.addEventListener("keydown",event=>{
 if(event.altKey||event.ctrlKey||event.metaKey||event.repeat)return;
 if(["INPUT","TEXTAREA","SELECT"].includes(event.target.tagName))return;
 if(Object.hasOwn(keymap,event.code)){
  event.preventDefault();takeTurn(keymap[event.code]);return;
 }
 if(event.code==="KeyZ"){event.preventDefault();undo();}
 if(event.code==="KeyR"){event.preventDefault();reset();}
});
for(const button of document.querySelectorAll("[data-action]")){
 button.addEventListener("click",()=>takeTurn(button.dataset.action));
}
nodes.undo.addEventListener("click",undo);
document.getElementById("reset").addEventListener("click",reset);
document.getElementById("download").addEventListener("click",downloadReplay);
reset();
"""


def _safe_script_json(value: object) -> str:
    """JSON embedded in a script: no literal closing tags or JS line separators."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return (raw.replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("/", "\\u002f"))


def _sha256_csp(content: str) -> str:
    return "sha256-" + base64.b64encode(sha256(content.encode("utf-8")).digest()).decode("ascii")


@dataclass(frozen=True, slots=True)
class PlayableHTML:
    world_digest: str
    html: str
    html_sha256: str
    proof_digest: str
    research_packet_digest: str | None
    supported_features: tuple[str, ...]

    def to_manifest(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": "skeleton.game_builder.playable_html.v1",
            "world_digest": self.world_digest,
            "html_sha256": self.html_sha256,
            "proof_digest": self.proof_digest,
            "research_packet_digest": self.research_packet_digest,
            "supported_features": list(self.supported_features),
            "offline": True,
            "third_party_assets": False,
            "model_or_execution_authority": False,
        }
        return {**body, "manifest_digest": canonical_digest(body)}


def render_playable_world(
    world: PlayableWorld, *,
    research_packet: object = None,
    authorized: bool,
) -> PlayableHTML:
    if not authorized:
        raise PermissionError("original playable game export requires authorization")
    if not isinstance(world, PlayableWorld):
        raise PlayableExportError("typed PlayableWorld required")
    from .knowledge_rights_bridge import ClearedResearchPacket
    if research_packet is not None and (
        not isinstance(research_packet, ClearedResearchPacket)
        or research_packet.artifact_digest != world.digest
        or research_packet.project_id != world.intent.project_id
        or not research_packet.human_approved
    ):
        raise PlayableExportError("research packet does not bind this original game world")

    proof = demonstrate_solvable(world, authorized=True)
    levels = []
    for level in world.levels:
        levels.append({
            "width": level.width, "height": level.height,
            "rows": list(level.rows), "start": list(level.start),
            "exit": list(level.exit),
            "collectibles": [list(pos) for pos in level.collectibles],
        })
    game_data = {
        "schema": "skeleton.game_builder.browser_game.v1",
        "world_digest": world.digest, "intent": world.intent.to_payload(),
        "levels": levels,
    }
    script = _JS.replace("__SAFE_GAME_JSON__", _safe_script_json(game_data))
    script_csp = _sha256_csp(script)
    css_csp = _sha256_csp(_CSS)
    csp = (
        "default-src 'none'; "
        + "script-src '" + script_csp + "'; "
        + "style-src '" + css_csp + "'; "
        + "img-src 'none'; font-src 'none'; connect-src 'none'; "
        + "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
    )
    title = escape(world.intent.title, quote=True)
    subtitle = escape(world.intent.subtitle, quote=True)
    label = escape(world.intent.project_id, quote=True)
    research = ""
    packet_digest = None
    if research_packet is not None:
        packet_digest = research_packet.to_payload()["packet_digest"]
        findings = []
        for hit in research_packet.citations[:20]:
            statement = escape(hit.statement[:2048], quote=True)
            quote = escape(hit.exact_quote[:1000], quote=True)
            source = escape(hit.source_url[:2048], quote=True)
            mechanic = escape(hit.mechanic[:128], quote=True)
            findings.append(
                '<div class="citation"><strong>' + mechanic + '</strong>'
                + " — " + statement + "<small>Evidence excerpt: “" + quote
                + "”</small><small>Source: " + source + "</small></div>"
            )
        conflict_text = ", ".join(research_packet.conflicts) or "none recorded"
        research = (
            '<details><summary>Reviewed research context (not game instructions)</summary>'
            + "<p>Original gameplay implementation. Research is cited for ideas only. "
            + "Conflicting mechanics: " + escape(conflict_text, quote=True) + ".</p>"
            + "".join(findings)
            + "</details>"
        )
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
        '<title>' + title + ' — Playable project</title>'
        '<style>' + _CSS + '</style></head><body>'
        '<header><h1>' + title + '</h1><p>' + subtitle + '</p>'
        '<span class="tag">Original · Offline · ' + label + '</span></header>'
        '<main><section class="surface" aria-label="Game status">'
        '<div class="hud"><span>Level <b id="level">1</b></span>'
        '<span>Health <b id="health">3</b></span>'
        '<span>Crystals <b id="items">0</b></span>'
        '<span>Score <b id="score">0</b></span>'
        '<span>Moves <b id="moves">0</b></span>'
        '<span id="progress" role="status">Ready</span></div></section>'
        '<div class="play-area"><section class="surface" aria-label="Playable game">'
        '<canvas id="screen" width="456" height="360" role="img" '
        'aria-label="Original maze adventure game board"></canvas>'
        '<p id="message" aria-live="polite">Loading game…</p>'
        '<div class="legend"><span><b>◇</b> Crystal — collect</span>'
        '<span><b>▲</b> Hazard — avoid</span>'
        '<span><b>▣</b> Exit — opens after collection</span></div>'
        '</section><section class="surface"><h2>Move</h2>'
        '<div class="controls">'
        '<button data-action="up" aria-label="Move up">↑</button>'
        '<button data-action="left" aria-label="Move left">←</button>'
        '<button data-action="down" aria-label="Move down">↓</button>'
        '<button data-action="right" aria-label="Move right">→</button>'
        '</div><p>Arrows or WASD on keyboard. Moves happen one turn at a time.</p>'
        '</section></div>'
        '<section class="surface"><div class="toolbar">'
        '<button id="undo" type="button" aria-label="Undo last move">Undo (Z)</button>'
        '<button id="reset" type="button">Restart game (R)</button>'
        '<button id="download" type="button">Export my run</button></div>'
        '<div class="details">'
        '<details><summary>Accessible text map and legend</summary>'
        '<p>Each character is one tile: # wall, . floor, S entry, '
        'G exit, C crystal, H hazard, @ player. Use the buttons above to play.</p>'
        '<pre id="text-map" aria-live="off"></pre></details>'
        '<details><summary>Rules, safety and local replay</summary>'
        '<p>Collect every crystal and reach the exit. A hazard costs one health. '
        'Undo works for the latest 256 moves. A complete exit awards 100 points, '
        'each crystal awards 10. No adverts, telemetry, network dependencies '
        'or third-party game assets are included.</p>'
        '<p>Exported action logs are untrusted until the Python reference '
        'simulation validates them. The game does not train or update an AI.</p>'
        '</details>' + research + '</div></section></main>'
        '<footer>Generated by Skeleton Game Builder · Original geometric artwork</footer>'
        '<script>' + script + '</script></body></html>'
    )
    return PlayableHTML(
        world.digest, html, sha256(html.encode("utf-8")).hexdigest(),
        proof.digest, packet_digest,
        (
            "procedural_levels", "collected_objectives", "hazard_health",
            "locked_exits", "scoring", "replay_export", "undo",
            "keyboard_navigation", "touch_buttons", "accessible_text_map",
            "offline_csp", "source_citations",
        ),
    )


def write_playable_html(bundle: PlayableHTML, path: str | Path, *, authorized: bool) -> Path:
    if not authorized:
        raise PermissionError("file export requires authorization")
    if not isinstance(bundle, PlayableHTML):
        raise PlayableExportError("typed PlayableHTML required")
    target = Path(path)
    if target.is_symlink() or target.is_dir():
        raise PlayableExportError("file export target must not be symlink or directory")
    if sha256(bundle.html.encode("utf-8")).hexdigest() != bundle.html_sha256:
        raise PlayableExportError("HTML output digest mismatch")
    if len(bundle.html.encode("utf-8")) > 1_000_000:
        raise PlayableExportError("HTML bundle exceeds file size budget")
    if not target.parent.is_dir():
        raise PlayableExportError("export target parent does not exist")
    import os
    import tempfile
    fd, temporary = tempfile.mkstemp(
        prefix=".skeleton-game-", suffix=".tmp", dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(bundle.html.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        if os.name == "posix":
            dirfd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


__all__ = [
    "PlayableExportError", "PlayableHTML", "render_playable_world",
    "write_playable_html",
]
