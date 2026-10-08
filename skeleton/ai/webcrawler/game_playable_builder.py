"""Export playable original games from the game-knowledge design compiler.

The HTML5 build is a self-contained, fixed-timestep Canvas game with working
keyboard/touch controls, collision, jumps, adversaries, collectibles, goal,
pause/retry, camera and HUD. No external assets, CDN scripts or source code
from scraped documentation are copied into the output.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
import json
import re

from .game_knowledge_design import GameBlueprint, analyze_level_playability

_TILE=32


@dataclass(frozen=True)
class CompiledGame:
    html: str
    scene: dict[str,object]
    fingerprint: str


def _valid(blueprint: GameBlueprint) -> None:
    if not isinstance(blueprint,GameBlueprint):
        raise ValueError("GameBlueprint required")
    if not blueprint.grid or len(blueprint.grid)!=blueprint.height:
        raise ValueError("invalid game level grid")
    if any(len(row)!=blueprint.width for row in blueprint.grid):
        raise ValueError("inconsistent game map dimensions")
    if any(c not in "#.PCGE^" for row in blueprint.grid for c in row):
        raise ValueError("unsupported game tile")
    if sum(row.count("P") for row in blueprint.grid)!=1 or sum(
        row.count("G") for row in blueprint.grid)!=1:
        raise ValueError("game requires exactly one start and one goal")
    if not analyze_level_playability(blueprint).playable:
        raise ValueError("no route to goal")


# 31: Compile concrete scene instances from generator output.
def compile_scene_entities(blueprint: GameBlueprint) -> tuple[dict,...]:
    _valid(blueprint)
    roles={"P":"player","G":"goal","C":"collectible","E":"enemy",
           "^":"hazard"}
    result=[]
    for y,row in enumerate(blueprint.grid):
        for x,key in enumerate(row):
            if key in roles:
                result.append({
                    "id":f"{roles[key]}-{x}-{y}","type":roles[key],
                    "x":x*_TILE,"y":y*_TILE,
                    "width":_TILE,"height":_TILE,
                })
    return tuple(result)


# 32: Encode deterministic solid-tile collision layer.
def compile_tile_collision(blueprint: GameBlueprint) -> tuple[tuple[int,...],...]:
    _valid(blueprint)
    return tuple(tuple(1 if c=="#" else 0 for c in row)
                 for row in blueprint.grid)


# 33: Keyboard + pointer controller with jump edge buffering and pause.
def compile_input_controls_js() -> str:
    return r"""
const keys = new Set();
const touch = {left:false,right:false,jump:false};
const actionKeys = new Set(["Space","ArrowUp","ArrowDown","ArrowLeft","ArrowRight"]);
addEventListener("keydown", e => {
  if(actionKeys.has(e.code)) e.preventDefault();
  if(e.code==="KeyP" && !e.repeat) state.paused = !state.paused;
  if(e.code==="KeyR" && !e.repeat) restart();
  if(!e.repeat) keys.add(e.code);
});
addEventListener("keyup", e => keys.delete(e.code));
addEventListener("blur", () => {keys.clear(); Object.keys(touch).forEach(k=>touch[k]=false)});
document.querySelectorAll("[data-button]").forEach(node=>{
  const k=node.dataset.button;
  node.addEventListener("pointerdown",e=>{e.preventDefault();touch[k]=true;node.setPointerCapture(e.pointerId)});
  ["pointerup","pointercancel","lostpointercapture"].forEach(event=>
    node.addEventListener(event,e=>{e.preventDefault();touch[k]=false}));
});
const left = () => keys.has("ArrowLeft")||keys.has("KeyA")||touch.left;
const right = () => keys.has("ArrowRight")||keys.has("KeyD")||touch.right;
const jump = () => keys.has("Space")||keys.has("ArrowUp")||keys.has("KeyW")||touch.jump;
const attack = () => keys.has("KeyJ")||keys.has("KeyK");
const dash = () => keys.has("ShiftLeft")||keys.has("ShiftRight");
"""


# 34: Real fixed-step platformer physics with tile AABB collision.
def compile_physics_system_js() -> str:
    return r"""
