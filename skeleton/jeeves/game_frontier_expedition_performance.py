"""Canonical cinematic performances with timed mouth-visemes and soundtrack cues.

This is a deterministic phoneme-inspired *text timing* driver, not a claim of
TTS, live speech recognition, actor likeness or professional face capture.
Visemes, camera and original audio are tied to real authored scene identities.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from math import isfinite
from .game_frontier_expedition import ExpeditionError,_digest,_json
from .game_frontier_expedition_cinematics import Storyboard
from .game_frontier_expedition_narrative import StoryBook

VOWELS=set("aeiouy")
CONSONANTS=set("pbmfv")
@dataclass(frozen=True,slots=True)
class PerformancePolicy:
    fps:int=24
    frames_per_character:int=3
    max_dialogue_chars:int=2048
    def __post_init__(self):
        if type(self.fps) is not int or self.fps not in (24,30,50,60):
            raise ExpeditionError("original performance frame rate invalid")
        if type(self.frames_per_character) is not int or not 1<=self.frames_per_character<=8:
            raise ExpeditionError("performance mouth speed outside source bounds")
        if type(self.max_dialogue_chars) is not int or not 1<=self.max_dialogue_chars<=4096:
            raise ExpeditionError("performance speech budget invalid")

def _viseme(character:str)->str:
    if character.isspace():
        return "rest"
    if character.lower() in VOWELS:
        return "open"
    if character.lower() in CONSONANTS:
        return "closed"
    return "narrow"

def author_performance(story:StoryBook,board:Storyboard, *,
                       policy:PerformancePolicy=PerformancePolicy())->dict:
    if (not isinstance(story,StoryBook) or not isinstance(board,Storyboard)
            or not isinstance(policy,PerformancePolicy)
            or story.world_digest!=board.world_digest
            or story.gdd_digest!=board.gdd_digest):
        raise ExpeditionError("facial performance is not bound to one original GDD/story")
    scenes={scene.waypoint:scene for scene in story.scenes}
    takes=[]
    for clip in board.clips:
        if clip.waypoint not in scenes:
            raise ExpeditionError("camera shot has no authored scene dialogue")
        scene=scenes[clip.waypoint]
        line=scene.opening
        if not 1<=len(line)<=policy.max_dialogue_chars:
            raise ExpeditionError("scene dialogue violates speech budget")
        # Fit the entire original line into a finite cinematic. Every source
        # character receives an indexed viseme even when clipped into a frame.
        source=[]
        for index,char in enumerate(line):
            moment=min(clip.frames-1,index*policy.frames_per_character)
            source.append({"frame":moment,"char_index":index,
                           "viseme":_viseme(char),"symbol":char})
        # Distinct keyed expression frames, no unexplained interpolated shifts.
        emotional=[
            {"frame":0,"eyebrow":0.,"jaw":0.,"emotion":"anticipation"},
            {"frame":clip.frames//2,"eyebrow":.18,"jaw":.28,"emotion":"discovery"},
            {"frame":clip.frames-1,"eyebrow":-.08,"jaw":0.,"emotion":"resolve"},
        ]
        takes.append({"clip_id":clip.clip_id,"scene_id":scene.scene_id,
                      "speaker":scene.speaker,"dialogue":line,
                      "visemes":source,"expressions":emotional,
                      "duration_frames":clip.frames,"fps":policy.fps,
                      "camera_source":board.digest,
                      "audio_alignment_verified":False})
    result={"schema":"skeleton.game.original_facial_performance.v1",
            "world":story.world_digest,"story_digest":story.digest,
            "storyboard_digest":board.digest,"policy":asdict(policy),
            "takes":takes,"native_character_animation_verified":False}
    result["receipt_digest"]=_digest(result)
    return result

def verify_performance(story:StoryBook,board:Storyboard,
                       performance:dict,policy:PerformancePolicy=PerformancePolicy())->None:
    if not isinstance(performance,dict) or performance!=author_performance(story,board,policy=policy):
        raise ExpeditionError("original speech/visemes differ from canonical scene")

_GODOT_PERFORMANCE = """extends Node3D
# Original dialogue-viseme source for a real lightweight facial puppet.
const SOURCE = "res://game/frontier/performance.json"
var takes: Dictionary = {}
var mouth: MeshInstance3D
var tick: int = 0
var active_id: String = ""

func _ready() -> void:
    var parsed = JSON.parse_string(FileAccess.get_file_as_string(SOURCE))
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Authored original performance missing")
        return
    if str(parsed.get("world","")) != str(get_meta("expected_world","")):
        push_error("Original performance belongs to another authored game")
        return
    for take in parsed.get("takes", []):
        takes[str(take.get("clip_id", ""))] = take
    mouth = MeshInstance3D.new()
    var geometry := SphereMesh.new()
    geometry.radius = .11
    mouth.mesh = geometry
    mouth.position = Vector3(0,1.7,-.26)
    add_child(mouth)
    print("EXPEDITION_PERFORMANCE_READY " + str(parsed.get("world","")))

func play_performance(clip_id: String) -> bool:
    if not takes.has(clip_id):
        return false
    active_id = clip_id
    tick = 0
    return true

func _process(_delta: float) -> void:
    if active_id == "" or mouth == null:
        return
    var take: Dictionary = takes[active_id]
    var expression: String = "rest"
    for event in take.get("visemes", []):
        if int(event["frame"]) > tick:
            break
        expression = str(event["viseme"])
    mouth.scale.y = 1.65 if expression == "open" else .32 if expression == "closed" else .85
    tick += 1
    if tick >= int(take.get("duration_frames",1)):
        active_id = ""
        print("EXPEDITION_PERFORMANCE_COMPLETE " + str(take.get("clip_id","")))
"""
def export_performance_godot(story:StoryBook,board:Storyboard)->dict[str,str]:
    return {"game/frontier/performance.json":_json(author_performance(story,board)).decode("utf-8"),
            "game/frontier/performance.gd":_GODOT_PERFORMANCE}
