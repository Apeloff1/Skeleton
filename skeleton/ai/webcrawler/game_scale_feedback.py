"""Play-session evidence drives actual game balancing and next-build tuning.

Event traces are bounded, local, source-independent player observations.
They do not claim to be random player samples, imply personal consent, or
automatically promote knowledge into the LLM. Export is user-initiated.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from hashlib import sha256
from collections import Counter
from math import isfinite
import json

from .game_knowledge_design import GameBlueprint,find_level_route

_ALLOWED={"spawn","move","jump","dash","collect","attack","damage",
          "death","checkpoint","victory","retry","pause","elapsed"}

@dataclass(frozen=True)
class GameplayEvent:
    event:str
    second:float
    x:float
    y:float
    value:float=0.

@dataclass(frozen=True)
class SessionFeedback:
    blueprint:str
    total_seconds:float
    victories:int
    deaths:int
    pickups:int
    retries:int
    movement_samples:int
    completion_rate:float
    death_hotspots:tuple[tuple[int,int,int],...]
    fingerprint:str

@dataclass(frozen=True)
class PlayerTuning:
    level_fingerprint:str
    new_blueprint:GameBlueprint
    old_speed:float
    new_speed:float
    old_gravity:float
    new_gravity:float
    changes:tuple[str,...]


def _finite(value:object)->bool:
    return isinstance(value,(int,float)) and not isinstance(value,bool) and isfinite(value)


def decode_play_sessions(payload:bytes | str, *,
                         max_bytes:int=3_000_000,
                         max_events:int=20000
                         )->tuple[str,tuple[GameplayEvent,...]]:
    if isinstance(payload,bytes):
        if len(payload)>max_bytes:raise ValueError("oversized play-session log")
        payload=payload.decode("utf-8")
    if not isinstance(payload,str) or len(payload.encode("utf-8"))>max_bytes:
        raise ValueError("oversized play-session log")
    data=json.loads(payload)
    if not isinstance(data,dict) or data.get("schema")!="skeleton.original_game.telemetry.v1":
        raise ValueError("invalid gameplay telemetry schema")
    source=data.get("blueprint")
    if not isinstance(source,str) or len(source)!=64 or any(
        c not in "0123456789abcdef" for c in source
    ):
        raise ValueError("invalid gameplay source fingerprint")
    raw=data.get("events")
    if not isinstance(raw,list) or len(raw)>max_events:
        raise ValueError("excessive play-session events")
    results=[]
    last=-1.
    for record in raw:
        if not isinstance(record,dict) or record.get("event") not in _ALLOWED:
            raise ValueError("unsupported gameplay observation")
        numbers=[record.get("second"),record.get("x"),record.get("y"),
                 record.get("value",0)]
        if not all(_finite(n) for n in numbers):
            raise ValueError("invalid gameplay measurement")
        elapsed,x,y,value=map(float,numbers)
        if not 0<=elapsed<=604800 or elapsed<last or max(abs(x),abs(y),abs(value))>1e7:
            raise ValueError("out-of-order or unbounded gameplay measurement")
        results.append(GameplayEvent(record["event"],elapsed,x,y,value))
        last=elapsed
    return source,tuple(results)


def analyze_player_feedback(
    source:str,events:tuple[GameplayEvent,...], *,
    tile_size:int=32,max_hotspots:int=15
) -> SessionFeedback:
    if not 8<=tile_size<=256 or not 1<=max_hotspots<=100:
        raise ValueError("invalid analytics geometry")
    counts=Counter(e.event for e in events)
    deaths=Counter((int(e.x//tile_size),int(e.y//tile_size))
                   for e in events if e.event in ("death","damage"))
    hotspots=tuple((x,y,n) for (x,y),n in
                   sorted(deaths.items(),key=lambda p:(-p[1],p[0]))[:max_hotspots])
    attempts=max(1,counts["spawn"]+counts["retry"])
    wins=counts["victory"]
    digest=sha256(json.dumps([
        source,[(e.event,e.second,e.x,e.y,e.value) for e in events],
    ],ensure_ascii=True,separators=(",",":")).encode()).hexdigest()
    return SessionFeedback(
        source,events[-1].second if events else 0.,wins,
        counts["death"]+counts["damage"],counts["collect"],
        counts["retry"],counts["move"],round(min(1,wins/attempts),5),
        hotspots,digest,
    )


def tune_game_from_feedback(
    blueprint:GameBlueprint,feedback:SessionFeedback, *,
    expected_success:float=.65,max_adjustment:float=.15,
) -> PlayerTuning:
    """Apply bounded improvements to next build based on observed difficulty.

    The function never rewrites a played game in place. It creates a new
    blueprint fingerprint and preserves original source-evidence custody.
    """
    if blueprint.fingerprint!=feedback.blueprint:
        raise ValueError("feedback does not belong to the referenced game")
    if not 0<expected_success<1 or not 0<max_adjustment<=.25:
        raise ValueError("invalid adaptation policy")
    original=blueprint.physics_dict()
    speed=float(original["move_speed"])
    gravity=float(original["gravity"])
    changes=[]
    trials=feedback.victories+feedback.deaths+feedback.retries
    if trials>=3:
        error=expected_success-feedback.completion_rate
        delta=max(-max_adjustment,min(max_adjustment,error*.18))
        if abs(delta)>.0001:
            original["move_speed"]=round(max(1.5,min(15.,speed*(1+delta))),4)
            original["gravity"]=round(max(10.,min(40.,gravity*(1-delta*.6))),4)
            changes.append("adaptive_movement_and_jump_margin")
    if feedback.death_hotspots:
        changes.append("review_collision_hotspots")
    modified=tuple(sorted(original.items()))
    fingerprint=sha256(json.dumps({
        "schema":"skeleton.original_game.feedback_tuned.v1",
        "base":blueprint.fingerprint,"feedback":feedback.fingerprint,
        "physics":modified,"changes":changes,
    },sort_keys=True,separators=(",",":")).encode()).hexdigest()
    updated=replace(blueprint,physics=modified,fingerprint=fingerprint)
    return PlayerTuning(
        blueprint.fingerprint,updated,speed,original["move_speed"],
        gravity,original["gravity"],tuple(changes),
    )


def instrument_playable_telemetry(game_html:str,blueprint:GameBlueprint
                                  )->str:
    """Insert local telemetry recording into an actual compiled Canvas game."""
    if not isinstance(game_html,str):
        raise ValueError("game HTML required")
    anchors=[
        "const state={paused:false,won:false};",
        "function physicsStep(dt){",
        "function restart(){",
        "function loseLife(){",
        "function updateGameState(){",
        "requestAnimationFrame(frame);",
    ]
    if any(a not in game_html for a in anchors):
        raise ValueError("unrecognized game engine telemetry hooks")
    setup=r"""