const TILE=32;
function solid(tx,ty){
  if(tx<0||tx>=scene.width||ty<0) return true;
  if(ty>=scene.height) return true;
  return scene.collision[ty][tx]===1;
}
function intersects(a,b){
  return a.x<b.x+b.w && a.x+a.w>b.x && a.y<b.y+b.h && a.y+a.h>b.y;
}
function hitsSolid(o){
  const minX=Math.floor(o.x/TILE), maxX=Math.floor((o.x+o.w-.001)/TILE);
  const minY=Math.floor(o.y/TILE), maxY=Math.floor((o.y+o.h-.001)/TILE);
  for(let y=minY;y<=maxY;y++) for(let x=minX;x<=maxX;x++)
    if(solid(x,y)) return true;
  return false;
}
function moveAxis(body,axis,amount){
  // Move at <= one tile per substep: prevents tunnelling through thin platforms.
  const count=Math.max(1,Math.ceil(Math.abs(amount)/(TILE*.33)));
  const d=amount/count;
  for(let i=0;i<count;i++){
    body[axis]+=d;
    if(hitsSolid(body)){
      body[axis]-=d;
      if(axis==="y" && d>0) body.grounded=true;
      if(axis==="x") body.vx=0;
      else body.vy=0;
      break;
    }
  }
}
function physicsStep(dt){
  const p=state.player;
  if(!p.alive||state.won) return;
  const direction=Number(right())-Number(left());
  const desired=direction*scene.physics.move_speed*TILE;
  const accel=scene.physics.acceleration*TILE;
  const friction=scene.physics.friction*TILE;
  p.dashCooldown=Math.max(0,p.dashCooldown-dt);
  p.dashTimer=Math.max(0,p.dashTimer-dt);
  if(scene.mechanics.includes("dash")&&dash()&&!p.dashHeld&&
     direction&&p.dashCooldown===0){
    p.dashTimer=.14;p.dashCooldown=.7;
    p.vx=direction*scene.physics.move_speed*TILE*2.7;
  }
  p.dashHeld=dash();
  if(!p.dashTimer){
    if(desired) p.vx += Math.sign(desired-p.vx)*Math.min(Math.abs(desired-p.vx),accel*dt);
    else p.vx += -Math.sign(p.vx)*Math.min(Math.abs(p.vx),friction*dt);
  }
  if(jump()&&!p.jumpHeld) p.jumpBuffer=.12;
  p.jumpHeld=jump();
  p.jumpBuffer=Math.max(0,p.jumpBuffer-dt);
  p.coyote=p.grounded?.10:Math.max(0,p.coyote-dt);
  if(p.jumpBuffer>0&&(p.coyote>0 ||
      (scene.mechanics.includes("double_jump")&&p.airJumps>0))){
    if(p.coyote<=0) p.airJumps--;
    p.vy=-scene.physics.jump_speed*TILE;
    p.jumpBuffer=0;p.coyote=0;p.grounded=false;
  }
  p.vy=Math.min(18*TILE,p.vy+scene.physics.gravity*TILE*dt);
  moveAxis(p,"x",p.vx*dt);
  p.grounded=false;
  moveAxis(p,"y",p.vy*dt);
  if(p.grounded) p.airJumps=1;
  if(p.y>scene.height*TILE+TILE) loseLife();
  p.invincible=Math.max(0,p.invincible-dt);
}
"""


# 35: Deterministic enemy patrol AI and contact damage.
def compile_enemy_behaviors_js() -> str:
    return r"""
