"""Independent offline Godot 4 native physics laboratory and exact replay gate.

This exports one explicitly supported deterministic original-game profile,
rather than pretending Godot's stock RigidBody physics matches Python's
fixed-point SAT/CCD. All unsupported game states fail closed *before* export.
"""
from __future__ import annotations

from hashlib import sha256

from .advanced_godot_export import (
    AdvancedGodotExportError, NativeAdvancedGamePackage, _json,
)
from .advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session,
)
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA = "skeleton.game_builder.godot_physics_lab.v1"
PROOF_SCHEMA = "skeleton.game_builder.godot_physics_lab_proof.v1"
NATIVE_ACTIONS = frozenset((
    "inspect", "step", "step:4", "push:east", "push:west",
    "push:up", "push:down", "brake", "torque:cw", "torque:ccw", "select:0",
))
PROOF_FIELDS = (
    "tick", "frame", "x", "y", "vx", "vy", "orientation",
    "angular_velocity", "impulses_left", "battery", "contacts",
    "max_velocity_seen", "max_angular_speed_seen", "goal_frames",
    "finished", "failed", "milestones",
)

GODOT_PHYSICS = r'''
extends Control
## Independent integer physics lab: one signed rigid body and finite actuators.
## NOT engine-builtin RigidBody parity; recreates authorized fixed-point rules.
const VERIFY_FLAG: String = "--verify-physics"
const MAX_ACTIONS: int = 128
const ACTIONS: Array = [
    "inspect","step","step:4","push:east","push:west",
    "push:up","push:down","brake","torque:cw","torque:ccw","select:0"
]

var original: Dictionary = {}
var cfg: Dictionary = {}
var chart: Dictionary = {}
var physical: Dictionary = {}
var actions: Array = []
var ready_to_play: bool = false
var notice: String = "Original Physics Lab · arrows push, J/K rotate, B brake"


func _fault(problem: String) -> void:
    push_error("NATIVE_PHYSICS_PARITY_ERROR: " + problem)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var content: String = FileAccess.get_file_as_string("res://game.json")
    if content.is_empty() or content.length() > 80000:
        _fault("original source absent or too large")
        return
    var decoded: Variant = JSON.parse_string(content)
    if typeof(decoded) != TYPE_DICTIONARY:
        _fault("invalid authored JSON")
        return
    original = decoded
    if str(original.get("schema","")) != "skeleton.game_builder.godot_physics_lab.v1":
        _fault("unknown native physics source")
        return
    cfg = original["settings"]
    chart = original["scene"]["layout"]
    if (int(cfg["max_bodies"]) != 1 or int(cfg["gravity"]) != 0
        or int(cfg["substeps"]) != 1 or str(cfg["dimension"]) != "2d"
        or str(cfg["collision_geometry"]) != "aabb"
        or int(cfg["initial_battery"]) != 0
        or chart["bodies"].size() != 1 or chart["fixtures"].size() != 0
        or chart["water_y"] <= chart["floor_y"]):
        _fault("profile forbids unsupported native dynamics")
        return
    ready_to_play = true
    get_window().title = "Skeleton Original Physics Lab"
    _reset()
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _floor_div(a: int, b: int) -> int:
    return floori(float(a) / float(b))


func _clamp(v: int, lo: int, hi: int) -> int:
    return maxi(lo,mini(hi,v))


func _reset() -> void:
    var body: Dictionary = chart["bodies"][0]
    physical = {
        "tick":0, "frame":0,
        "x":int(body["position"][0]),"y":int(body["position"][1]),
        "vx":int(body["velocity"][0]),"vy":int(body["velocity"][1]),
        "orientation":int(body["initial_orientation"]),
        "angular_velocity":0,
        "impulses_left":int(cfg["impulse_budget"]),
        "battery":int(cfg["initial_battery"]),
        "contacts":0,"max_velocity_seen":0,
        "max_angular_speed_seen":0,"goal_frames":0,
        "finished":false,"failed":false,"milestones":[],
    }
    actions=[]
    notice="Push the authored payload to the green destination"
    queue_redraw()


func _frame() -> void:
    physical["frame"]=int(physical["frame"])+1
    var vx: int=int(physical["vx"])
    var vy: int=int(physical["vy"])
    var ang: int=int(physical["angular_velocity"])
    physical["orientation"]=posmod(int(physical["orientation"])+ang,360000)
    ang=int(float(ang*(100-int(cfg["angular_damping"])))/100.0)
    physical["angular_velocity"]=ang
    physical["max_angular_speed_seen"]=maxi(
        int(physical["max_angular_speed_seen"]),absi(ang))
    physical["x"]=int(physical["x"])+vx
    physical["y"]=int(physical["y"])+vy
    vx=_floor_div(vx*(100-int(cfg["air_drag"])),100)
    vy=_floor_div(vy*(100-int(cfg["air_drag"])),100)
    var radius: int=int(chart["bodies"][0]["radius"])
    var floor_y: int=int(chart["floor_y"])*100-radius
    if int(physical["y"])>=floor_y:
        vx=_floor_div(vx*(100-int(cfg["floor_friction"])),100)
    physical["max_velocity_seen"]=maxi(
        int(physical["max_velocity_seen"]),maxi(absi(vx),absi(vy)))
    var width: int=(int(chart["width"])-1)*100-radius
    var lower: int=radius
    if int(physical["x"])<lower or int(physical["x"])>width:
        physical["x"]=_clamp(int(physical["x"]),lower,width)
        vx=_floor_div(-vx*int(cfg["wall_restitution"]),100)
        physical["contacts"]=int(physical["contacts"])+1
    if int(physical["y"])<lower or int(physical["y"])>floor_y:
        physical["y"]=_clamp(int(physical["y"]),lower,floor_y)
        vy=_floor_div(-vy*int(cfg["wall_restitution"]),100)
        physical["contacts"]=int(physical["contacts"])+1
    physical["vx"]=vx
    physical["vy"]=vy
    var goal: Array=chart["goal"]
    if (absi(int(physical["x"])-int(goal[0]))<=int(cfg["goal_radius"])
        and absi(int(physical["y"])-int(goal[1]))<=int(cfg["goal_radius"])
        and maxi(absi(vx),absi(vy))<=int(cfg["goal_speed"])):
        physical["goal_frames"]=int(physical["goal_frames"])+1
        if int(physical["goal_frames"])>=int(cfg["goal_dwell_frames"]):
            if str(cfg["completion_mode"])=="challenge":
                physical["finished"]=true
            elif not physical["milestones"].has("cargo_docked"):
                physical["milestones"].append("cargo_docked")
    else:
        physical["goal_frames"]=0


func _step(action: String) -> bool:
    if (not ready_to_play or bool(physical["finished"])
        or bool(physical["failed"]) or actions.size()>=MAX_ACTIONS
        or action not in ACTIONS):
        return false
    var kind: String=action
    var mass: int=int(chart["bodies"][0]["mass"])
    if kind.begins_with("push:"):
        if int(physical["impulses_left"])<1:
            return false
        physical["impulses_left"]=int(physical["impulses_left"])-1
        var delta: int=_floor_div(int(cfg["impulse_strength"]),mass)
        match kind:
            "push:east":
                physical["vx"]=_clamp(int(physical["vx"])+delta,
                    -int(cfg["speed_limit"]),int(cfg["speed_limit"]))
            "push:west":
                physical["vx"]=_clamp(int(physical["vx"])-delta,
                    -int(cfg["speed_limit"]),int(cfg["speed_limit"]))
            "push:up":
                physical["vy"]=_clamp(int(physical["vy"])-delta,
                    -int(cfg["speed_limit"]),int(cfg["speed_limit"]))
            "push:down":
                physical["vy"]=_clamp(int(physical["vy"])+delta,
                    -int(cfg["speed_limit"]),int(cfg["speed_limit"]))
    elif kind.begins_with("torque:"):
        if int(physical["impulses_left"])<1:
            return false
        physical["impulses_left"]=int(physical["impulses_left"])-1
        var radius: int=int(chart["bodies"][0]["radius"])
        var inertia: int=maxi(1,_floor_div(mass*radius*radius,100))
        var change: int=maxi(1,_floor_div(int(cfg["torque_strength"])*100,inertia))
        if kind=="torque:ccw":
            change=-change
        physical["angular_velocity"]=_clamp(
            int(physical["angular_velocity"])+change,
            -int(cfg["max_angular_speed"]),int(cfg["max_angular_speed"]))
    elif kind=="brake":
        physical["vx"]=_floor_div(
            int(physical["vx"])*(100-int(cfg["brake_strength"])),100)
        physical["vy"]=_floor_div(
            int(physical["vy"])*(100-int(cfg["brake_strength"])),100)
        # Python uses truncation towards zero for signed angular braking.
        physical["angular_velocity"]=int(
            float(int(physical["angular_velocity"])*
            (100-int(cfg["brake_strength"])))/100.0)
    physical["tick"]=int(physical["tick"])+1
    var iterations: int=4 if action=="step:4" else 1
    for _i in range(iterations):
        if bool(physical["finished"]) or bool(physical["failed"]):
            break
        _frame()
    actions.append(action)
    queue_redraw()
    return true


func _snapshot() -> Dictionary:
    return physical.duplicate(true)


func _verify() -> void:
    var raw: String=FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length()>100000:
        _fault("missing or oversized original proof")
        return
    var data: Variant=JSON.parse_string(raw)
    if typeof(data)!=TYPE_DICTIONARY:
        _fault("invalid Python receipt")
        return
    if (str(data.get("schema","")) !=
        "skeleton.game_builder.godot_physics_lab_proof.v1"
        or data.get("settings_digest")!=original.get("settings_digest")
        or data.get("scene_digest")!=original["scene"]["digest"]):
        _fault("physics proof bound to wrong authored source")
        return
    if typeof(data.get("actions"))!=TYPE_ARRAY or typeof(data.get("expected"))!=TYPE_DICTIONARY:
        _fault("malformed native replay")
        return
    if data["actions"].size()>MAX_ACTIONS:
        _fault("native replay exceeds finite budget")
        return
    for command in data["actions"]:
        if typeof(command)!=TYPE_STRING or not _step(command):
            _fault("original physical command rejected")
            return
    var expected: Dictionary=data["expected"]
    var actual: Dictionary=_snapshot()
    if actual.size()!=expected.size():
        _fault("physics proof schema drift")
        return
    for key in actual:
        if not expected.has(key) or actual[key]!=expected[key]:
            _fault("independent native physics divergence: "+key+
                   " actual="+str(actual[key])+" expected="+str(expected.get(key)))
            return
    print("NATIVE_ADVANCED_PHYSICS_OK " + str(original["scene"]["digest"]) +
          " actions="+str(actions.size()) +
          " frames="+str(actual["frame"]))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not ready_to_play or not event is InputEventKey or not event.pressed or event.echo:
        return
    var command: String=""
    match event.keycode:
        KEY_LEFT,KEY_A: command="push:west"
        KEY_RIGHT,KEY_D: command="push:east"
        KEY_UP,KEY_W: command="push:up"
        KEY_DOWN,KEY_S: command="push:down"
        KEY_J: command="torque:ccw"
        KEY_K: command="torque:cw"
        KEY_B: command="brake"
        KEY_SPACE: command="step"
        KEY_R: _reset()
    if command!="":
        _step(command)
    get_viewport().set_input_as_handled()


func _draw() -> void:
    var sx: float=50.0
    var sy: float=70.0
    var factor: float=30.0
    var goal: Array=chart.get("goal",[800,960,0])
    draw_rect(Rect2(sx,sy,int(chart.get("width",18))*factor,
                    int(chart.get("floor_y",10))*factor),
              Color(0.08,0.20,0.24))
    for x in range(int(chart.get("width",18))):
        draw_line(Vector2(sx+x*factor,sy),
                  Vector2(sx+x*factor,sy+int(chart.get("floor_y",10))*factor),
                  Color(0.19,0.35,0.42),1.0)
    draw_rect(Rect2(sx+int(goal[0])*factor/100.0-9,
                    sy+int(goal[1])*factor/100.0-9,18,18),
              Color(0.30,0.80,0.49),false,2)
    var b: Dictionary=chart["bodies"][0]
    var center:=Vector2(sx+int(physical["x"])*factor/100.0,
                        sy+int(physical["y"])*factor/100.0)
    var radius: float=int(b["radius"])*factor/100.0
    draw_circle(center,radius,Color(0.93,0.74,0.43))
    var radians: float=float(physical["orientation"])*PI/180000.0
    draw_line(center,center+Vector2(cos(radians),sin(radians))*radius,
              Color(0.06,0.12,0.21),3)
'''