const gameTelemetry={schema:"skeleton.original_game.telemetry.v1",
  blueprint:__BLUEPRINT__,events:[]};
let gameTelemetryTime=0,gameTelemetryAccumulator=0;
const _gameTelemetryPush=(event,value=0)=>{
 if(gameTelemetry.events.length>=15000)return;
 const p=state.player||{x:0,y:0};
 gameTelemetry.events.push({
   event,second:Math.round(gameTelemetryTime*100)/100,
   x:Math.round(p.x*10)/10,y:Math.round(p.y*10)/10,value
 });
};
function exportGameTelemetry(){
 const data=new Blob([JSON.stringify(gameTelemetry,null,2)],{
   type:"application/json"});
 const ref=URL.createObjectURL(data),link=document.createElement("a");
 link.href=ref;link.download="gameplay-feedback.json";link.click();
 setTimeout(()=>URL.revokeObjectURL(ref),1000);
}
document.addEventListener("keydown",event=>{
 if(event.code==="KeyT"&&!event.repeat)exportGameTelemetry();
});
"""
    js=(setup.replace("__BLUEPRINT__",json.dumps(blueprint.fingerprint)))
    game_html=game_html.replace(
        "const state={paused:false,won:false};",
        "const state={paused:false,won:false};"+js,1
    )
    game_html=game_html.replace(
        "function physicsStep(dt){",
        """function physicsStep(dt){
  gameTelemetryTime+=dt;
  gameTelemetryAccumulator+=dt;
  if(gameTelemetryAccumulator>=.5){
    gameTelemetryAccumulator=0;_gameTelemetryPush("move");
  }""",1
    )
    game_html=game_html.replace(
        "function restart(){",
        'function restart(){_gameTelemetryPush("retry");',1
    )
    game_html=game_html.replace(
        "function loseLife(){",
        'function loseLife(){_gameTelemetryPush("damage");',1
    )
    game_html=game_html.replace(
        'state.won=true;state.score+=250',
        'state.won=true;_gameTelemetryPush("victory");state.score+=250',1
    )
    game_html=game_html.replace(
        'item.active=false;state.score+=10;',
        'item.active=false;_gameTelemetryPush("collect");state.score+=10;'
    )
    game_html=game_html.replace(
        '<p class="note">',
        '<p class="note">Press T to export local gameplay feedback. ',1
    )
    return game_html
