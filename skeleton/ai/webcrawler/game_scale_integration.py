"""Integrate the 100-capability expansion into actual playable deliveries.

Exports use actual procedural sprite/SVG and synthesized WAV assets, provide
live event sounds and enriched game rendering, plus game balancing reports.
No third-party assets or downloaded executable code.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import json

from .game_knowledge_design import GameBlueprint
from .game_playable_builder import build_playable_web_game
from .game_scale_assets import (
    generate_game_palette,procedural_sprite,sprite_to_svg,
    synthesize_game_effect,compose_game_melody,render_game_melody,
)
from .game_scale_balancing import evaluate_game_balance,PlayBalance
from .game_scale_campaign import Campaign,export_campaign_archive
from .game_scale_studio import generate_level_studio
from .game_scale_live_systems import integrate_live_progression

@dataclass(frozen=True)
class EnhancedGame:
    html:str
    archive:bytes
    balancing:PlayBalance
    assets:tuple[str,...]
    fingerprint:str

_SPRITES=("hero","enemy","collectible","portal","chest","plant","rock")
_SOUNDS=("pickup","hit","jump","win","dash")

def _assets(seed:int,theme:str)->tuple[tuple[str,bytes],...]:
    colors=generate_game_palette(seed,theme=theme)
    items=[]
    for i,kind in enumerate(_SPRITES):
        sprite=procedural_sprite(seed+i*131,kind=kind,palette=colors)
        items.append((f"assets/{kind}.svg",sprite_to_svg(sprite).encode()))
    for kind in _SOUNDS:
        items.append((f"assets/{kind}.wav",synthesize_game_effect(kind)))
    notes=compose_game_melody(seed,bars=8)
    items.append(("assets/theme.wav",render_game_melody(notes)))
    return tuple(items)

def _enhance_html(html:str,assets:tuple[tuple[str,bytes],...])->str:
    # Web browser can open the zip-extracted index directly. Images are
    # optional and preserve original vector fallback for early render frames.
    setup=r"""
const art={};
for(const kind of ["hero","enemy","collectible","portal"]){
  const image=new Image();image.src="assets/"+kind+".svg";art[kind]=image;
}
const sounds={};
for(const kind of ["pickup","hit","jump","win","dash"]){
  const audio=new Audio("assets/"+kind+".wav");
  audio.preload="auto";sounds[kind]=audio;
}
function playAudio(kind){
  try{const sample=sounds[kind];if(!sample)return;
      const voice=sample.cloneNode();voice.volume=.35;
      const attempt=voice.play();if(attempt&&attempt.catch)attempt.catch(()=>{});
  }catch(_){}
}
function sprite(kind,x,y,w,h){
  const image=art[kind];
  if(image&&image.complete&&image.naturalWidth){
    ctx.drawImage(image,x,y,w,h);return true;
  }
  return false;
}
"""
    anchor="function draw(){"
    if anchor not in html:
        raise ValueError("missing Canvas runtime")
    html=html.replace(anchor,setup+anchor,1)
    substitutions=(
        ('ctx.fillStyle="#f8ca55";ctx.beginPath();',
         'if(sprite("collectible",item.x,item.y,20,20)) continue;\n    ctx.fillStyle="#f8ca55";ctx.beginPath();'),
        ('ctx.fillStyle="#e66d77";ctx.fillRect(e.x,e.y,e.w,e.h);',
         'if(sprite("enemy",e.x,e.y,e.w,e.h))continue;\n    ctx.fillStyle="#e66d77";ctx.fillRect(e.x,e.y,e.w,e.h);'),
        ('ctx.fillStyle="#7ce4b2";\n  ctx.fillRect(state.goal.x+9,state.goal.y+3,14,29);',
         'if(!sprite("portal",state.goal.x+2,state.goal.y+2,28,28)){\n'
         '  ctx.fillStyle="#7ce4b2";ctx.fillRect(state.goal.x+9,state.goal.y+3,14,29);\n  }'),
        ('ctx.fillStyle="#7cc5ff";\n    ctx.fillRect(state.player.x,state.player.y,state.player.w,state.player.h);',
         'if(!sprite("hero",state.player.x,state.player.y,state.player.w,state.player.h)){\n'
         '  ctx.fillStyle="#7cc5ff";ctx.fillRect(state.player.x,state.player.y,state.player.w,state.player.h);\n  }'),
        ('item.active=false;state.score+=10;', 'item.active=false;state.score+=10;playAudio("pickup");'),
        ('state.won=true;state.score+=250', 'state.won=true;state.score+=250;playAudio("win");'),
        ('p.vy=-scene.physics.jump_speed*TILE;', 'p.vy=-scene.physics.jump_speed*TILE;playAudio("jump");'),
        ('p.dashTimer=.14;p.dashCooldown=.7;', 'p.dashTimer=.14;p.dashCooldown=.7;playAudio("dash");'),
        ('e.active=false;state.score+=50;', 'e.active=false;state.score+=50;playAudio("hit");'),
    )
    for before,after in substitutions:
        if before not in html:raise ValueError("playable engine structure changed: "+before[:45])
        html=html.replace(before,after)
    return html

# Real enriched build: alternative to the baseline HTML5 ZIP.
def build_enhanced_game(blueprint:GameBlueprint, *,
                        theme:str="fantasy")->EnhancedGame:
    if blueprint.engine not in ("web","phaser"):
        raise ValueError("enriched Canvas build requires web target")
    underlying=build_playable_web_game(blueprint)
    assets=_assets(blueprint.seed,theme)
    html=integrate_live_progression(_enhance_html(underlying.html,assets))
    report=evaluate_game_balance(blueprint)
    studio=generate_level_studio(blueprint,game_html=html)
    html=html.replace(
        '<script>',
        '<p><a href="studio.html" style="color:#86d4ff">Open Level Editor</a></p><script>',
        1,
    )
    description={
        "title":blueprint.title,"source_evidence":blueprint.source_evidence,
        "balancing":{"route_tiles":report.route_tiles,
                     "estimated_seconds":report.estimated_seconds,
                     "predicted_deaths":report.predicted_deaths,
                     "collectibles":report.collectibles,
                     "recommendations":report.recommendations},
        "theme":theme,
        "schema":"skeleton.game.expanded_project.v1",
    }
    files=[
        ("index.html",html.encode()),
        ("studio.html",studio.encode()),
        ("scene.json",json.dumps(underlying.scene,sort_keys=True,indent=2).encode()),
        ("build-report.json",json.dumps(description,sort_keys=True,indent=2).encode()),
        ("README.md",(
            f"# {blueprint.title}\nOriginal 2D game with procedurally generated SVGs "
            "and synthesized WAV sounds.\n"
            "Unpack all files, then open index.html.\n"
            "A/D move, Space jump, Shift dash, J attack, P pause, R restart.\n"
            "Research source identifiers are in scene.json.\n"
        ).encode()),
        *assets,
    ]
    output=BytesIO()
    with ZipFile(output,"w",compression=ZIP_DEFLATED,compresslevel=9) as z:
        for name,payload in files:
            record=ZipInfo(name,date_time=(2026,1,1,0,0,0))
            record.compress_type=ZIP_DEFLATED
            record.external_attr=0o644<<16
            z.writestr(record,payload)
    data=output.getvalue()
    return EnhancedGame(html,data,report,tuple(n for n,_ in assets),
                        sha256(data).hexdigest())