function updateEnemies(dt){
  state.attackCooldown=Math.max(0,state.attackCooldown-dt);
  if(attack()&&state.attackCooldown===0&&state.player.alive){
    state.attackCooldown=.28;
    const p=state.player;
    const facing=p.vx>=0?1:-1;
    const hit={
      x:facing>0?p.x+p.w:p.x-26,
      y:p.y+4,w:26,h:p.h-8
    };
    for(const e of state.enemies) if(e.active && intersects(e,hit)){
      e.active=false;state.score+=50;
    }
  }
  for(const e of state.enemies){
    if(!e.active) continue;
    const next=e.x+e.direction*scene.physics.enemy_speed*TILE*dt;
    const preview={x:next,y:e.y,w:e.w,h:e.h};
    const lookX=Math.floor((next+(e.direction>0?e.w:0))/TILE);
    const floorY=Math.floor((e.y+e.h+3)/TILE);
    if(hitsSolid(preview)||!solid(lookX,floorY)||
       Math.abs(next-e.home)>TILE*2){
      e.direction*=-1;
    }else e.x=next;
    if(state.player.alive&&intersects(e,state.player) &&
       state.player.invincible<=0){
      if(state.player.vy>0 &&
         state.player.y+state.player.h < e.y+e.h*.5){
        e.active=false; state.score+=100;
        state.player.vy=-scene.physics.jump_speed*TILE*.55;
      }else loseLife();
    }
  }
}
"""


# 36: Working pickups, score, checkpoints, goal and retry.
def compile_gameplay_system_js() -> str:
    return r"""
function restart(){
  const original=scene.entities.find(e=>e.type==="player");
  state.player={x:original.x+5,y:original.y+4,w:22,h:28,
                vx:0,vy:0,grounded:false,coyote:0,jumpBuffer:0,
                jumpHeld:false,airJumps:1,dashTimer:0,dashCooldown:0,
                dashHeld:false,invincible:1,alive:true};
  state.pickups=scene.entities.filter(e=>e.type==="collectible")
    .map(e=>({...e,w:20,h:20,x:e.x+6,y:e.y+6,active:true}));
  state.enemies=scene.entities.filter(e=>e.type==="enemy")
    .map(e=>({...e,x:e.x+4,y:e.y+6,w:24,h:26,
               home:e.x+4,direction:1,active:true}));
  state.goal=scene.entities.find(e=>e.type==="goal");
  state.hazards=scene.entities.filter(e=>e.type==="hazard");
  state.score=0;state.lives=scene.physics.max_lives|0;
  state.attackCooldown=0;
  state.won=false;state.paused=false;
}
function loseLife(){
  const p=state.player;
  if(!p.alive||p.invincible>0) return;
  state.lives--;
  if(state.lives<=0){p.alive=false;return}
  const start=scene.entities.find(e=>e.type==="player");
  p.x=start.x+5;p.y=start.y+4;
  p.vx=0;p.vy=0;p.invincible=1.5;
}
function updateGameState(){
  if(state.player.alive&&state.player.invincible<=0){
    for(const hazard of state.hazards){
      if(intersects(state.player,hazard)){loseLife();break}
    }
  }
  for(const item of state.pickups){
    if(item.active&&intersects(state.player,item)){
      item.active=false;state.score+=10;
    }
  }
  if(state.player.alive&&intersects(state.player,state.goal)){
    const locked=scene.genre==="puzzle" &&
      state.pickups.some(item=>item.active);
    if(!locked){state.won=true;state.score+=250}
  }
}
"""


# 37: Smooth bounded camera following player without showing outside world.
def compile_camera_system_js() -> str:
    return r"""
function updateCamera(dt){
  const targetX=state.player.x+state.player.w/2-canvas.width/2;
  const targetY=state.player.y+state.player.h/2-canvas.height/2;
  const maxX=Math.max(0,scene.width*TILE-canvas.width);
  const maxY=Math.max(0,scene.height*TILE-canvas.height);
  const x=Math.max(0,Math.min(maxX,targetX));
  const y=Math.max(0,Math.min(maxY,targetY));
  const lerp=1-Math.exp(-9*dt);
  camera.x+=(x-camera.x)*lerp;
  camera.y+=(y-camera.y)*lerp;
}
"""


# 38: Draw a complete original game on Canvas with HUD and win/loss overlays.
def compile_rendering_system_js() -> str:
    return r"""
