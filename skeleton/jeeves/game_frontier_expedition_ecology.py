"""Original per-biome procedural foliage and weather-aware growth/sway.

Provides reproducible positions, stable IDs, original flora archetypes,
LOD density and exact frame-based wind dynamics. Exports a Godot MultiMesh
scene for *actual* instancing, not just a visually themed metadata label.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
from math import sin,cos,pi,isfinite
import random

from .game_frontier_expedition import ExpeditionWorld,ExpeditionError,_digest,_json

KINDS={
    "sky_island":"cloud_grass",
    "underwater":"tide_kelp",
    "cavern":"glow_fungus",
    "settlement":"sky_lantern",
    "ruins":"memory_vine",
    "canopy":"wind_fern",
    "volcano":"ember_reed",
    "ice":"crystal_sprout",
    "airship":"deck_herb",
    "ground":"wayfarer_grass",
}


@dataclass(frozen=True,slots=True)
class EcologyPolicy:
    seed:int=7
    per_waypoint:int=16
    patch_radius_m:float=5.
    wind_response:float=.4
    seasonal_growth:float=.7

    def __post_init__(self):
        if type(self.seed) is not int or not 0<=self.seed<2**63:
            raise ExpeditionError("ecology seed is outside original game budget")
        if type(self.per_waypoint) is not int or not 1<=self.per_waypoint<=128:
            raise ExpeditionError("foliage per-region budget invalid")
        for name,low,hi in (("patch_radius_m",.5,100),("wind_response",0,1),
                            ("seasonal_growth",0,1)):
            val=getattr(self,name)
            if type(val) not in (int,float) or not isfinite(val) or not low<=val<=hi:
                raise ExpeditionError("ecology growth parameter invalid")


def generate_original_ecology(world:ExpeditionWorld, policy:EcologyPolicy=EcologyPolicy())->dict:
    if not isinstance(world,ExpeditionWorld) or not isinstance(policy,EcologyPolicy):
        raise ExpeditionError("ecology needs exact authored game world")
    if len(world.waypoints)*policy.per_waypoint>8192:
        raise ExpeditionError("ecology game instances exceeded world budget")
    points=[]
    for node in world.waypoints:
        original_seed=int(sha256(
            f"{world.digest}:{policy.seed}:{node.waypoint_id}".encode()
        ).hexdigest()[:15],16)
        rng=random.Random(original_seed)
        for j in range(policy.per_waypoint):
            radians=2*pi*rng.random()
            radius=policy.patch_radius_m*(rng.random()**.5)
            item={
                "id":f"{node.waypoint_id}_plant_{j:04d}",
                "waypoint":node.waypoint_id,
                "species":KINDS[node.kind],
                "x":round(node.x_m+cos(radians)*radius,5),
                "y":round(node.altitude_m+(rng.random()-.5)*.3,5),
                "z":round(node.y_m+sin(radians)*radius,5),
                "scale":round(.3+policy.seasonal_growth*(.5+rng.random()),5),
                "phase":round(2*pi*rng.random(),5),
                "response":round(policy.wind_response*(.5+rng.random()),5),
            }
            points.append(item)
    manifest={
        "schema":"skeleton.game.original_ecology.v1",
        "world_digest":world.digest,
        "source_digest":world.source_digest,
        "policy":asdict(policy),
        "instance_count":len(points),
        "instances":points,
        "native_engine_instances_verified":False,
    }
    manifest["receipt_digest"]=_digest(manifest)
    return manifest


def simulate_ecology_frame(manifest:dict,*,frame:int,fps:int=60,
                           wind_mps:float=5.)->dict:
    if (not isinstance(manifest,dict)
            or manifest.get("schema")!="skeleton.game.original_ecology.v1"
            or manifest.get("receipt_digest")!=_digest({
                k:v for k,v in manifest.items() if k!="receipt_digest"
            })):
        raise ExpeditionError("ecology scene source is invalid")
    if type(frame) is not int or not 0<=frame<=10**10 or type(fps) is not int or not 1<=fps<=240:
        raise ExpeditionError("ecology frame clock invalid")
    if type(wind_mps) not in (float,int) or not isfinite(wind_mps) or not -100<=wind_mps<=100:
        raise ExpeditionError("ecology wind value must be finite")
    if not isinstance(manifest.get("instances"),list) or len(manifest["instances"])>8192:
        raise ExpeditionError("ecology scene too large to simulate")
    t=frame/fps
    out=[]
    for item in manifest["instances"]:
        shift=sin(t*1.1+item["phase"])*item["response"]*wind_mps*.03
        out.append({"id":item["id"],"angle_rad":round(shift,6),
                    "growth":item["scale"]})
    record={
        "schema":"skeleton.game.ecology_frame_v1",
        "source":manifest["receipt_digest"],"frame":frame,
        "fps":fps,"wind_mps":wind_mps,"plants":out,
        "native_draw_calls_measured":False,
    }
    record["receipt_digest"]=_digest(record)
    return record


_GODOT_ECOLOGY = """extends Node3D
# Original flora MultiMesh geometry and weather-dependent motion.
const SOURCE = "res://game/frontier/ecology.json"
var foliage: MultiMeshInstance3D
var plants: Array = []
var elapsed: float = 0.0
var wind: float = 5.0

func _ready() -> void:
    if not FileAccess.file_exists(SOURCE):
        return
    var data = JSON.parse_string(FileAccess.get_file_as_string(SOURCE))
    if typeof(data) != TYPE_DICTIONARY:
        push_error("Invalid original foliage scene")
        return
    if str(data.get("schema", "")) != "skeleton.game.original_ecology.v1":
        push_error("Foreign ecosystem source")
        return
    if str(data.get("world_digest", "")) != str(get_meta("expected_world", "")):
        push_error("Foliage world source is not owned by this game")
        return
    plants = data.get("instances", [])
    if plants.size() > 8192 or plants.is_empty():
        push_error("Ecology original scene exceeds bounded instance budget")
        return
    var geom := CylinderMesh.new()
    geom.top_radius = 0.03
    geom.bottom_radius = 0.13
    geom.height = 1.2
    var cloud := MultiMesh.new()
    cloud.transform_format = MultiMesh.TRANSFORM_3D
    cloud.mesh = geom
    cloud.instance_count = plants.size()
    foliage = MultiMeshInstance3D.new()
    foliage.multimesh = cloud
    add_child(foliage)
    _draw_original_flora()
    print("EXPEDITION_ECOLOGY_READY " + str(data.get("world_digest", "")) + " " + str(plants.size()))

func _draw_original_flora() -> void:
    if foliage == null:
        return
    for i in range(plants.size()):
        var plant: Dictionary = plants[i]
        var angle: float = sin(elapsed*1.1+float(plant["phase"])) * float(plant["response"]) * wind * .03
        var basis := Basis(Vector3.FORWARD,angle).scaled(Vector3.ONE*float(plant["scale"]))
        var position := Vector3(float(plant["x"]),float(plant["y"]),float(plant["z"]))
        foliage.multimesh.set_instance_transform(i,Transform3D(basis,position))

func _process(delta: float) -> void:
    elapsed += delta
    _draw_original_flora()
"""


def export_ecology_godot(world:ExpeditionWorld,policy:EcologyPolicy=EcologyPolicy())->dict[str,str]:
    result=generate_original_ecology(world,policy)
    return {
        "game/frontier/ecology.json":_json(result).decode("utf-8"),
        "game/frontier/ecology.gd":_GODOT_ECOLOGY,
    }