def _projection(state: dict) -> dict:
    body = state["bodies"][0]
    return {
        "tick":state["tick"],"frame":state["frame"],
        "x":body["position"][0],"y":body["position"][1],
        "vx":body["velocity"][0],"vy":body["velocity"][1],
        "orientation":body["orientation"],
        "angular_velocity":body["angular_velocity"],
        "impulses_left":state["impulses_left"],"battery":state["battery"],
        "contacts":state["contacts"],"max_velocity_seen":state["max_velocity_seen"],
        "max_angular_speed_seen":state["max_angular_speed_seen"],
        "goal_frames":state["goal_frames"],"finished":state["finished"],
        "failed":state["failed"],"milestones":state["milestones"],
    }


def render_physics_godot_package(session: dict, settings: dict | None = None,
                                 *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("native physics export requires explicit operator approval")
    if type(session) is not dict or session.get("editor") != "physics":
        raise AdvancedGodotExportError("native physics requires an original physics session")
    config = make_editor_document("physics",settings)
    rules = config["settings"]
    verify_advanced_session(session,rules)
    if not (
        rules["dimension"]=="2d" and rules["collision_geometry"]=="aabb"
        and rules["max_bodies"]==1 and rules["gravity"]==0
        and rules["substeps"]==1 and rules["initial_battery"]==0
    ):
        raise AdvancedGodotExportError(
            "native parity profile: single-body, 2D AABB, zero gravity, "
            "zero motor battery and one authored fixed substep required")
    if any(action not in NATIVE_ACTIONS for action in session["actions"]):
        raise AdvancedGodotExportError("native action unsupported by exact physics profile")
    scene = (validate_advanced_scene(session["scene"],rules)
             if session["scene"] is not None
             else make_advanced_scene("physics",rules,seed=session["seed"]))
    if session["scene"] is None:
        session=run_advanced_session("physics",rules,session["actions"],
                                     seed=session["seed"],scene=scene)
    layout=scene["layout"]
    if (len(layout["bodies"])!=1 or layout["fixtures"] or
        layout["water_y"]<=layout["floor_y"] or
        layout["bodies"][0]["position"][1]!=
        layout["floor_y"]*100-layout["bodies"][0]["radius"]):
        raise AdvancedGodotExportError(
            "native profile needs one floor-grounded object without fixtures/water")
    game={
        "schema":SCHEMA,"editor":"physics","quality_floor":"advanced",
        "settings":rules,"settings_digest":config["digest"],"scene":scene,
        "independent_native_parity_verified":False,
        "native_profile":"fixedpoint_one_body_2d_laboratory",
    }
    proof={
        "schema":PROOF_SCHEMA,"settings_digest":config["digest"],
        "scene_digest":scene["digest"],"actions":list(session["actions"]),
        "expected":_projection(session["state"]),
        "python_session_digest":session["digest"],
        "verified_by_python_replay":True,
    }
    files={
        "godot/project.godot":_PROJECT.replace(
            "Skeleton Original Adventure","Skeleton Original Physics Laboratory"
        ).encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_PHYSICS.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Skeleton Original Native Physics Laboratory\n\n"
            "One-body independently executing fixed-point physics reference, offline.\n"
            "Arrows/WASD apply finite impulses, J/K torque, B brakes, Space advances.\n"
            "Godot 4.4.1+ headless source-proof check:\n"
            "godot --headless --path godot -- --verify-physics\n\n"
            "Only the exact signed one-body 2D zero-gravity AABB profile is "
            "supported. Other physics modes refuse export; Godot built-in "
            "RigidBody contact equivalence and hardware certification are NOT claimed.\n"
        ).encode("utf-8")
    }
    manifest={
        "schema":"skeleton.game_builder.advanced_native_package.v1",
        "native_editor":"physics",
        "native_adapter":"godot4_independent_fixedpoint_physics_lab",
        "advanced_floor":True,
        "source_session_digest":session["digest"],
        "authored_scene_digest":scene["digest"],
        "native_parity_profile":"fixedpoint_one_body_2d_laboratory",
        "files":{path:sha256(raw).hexdigest() for path,raw in sorted(files.items())},
        "godot_executed":False,"native_hardware_certified":False,
        "publish_approved":False,
    }
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","PROOF_FIELDS","NATIVE_ACTIONS",
         "GODOT_PHYSICS","render_physics_godot_package"]