function draw(){
  const W=canvas.width,H=canvas.height;
  ctx.fillStyle="#0b1423";ctx.fillRect(0,0,W,H);
  ctx.save();ctx.translate(-Math.round(camera.x),-Math.round(camera.y));
  const firstX=Math.max(0,Math.floor(camera.x/TILE));
  const lastX=Math.min(scene.width-1,Math.ceil((camera.x+W)/TILE));
  const firstY=Math.max(0,Math.floor(camera.y/TILE));
  const lastY=Math.min(scene.height-1,Math.ceil((camera.y+H)/TILE));
  for(let y=firstY;y<=lastY;y++) for(let x=firstX;x<=lastX;x++){
    if(scene.collision[y][x]){
      ctx.fillStyle="#344765";ctx.fillRect(x*TILE,y*TILE,TILE,TILE);
      ctx.fillStyle="#78b1c8";ctx.fillRect(x*TILE,y*TILE,TILE,4);
    }
  }
  for(const hazard of state.hazards){
    ctx.fillStyle="#ce6071";
    ctx.beginPath();ctx.moveTo(hazard.x,hazard.y+TILE);
    ctx.lineTo(hazard.x+TILE/2,hazard.y+TILE/5);
    ctx.lineTo(hazard.x+TILE,hazard.y+TILE);
    ctx.closePath();ctx.fill();
  }
  for(const item of state.pickups) if(item.active){
    ctx.fillStyle="#f8ca55";ctx.beginPath();
    ctx.arc(item.x+10,item.y+10,8,0,Math.PI*2);ctx.fill();
  }
  for(const e of state.enemies) if(e.active){
    ctx.fillStyle="#e66d77";ctx.fillRect(e.x,e.y,e.w,e.h);
    ctx.fillStyle="#fff";ctx.fillRect(e.x+5,e.y+7,4,4);
  }
  ctx.fillStyle="#7ce4b2";
  ctx.fillRect(state.goal.x+9,state.goal.y+3,14,29);
  if(state.player.alive &&
    (state.player.invincible<=0||Math.floor(state.player.invincible*9)%2===0)){
    ctx.fillStyle="#7cc5ff";
    ctx.fillRect(state.player.x,state.player.y,state.player.w,state.player.h);
    ctx.fillStyle="#10223a";
    ctx.fillRect(state.player.x+14,state.player.y+8,4,5);
  }
  ctx.restore();
  ctx.fillStyle="#e8f4ff";ctx.font="bold 18px system-ui";
  ctx.fillText("Score: "+state.score+"    Lives: "+state.lives,20,32);
  ctx.font="14px system-ui";
  ctx.fillText("A/D: move   Space: jump   Shift: dash   J: attack   P: pause   R: restart",20,54);
  if(scene.genre==="puzzle"){
    const remaining=state.pickups.filter(i=>i.active).length;
    ctx.fillText("Puzzle: collect all tokens to unlock the goal ("+remaining+" left)",20,76);
  }
  if(state.won||!state.player.alive||state.paused){
    ctx.fillStyle="rgba(4,12,25,.82)";
    ctx.fillRect(0,H/2-65,W,130);
    ctx.fillStyle="#f5fcff";ctx.textAlign="center";
    ctx.font="bold 34px system-ui";
    ctx.fillText(state.won?"Level Complete!":!state.player.alive?
                 "Game Over":"Paused",W/2,H/2);
    ctx.font="18px system-ui";ctx.fillText("Press R to retry",W/2,H/2+36);
    ctx.textAlign="left";
  }
}
"""


# 39: Assemble and lint a playable HTML5 game with no CDN dependencies.
def build_playable_web_game(blueprint: GameBlueprint) -> CompiledGame:
    _valid(blueprint)
    entities=compile_scene_entities(blueprint)
    scene={
        "schema":"skeleton.game.original_playable.v1",
        "title":blueprint.title,"genre":blueprint.genre,
        "mechanics":blueprint.mechanics,"width":blueprint.width,
        "height":blueprint.height,
        "entities":entities,"collision":compile_tile_collision(blueprint),
        "physics":blueprint.physics_dict(),"knowledge_refs":blueprint.source_evidence,
        "blueprint":blueprint.fingerprint,
    }
    payload=json.dumps(scene,separators=(",",":"),ensure_ascii=True).replace(
        "<","\\u003c"
    ).replace(">","\\u003e")
    pieces=[
        compile_input_controls_js(),compile_physics_system_js(),
        compile_enemy_behaviors_js(),compile_gameplay_system_js(),
        compile_camera_system_js(),compile_rendering_system_js(),
    ]
    runtime=r"""
