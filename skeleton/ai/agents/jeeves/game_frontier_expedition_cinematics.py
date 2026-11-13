"""Original cinematic timelines, interpolation and playable Godot scene source.

All frames refer to actual authored game coordinates; the exported scene
runs with Godot's Camera3D. Source frame receipts do not assert native render.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from math import isfinite
from .game_frontier_expedition import ExpeditionError,ExpeditionWorld,_digest,_json


@dataclass(frozen=True,slots=True)
class CameraKey:
    frame:int
    x:float
    y:float
    z:float
    look_x:float
    look_y:float
    look_z:float
    fov:float=65.

    def __post_init__(self):
        if type(self.frame) is not int or not 0<=self.frame<=216000:
            raise ExpeditionError("camera frame out of range")
        for name in ("x","y","z","look_x","look_y","look_z","fov"):
            v=getattr(self,name)
            lo,hi=(30,115) if name=="fov" else (-1e6,1e6)
            if type(v) not in (int,float) or not isfinite(v) or not lo<=v<=hi:
                raise ExpeditionError("camera geometry is nonfinite or unbounded")


@dataclass(frozen=True,slots=True)
class Cinematic:
    clip_id:str
    waypoint:str
    frames:int
    fps:int
    keys:tuple[CameraKey,...]
    dialogue:str
    event_ref:str

    def __post_init__(self):
        for token in (self.clip_id,self.waypoint,self.event_ref):
            if type(token) is not str or not token.isidentifier():
                raise ExpeditionError("cinematic source id invalid")
        if type(self.fps) is not int or self.fps not in (24,25,30,50,60):
            raise ExpeditionError("unsupported cinematic frame rate")
        if type(self.frames) is not int or not 2<=self.frames<=216000:
            raise ExpeditionError("cinematic frame count invalid")
        if (type(self.keys) is not tuple or not 2<=len(self.keys)<=512
                or self.keys[0].frame!=0 or self.keys[-1].frame!=self.frames-1
                or any(b.frame<=a.frame for a,b in zip(self.keys,self.keys[1:]))):
            raise ExpeditionError("cinematic keys must cover ordered full clip")
        if not isinstance(self.dialogue,str) or len(self.dialogue)>1024:
            raise ExpeditionError("original scene dialogue out of bounds")


@dataclass(frozen=True,slots=True)
class Storyboard:
    world_digest:str
    gdd_digest:str
    clips:tuple[Cinematic,...]

    def __post_init__(self):
        if any(type(x) is not str or len(x)!=64 for x in (self.world_digest,self.gdd_digest)):
            raise ExpeditionError("storyboard needs world and GDD source digests")
        if type(self.clips) is not tuple or not 1<=len(self.clips)<=128:
            raise ExpeditionError("storyboard clip count invalid")
        if len({c.clip_id for c in self.clips})!=len(self.clips):
            raise ExpeditionError("duplicate cinematic clip identity")

    def validate(self,world:ExpeditionWorld):
        if not isinstance(world,ExpeditionWorld) or world.digest!=self.world_digest:
            raise ExpeditionError("cinematic source world has changed")
        if any(clip.waypoint not in world.by_id for clip in self.clips):
            raise ExpeditionError("cinematic references missing location")

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict:
        return {
            "schema":"skeleton.game.original_storyboard.v1",
            "world":self.world_digest,"gdd":self.gdd_digest,
            "clips":[asdict(c) for c in self.clips],
        }


def camera_at(clip:Cinematic,frame:int)->CameraKey:
    if not isinstance(clip,Cinematic) or type(frame) is not int or not 0<=frame<clip.frames:
        raise ExpeditionError("requested cinematic frame unavailable")
    for a,b in zip(clip.keys,clip.keys[1:]):
        if a.frame<=frame<=b.frame:
            factor=(frame-a.frame)/(b.frame-a.frame)
            values=tuple(round(getattr(a,k)*(1-factor)+getattr(b,k)*factor,6)
                         for k in ("x","y","z","look_x","look_y","look_z","fov"))
            return CameraKey(frame,*values)
    raise ExpeditionError("cinematic keyframe continuity lost")


def storyboard_frame_receipts(board:Storyboard,*,sample_stride:int=1)->dict:
    if not isinstance(board,Storyboard) or type(sample_stride) is not int or not 1<=sample_stride<=600:
        raise ExpeditionError("cinematic frame sampling bound invalid")
    if sum((clip.frames-1)//sample_stride+1 for clip in board.clips)>200000:
        raise ExpeditionError("cinematic frame evidence budget exceeded")
    history=[]
    prior=_digest({"storyboard":board.digest,"genesis":True})
    for clip in board.clips:
        for frame in range(0,clip.frames,sample_stride):
            proof=_digest({"board":board.digest,"clip":clip.clip_id,
                           "frame":frame,"camera":asdict(camera_at(clip,frame)),
                           "prior":prior})
            history.append({"clip":clip.clip_id,"frame":frame,"receipt":proof})
            prior=proof
    report={
        "schema":"skeleton.game.cinematic_frame_journal.v1",
        "storyboard":board.digest,"stride":sample_stride,
        "frames_checked":len(history),"history":history,
        "first":history[0]["receipt"],"last":history[-1]["receipt"],
        "native_frames_rendered":False,
    }
    report["receipt_digest"]=_digest(report)
    return report


def original_game_storyboard(world:ExpeditionWorld,gdd_digest:str)->Storyboard:
    if not isinstance(world,ExpeditionWorld) or type(gdd_digest) is not str or len(gdd_digest)!=64:
        raise ExpeditionError("original cinematic needs world/GDD")
    clips=[]
    ids=(world.arrival,world.waypoints[1].waypoint_id,world.destinations[0])
    for index,place in enumerate(ids):
        node=world.by_id[place]
        def pose(frame,dx,dy,dz):
            return CameraKey(frame,node.x_m+dx,node.altitude_m+dy,node.y_m+dz,
                             node.x_m,node.altitude_m,node.y_m)
        clips.append(Cinematic(
            f"scene_{index+1:03d}",place,72,24,
            (pose(0,0,20,35),pose(35,18,12,24),pose(71,6,9,14)),
            ("Departure across the sky","An island surfaces through clouds",
             "The horizon enters the archive")[index],
            f"story_act_{index+1}",
        ))
    return Storyboard(world.digest,gdd_digest,tuple(clips))


_GODOT_SCRIPT = """extends Node3D
# Original source-bound cinematic Camera3D gameplay viewer.
const STORYBOARD = "res://game/frontier/storyboard.json"
var source: Dictionary = {}
var active: Dictionary = {}
var frame: int = 0
var camera: Camera3D

