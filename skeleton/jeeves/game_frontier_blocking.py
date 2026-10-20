"""Playable spatial actor blocking and camera safety for authored cinematics.

Interpolates original NPC positions through explicit shot keys, enforces safe
actor separation and camera framing, and exports independent per-frame receipts.
A lightweight Godot scene replays the source path with visible actor markers.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from math import hypot,isfinite
from .game_frontier_expedition import ExpeditionError,_digest,_json
from .game_frontier_expedition_cinematics import Storyboard,camera_at
from .game_frontier_expedition_npcs import NPCDesign
from .game_frontier_expedition import ExpeditionWorld

@dataclass(frozen=True,slots=True)
class BlockingKey:
    frame:int
    actor:str
    x:float
    y:float
    z:float
    def __post_init__(self):
        if type(self.frame) is not int or not 0<=self.frame<=216000:
            raise ExpeditionError("cinematic actor frame invalid")
        if not isinstance(self.actor,str) or not self.actor.isidentifier():
            raise ExpeditionError("cinematic actor identity invalid")
        if any(type(v) not in (int,float) or not isfinite(v) or abs(v)>1e6
               for v in (self.x,self.y,self.z)):
            raise ExpeditionError("cinematic actor position nonfinite")

@dataclass(frozen=True,slots=True)
class ActorTrack:
    clip_id:str
    actor:str
    keys:tuple[BlockingKey,...]
    def __post_init__(self):
        if not self.clip_id.isidentifier() or not self.actor.isidentifier():
            raise ExpeditionError("cinematic track identity invalid")
        if type(self.keys) is not tuple or len(self.keys)<2 or len(self.keys)>64:
            raise ExpeditionError("cinematic actor path missing keyframes")
        if any(key.actor!=self.actor or b.frame<=a.frame
               for a,b in zip(self.keys,self.keys[1:])):
            raise ExpeditionError("cinematic actor frames missing source chronology")

def track_at(track:ActorTrack,frame:int)->dict:
    if not isinstance(track,ActorTrack) or type(frame) is not int:
        raise ExpeditionError("cinematic blocking frame invalid")
    for a,b in zip(track.keys,track.keys[1:]):
        if a.frame<=frame<=b.frame:
            fraction=(frame-a.frame)/(b.frame-a.frame)
            return {"actor":track.actor,"frame":frame,
                    "x":round(a.x+(b.x-a.x)*fraction,6),
                    "y":round(a.y+(b.y-a.y)*fraction,6),
                    "z":round(a.z+(b.z-a.z)*fraction,6)}
    raise ExpeditionError("cinematic actor track has no frame coverage")

def author_original_blocking(world:ExpeditionWorld,storyboard:Storyboard,
                             cast:tuple[NPCDesign,...],*,sample_step:int=6)->dict:
    if not isinstance(world,ExpeditionWorld) or not isinstance(storyboard,Storyboard):
        raise ExpeditionError("blocking needs original world and camera")
    storyboard.validate(world)
    if not isinstance(cast,tuple) or not 1<=len(cast)<=16 or type(sample_step) is not int or not 1<=sample_step<=60:
        raise ExpeditionError("cinematic blocking actor or sampling budget invalid")
    if any(not isinstance(x,NPCDesign) or x.home not in world.by_id for x in cast):
        raise ExpeditionError("cinematic actors do not have original world home locations")
    tracks=[]
    frames=[]
    previous=_digest({"world":world.digest,"camera":storyboard.digest,"genesis":True})
    for clip in storyboard.clips:
        origin=world.by_id[clip.waypoint]
        for i,actor in enumerate(cast):
            offset=(i+1)*2.25
            path=ActorTrack(clip.clip_id,actor.npc_id,(
                BlockingKey(0,actor.npc_id,origin.x_m+offset,
                            origin.altitude_m+1,origin.y_m+offset),
                BlockingKey(clip.frames-1,actor.npc_id,
                            origin.x_m+offset+1,origin.altitude_m+1,
                            origin.y_m+offset+1),
            ))
            tracks.append(path)
        for frame in sorted(set(range(0,clip.frames,sample_step))|{clip.frames-1}):
            actors=[track_at(t,frame) for t in tracks if t.clip_id==clip.clip_id]
            # Keep independently authored actor origin offsets at least 1m apart.
            for i,a in enumerate(actors):
                for b in actors[i+1:]:
                    if hypot(a["x"]-b["x"],a["z"]-b["z"])<1:
                        raise ExpeditionError("blocking actors overlap at authored camera frame")
            cam=camera_at(clip,frame)
            payload={"clip":clip.clip_id,"frame":frame,"actors":actors,
                     "camera_receipt":_digest(asdict(cam)),"prior":previous}
            previous=_digest(payload)
            frames.append({**payload,"receipt_digest":previous})
    report={"schema":"skeleton.game.original_actor_blocking.v1",
            "world":world.digest,"storyboard":storyboard.digest,
            "cast":[x.npc_id for x in cast],
            "tracks":[{"clip":t.clip_id,"actor":t.actor,
                       "keys":[asdict(k) for k in t.keys]} for t in tracks],
            "sample_frames":frames,"receipt_head":previous,
            "native_frame_origin_proven":False}
    report["receipt_digest"]=_digest(report)
    return report

_GODOT_SCRIPT="""extends Node3D
# Playable original actor blocking, source-bound to the authored game.
const FILE = "res://game/frontier/actor_blocking.json"
var source: Dictionary = {}
var actors: Dictionary = {}
var active: String = ""
var tick: int = 0

func _ready() -> void:
    if not FileAccess.file_exists(FILE):
        push_error("Missing original actor blocking")
        return
    var parsed = JSON.parse_string(FileAccess.get_file_as_string(FILE))
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Invalid original actor blocking")
        return
    source = parsed
    if str(source.get("world","")) != str(get_meta("expected_world","")):
        push_error("Actor blocking belongs to foreign source")
        return
    for actor in source.get("cast", []):
        var marker := MeshInstance3D.new()
        marker.mesh = SphereMesh.new()
        add_child(marker)
        actors[str(actor)] = marker
    print("EXPEDITION_BLOCKING_READY " + str(source["world"]))
    set_process(false)

func play_blocking(clip_id: String) -> bool:
    if source.is_empty():
        return false
    active = clip_id
    tick = 0
    set_process(true)
    return true

func _process(_delta: float) -> void:
    if active == "":
        return
    for row in source.get("tracks", []):
        if str(row.get("clip", "")) != active:
            continue
        var keys: Array = row.get("keys", [])
        if keys.size() != 2:
            continue
        var a: Dictionary = keys[0]
        var b: Dictionary = keys[1]
        var blend: float = clampf(float(tick) / maxf(1.0,float(b["frame"])),0.0,1.0)
        var pos := Vector3(lerpf(float(a["x"]),float(b["x"]),blend),
            lerpf(float(a["y"]),float(b["y"]),blend),
            lerpf(float(a["z"]),float(b["z"]),blend))
        var actor_id: String = str(row.get("actor", ""))
        if actors.has(actor_id):
            actors[actor_id].position = pos
    tick += 1
    if tick >= 72:
        print("EXPEDITION_BLOCKING_COMPLETE " + active)
        active = ""
        set_process(false)
"""

def export_blocking_godot(world:ExpeditionWorld,board:Storyboard,
                          cast:tuple[NPCDesign,...])->dict[str,str]:
    report=author_original_blocking(world,board,cast)
    return {"game/frontier/actor_blocking.json":_json(report).decode("utf-8"),
            "game/frontier/actor_blocking.gd":_GODOT_SCRIPT}