const canvas=document.getElementById("game"),ctx=canvas.getContext("2d");
const state={paused:false,won:false};
const camera={x:0,y:0};
restart();
let accumulator=0,last=0;
function frame(timestamp){
  const elapsed=last?Math.min(.1,(timestamp-last)/1000):0;
  last=timestamp;
  if(!state.paused&&state.player.alive&&!state.won){
    accumulator=Math.min(.15,accumulator+elapsed);
    while(accumulator>=1/60){
      physicsStep(1/60);
      updateEnemies(1/60);
      updateGameState();
      accumulator-=1/60;
    }
  }
  updateCamera(Math.max(elapsed,1/60));
  draw();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
"""
    js="\nconst scene="+payload+";\n"+"\n".join(pieces)+runtime
    if "</script" in js.casefold():
        raise ValueError("unsafe generated game script")
    css="""*{box-sizing:border-box}body{margin:0;background:#101927;color:#ecf4ff;
font:16px system-ui;display:flex;flex-direction:column;align-items:center;
min-height:100vh;padding:18px}canvas{width:min(100%,960px);
border:2px solid #6686a8;aspect-ratio:16/9;image-rendering:pixelated}
.controls{display:flex;gap:16px;margin-top:20px}
button{border:0;border-radius:12px;padding:16px 23px;
font-size:20px;background:#365474;color:white;touch-action:none}
button:focus-visible{outline:3px solid #ffd373}
.note{opacity:.8;font-size:13px;margin:12px}"""
    html=(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>'+escape(blueprint.title)+'</title><style>'+css+'</style></head>'
        '<body><h1>'+escape(blueprint.title)+'</h1>'
        '<canvas id="game" width="960" height="540" role="img" '
        'aria-label="Original playable platform game"></canvas>'
        '<div class="controls"><button data-button="left" aria-label="Move left">◀</button>'
        '<button data-button="right" aria-label="Move right">▶</button>'
        '<button data-button="jump" aria-label="Jump">⤒</button></div>'
        '<p class="note">Keyboard or touch controls. Offline, original art.</p>'
        '<script>'+js+'</script></body></html>'
    )
    digest=sha256(html.encode()).hexdigest()
    return CompiledGame(html,scene,digest)


# 40: Export an actual portable game project archive (HTML + JSON + README).
def export_playable_game_archive(blueprint: GameBlueprint) -> bytes:
    built=build_playable_web_game(blueprint)
    serialized=json.dumps(
        built.scene,ensure_ascii=True,sort_keys=True,indent=2,
    ).encode("utf-8")
    readme=(
        f"# {blueprint.title}\n\n"
        "Open index.html in any modern browser, including offline.\n"
        "Move with A/D or arrow keys, jump with Space/W, pause P, restart R.\n"
        "The game is independently generated, with no copied external assets.\n"
        f"Blueprint: {blueprint.fingerprint}\n"
        f"Build SHA256: {built.fingerprint}\n"
        "Original source evidence IDs are in scene.json for audit.\n"
    ).encode("utf-8")
    buf=BytesIO()
    with ZipFile(buf,"w",compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in (
            ("index.html",built.html.encode("utf-8")),
            ("scene.json",serialized),("README.md",readme),
        ):
            info=ZipInfo(name,date_time=(2026,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED
            info.external_attr=0o644<<16
            archive.writestr(info,data)
    return buf.getvalue()