func _ready() -> void:
    if not FileAccess.file_exists(STORYBOARD):
        push_error("Missing original game storyboard")
        return
    var parsed = JSON.parse_string(FileAccess.get_file_as_string(STORYBOARD))
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Invalid storyboard JSON")
        return
    source = parsed
    camera = Camera3D.new()
    camera.current = false
    add_child(camera)
    set_process(false)

func play_clip(clip_id: String, world_digest: String) -> bool:
    if str(source.get("world", "")) != world_digest:
        return false
    for clip in source.get("clips", []):
        if str(clip.get("clip_id", "")) == clip_id:
            active = clip
            frame = 0
            camera.current = true
            set_process(true)
            return true
    return false

func _process(_delta: float) -> void:
    if active.is_empty() or camera == null:
        return
    var keys: Array = active.get("keys", [])
    for i in range(keys.size()-1):
        var left: Dictionary = keys[i]
        var right: Dictionary = keys[i+1]
        var begin_frame: int = int(left["frame"])
        var end_frame: int = int(right["frame"])
        if frame < begin_frame or frame > end_frame:
            continue
        var weight: float = float(frame-begin_frame)/float(end_frame-begin_frame)
        var a := Vector3(float(left["x"]),float(left["y"]),float(left["z"]))
        var b := Vector3(float(right["x"]),float(right["y"]),float(right["z"]))
        camera.position = a.lerp(b,weight)
        var look_a := Vector3(float(left["look_x"]),float(left["look_y"]),float(left["look_z"]))
        var look_b := Vector3(float(right["look_x"]),float(right["look_y"]),float(right["look_z"]))
        camera.look_at(look_a.lerp(look_b,weight),Vector3.UP)
        camera.fov = lerpf(float(left["fov"]),float(right["fov"]),weight)
        break
    if frame >= int(active["frames"])-1:
        print("EXPEDITION_CINEMATIC_COMPLETE " + str(active["clip_id"]))
        active = {}
        camera.current = false
        set_process(false)
    else:
        frame += 1
"""

_GODOT_SCENE = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://game/frontier/cinematic.gd" id="1"]

[node name="OriginalCinematic" type="Node3D"]
script = ExtResource("1")
"""


_GODOT_AUDIT = """extends SceneTree
# Independently exercise an authored original Camera3D timeline on real Godot.
const CLIP = preload("res://game/frontier/cinematic.tscn")
const DATA_PATH = "res://game/frontier/storyboard.json"

func _initialize() -> void:
    call_deferred("_play_original_clip")

func _play_original_clip() -> void:
    if not FileAccess.file_exists(DATA_PATH):
        push_error("Cinema audit source is absent")
        quit(41)
        return
    var parsed = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Cinema audit source JSON invalid")
        quit(42)
        return
    if str(parsed.get("schema", "")) != "skeleton.game.original_storyboard.v1":
        push_error("Cinema audit schema mismatch")
        quit(43)
        return
    var clips: Array = parsed.get("clips", [])
    if clips.is_empty() or str(parsed.get("world", "")).length() != 64:
        push_error("Cinema audit needs source-bound timeline")
        quit(44)
        return
    var cinema: Node3D = CLIP.instantiate()
    root.add_child(cinema)
    await process_frame
    var launched: bool = bool(cinema.call(
        "play_clip", str(clips[0]["clip_id"]), str(parsed["world"])))
    if not launched:
        push_error("Cinema clip failed source binding")
        quit(45)
        return
    print("EXPEDITION_CINEMATIC_AUDIT_STARTED " + str(parsed["world"]))
    # Exercise the real GDScript camera interpolator at fixed authored frames.
    # The actual Camera3D is read back after each native runtime invocation.
    cinema.set_process(false)
    for frame_index in [0,17,35,54,71]:
        cinema.set("frame", frame_index)
        cinema.call("_process", 0.04166667)
        var actual: Camera3D = cinema.get("camera")
        if actual == null:
            push_error("Native cinematic never built Camera3D")
            quit(46)
            return
        print("EXPEDITION_CINEMATIC_FRAME " + JSON.stringify({
            "world_digest":str(parsed["world"]),
            "clip_id":str(clips[0]["clip_id"]),
            "frame":frame_index,
            "x":actual.position.x,
            "y":actual.position.y,
            "z":actual.position.z,
            "fov":actual.fov,
        }))
    print("EXPEDITION_CINEMATIC_AUDIT_VERIFIED " + str(clips[0]["clip_id"]))
    quit(0)
"""


def export_storyboard_godot(board:Storyboard,world:ExpeditionWorld)->dict[str,str]:
    board.validate(world)
    return {
        "game/frontier/storyboard.json":_json(board.as_dict()).decode("utf-8"),
        "game/frontier/cinematic.gd":_GODOT_SCRIPT,
        "game/frontier/cinematic.tscn":_GODOT_SCENE,
        "game/frontier/cinematic_audit.gd":_GODOT_AUDIT,
    }
