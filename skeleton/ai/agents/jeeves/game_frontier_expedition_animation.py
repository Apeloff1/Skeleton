"""Deterministic skeletal rigging, blended animation and elastic skin simulation.

Runs source-bound authored body poses in fixed 60 Hz steps. The soft-skin
wrapper uses a bounded spring/damper with collision clamp, not an unsupported
claim of full FEM biomechanics. A Godot Node3D rig plays the same source keys.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from math import isfinite, sin, pi
from .game_frontier_expedition import ExpeditionError,_digest,_json

def _finite(value,minimum=-1e4,maximum=1e4):
    return type(value) in (int,float) and isfinite(value) and minimum<=value<=maximum

@dataclass(frozen=True, slots=True)
class Bone:
    name:str
    parent:str
    length_m:float
    mass_kg:float
    limit_deg:float=70.
    def __post_init__(self):
        if not isinstance(self.name,str) or not self.name.isidentifier():
            raise ExpeditionError("skeletal bone identity invalid")
        if not isinstance(self.parent,str) or self.parent and not self.parent.isidentifier():
            raise ExpeditionError("skeletal parent identity invalid")
        if not _finite(self.length_m,.02,5.) or not _finite(self.mass_kg,.01,200.):
            raise ExpeditionError("skeletal length/mass invalid")
        if not _finite(self.limit_deg,1.,170.):
            raise ExpeditionError("skeletal joint rotation limit invalid")

@dataclass(frozen=True,slots=True)
class Rig:
    world_digest:str
    actor_id:str
    bones:tuple[Bone,...]
    def __post_init__(self):
        if (type(self.world_digest) is not str or len(self.world_digest)!=64
                or type(self.actor_id) is not str or not self.actor_id.isidentifier()
                or type(self.bones) is not tuple or not 2<=len(self.bones)<=128):
            raise ExpeditionError("original skeletal rig needs bounded world and actor")
        nodes=set()
        roots=0
        for bone in self.bones:
            if not isinstance(bone,Bone) or bone.name in nodes:
                raise ExpeditionError("duplicate or invalid skeletal bone")
            if bone.parent:
                if bone.parent not in nodes:
                    raise ExpeditionError("skeletal parents must precede children")
            else:
                roots+=1
            nodes.add(bone.name)
        if roots!=1:
            raise ExpeditionError("skeletal tree must have exactly one root")
    @property
    def digest(self):
        return _digest({"schema":"skeleton.game.original_skeleton.v1",
                        "world":self.world_digest,"actor":self.actor_id,
                        "bones":[asdict(b) for b in self.bones]})
    def as_dict(self):
        return {"schema":"skeleton.game.original_skeleton.v1",
                "world_digest":self.world_digest,"actor_id":self.actor_id,
                "bones":[asdict(b) for b in self.bones],"rig_digest":self.digest}

@dataclass(frozen=True,slots=True)
class PoseKey:
    frame:int
    angles:tuple[float,...]
    root_height:float=0.
    def __post_init__(self):
        if type(self.frame) is not int or not 0<=self.frame<=216000:
            raise ExpeditionError("skeletal pose frame out of range")
        if (type(self.angles) is not tuple or not 2<=len(self.angles)<=128
                or any(not _finite(x,-170,170) for x in self.angles)
                or not _finite(self.root_height,-5,5)):
            raise ExpeditionError("skeletal pose angles invalid")

@dataclass(frozen=True,slots=True)
class AnimationClip:
    name:str
    rig_digest:str
    duration_frames:int
    keys:tuple[PoseKey,...]
    def __post_init__(self):
        if type(self.name) is not str or not self.name.isidentifier():
            raise ExpeditionError("animation identity invalid")
        if type(self.rig_digest) is not str or len(self.rig_digest)!=64:
            raise ExpeditionError("animation has no original skeletal source")
        if (type(self.duration_frames) is not int or not 2<=self.duration_frames<=216000
                or type(self.keys) is not tuple or not 2<=len(self.keys)<=256
                or self.keys[0].frame!=0
                or self.keys[-1].frame!=self.duration_frames-1):
            raise ExpeditionError("animation has incomplete authored frame keys")
        if any(a.frame>=b.frame or len(a.angles)!=len(b.angles)
               for a,b in zip(self.keys,self.keys[1:])):
            raise ExpeditionError("animation keyframe ordering invalid")
    @property
    def digest(self):
        return _digest({"name":self.name,"rig":self.rig_digest,
                        "duration":self.duration_frames,
                        "keys":[asdict(k) for k in self.keys]})

def sample_pose(rig:Rig,clip:AnimationClip,frame:int)->dict:
    if not isinstance(rig,Rig) or not isinstance(clip,AnimationClip) or clip.rig_digest!=rig.digest:
        raise ExpeditionError("animation clip belongs to another skeleton")
    if type(frame) is not int or not 0<=frame<clip.duration_frames:
        raise ExpeditionError("animation source frame out of range")
    for a,b in zip(clip.keys,clip.keys[1:]):
        if a.frame<=frame<=b.frame:
            if len(a.angles)!=len(rig.bones):
                raise ExpeditionError("authored animation does not cover all bones")
            weight=(frame-a.frame)/(b.frame-a.frame)
            angles=tuple(round(x+(y-x)*weight,6)
                         for x,y in zip(a.angles,b.angles))
            for bone,angle in zip(rig.bones,angles):
                if abs(angle)>bone.limit_deg:
                    raise ExpeditionError("animation violates modeled joint limit")
            data={"schema":"skeleton.game.pose.v1","rig":rig.digest,
                  "animation":clip.digest,"frame":frame,"angles":angles,
                  "root_height":round(a.root_height+(b.root_height-a.root_height)*weight,6)}
            data["receipt_digest"]=_digest(data)
            return data
    raise ExpeditionError("animation has no frame interpolation interval")

def blend_poses(rig:Rig,a:dict,b:dict,weight:float)->dict:
    if not isinstance(rig,Rig) or not _finite(weight,0,1):
        raise ExpeditionError("skeletal animation blending weight invalid")
    if any(not isinstance(x,dict) or x.get("rig")!=rig.digest
           or len(x.get("angles",()))!=len(rig.bones) for x in (a,b)):
        raise ExpeditionError("blending foreign or partial skeleton")
    angles=tuple(round(x*(1-weight)+y*weight,6)
                 for x,y in zip(a["angles"],b["angles"]))
    data={"schema":"skeleton.game.pose_blend.v1","rig":rig.digest,
          "sources":[a["receipt_digest"],b["receipt_digest"]],
          "weight":weight,"angles":angles}
    data["receipt_digest"]=_digest(data)
    return data

@dataclass(frozen=True,slots=True)
class SkinPolicy:
    stiffness:float=28.
    damping:float=8.
    max_offset_m:float=.17
    fixed_dt:float=1./60
    def __post_init__(self):
        if not ( _finite(self.stiffness,0.1,250) and _finite(self.damping,.01,70)
                and _finite(self.max_offset_m,.001,1) and _finite(self.fixed_dt,.001,.0334)):
            raise ExpeditionError("elastic body skin material parameters invalid")

def simulate_elastic_skin(rig:Rig,clip:AnimationClip,*,frames:int=90,
                          policy:SkinPolicy=SkinPolicy())->dict:
    if (not isinstance(rig,Rig) or not isinstance(clip,AnimationClip)
            or not isinstance(policy,SkinPolicy) or type(frames) is not int
            or not 1<=frames<=min(clip.duration_frames,1800)):
        raise ExpeditionError("elastic skin integration frame budget invalid")
    offsets=[0.]*len(rig.bones)
    speeds=[0.]*len(rig.bones)
    previous=[0.]*len(rig.bones)
    prior=_digest({"rig":rig.digest,"clip":clip.digest,"skin_genesis":True})
    samples=[]
    for frame in range(frames):
        pose=sample_pose(rig,clip,frame)
        for i,(bone,angle) in enumerate(zip(rig.bones,pose["angles"])):
            change=(angle-previous[i])/max(1,bone.limit_deg)
            acceleration=change*2-policy.stiffness*offsets[i]-policy.damping*speeds[i]
            speeds[i]+=acceleration*policy.fixed_dt
            offsets[i]=max(-policy.max_offset_m,min(policy.max_offset_m,
                          offsets[i]+speeds[i]*policy.fixed_dt))
            previous[i]=angle
        row={"frame":frame,"pose":pose["receipt_digest"],
             "skin_offsets":tuple(round(v,7) for v in offsets),"prior":prior}
        prior=_digest(row)
        samples.append({**row,"receipt_digest":prior})
    result={"schema":"skeleton.game.elasticbodyskin3d.v1",
            "rig":rig.digest,"animation":clip.digest,"skin":asdict(policy),
            "frames":frames,"samples":samples,
            "head":prior,"native_soft_tissue_validated":False,
            "collision_floor_enforced":True}
    result["receipt_digest"]=_digest(result)
    return result

def original_actor_rig(world_digest:str)->tuple[Rig,AnimationClip]:
    bones=(Bone("hips","",.45,12.,40),Bone("spine","hips",.62,16.,35),
           Bone("head","spine",.26,5.,35),
           Bone("left_arm","spine",.66,3.,70),Bone("right_arm","spine",.66,3.,70),
           Bone("left_leg","hips",.9,8.,60),Bone("right_leg","hips",.9,8.,60))
    rig=Rig(world_digest,"original_wayfarer",bones)
    clip=AnimationClip("walk_cycle",rig.digest,60,(
        PoseKey(0,(0,0,0,18,-18,-20,20)),
        PoseKey(15,(0,2,0,0,0,0,0),.03),
        PoseKey(30,(0,0,0,-18,18,20,-20)),
        PoseKey(45,(0,2,0,0,0,0,0),.03),
        PoseKey(59,(0,0,0,18,-18,-20,20)),
    ))
    return rig,clip

_GODOT_RIG = """extends Node3D
# Original visual joint tree, authored skeletal animation and soft surface offset.
const SOURCE = "res://game/frontier/actor_rig.json"
var joints: Dictionary = {}
var source: Dictionary = {}
var tick: int = 0

func _ready() -> void:
    if not FileAccess.file_exists(SOURCE):
        return
    var decoded = JSON.parse_string(FileAccess.get_file_as_string(SOURCE))
    if typeof(decoded) != TYPE_DICTIONARY:
        push_error("Original authored skeletal source invalid")
        return
    source = decoded
    var skeleton: Dictionary = source.get("rig", {})
    if str(skeleton.get("world_digest","")) != str(get_meta("expected_world","")):
        push_error("Original skeletal actor belongs to another world")
        return
    for definition in skeleton.get("bones", []):
        var joint := Node3D.new()
        joint.name = str(definition["name"])
        var parent_name: String = str(definition.get("parent", ""))
        if parent_name == "":
            add_child(joint)
        elif joints.has(parent_name):
            joints[parent_name].add_child(joint)
        else:
            push_error("Original skeleton hierarchy disconnected")
            return
        var geometry := MeshInstance3D.new()
        var body := CapsuleMesh.new()
        body.height = float(definition["length_m"])
        body.radius = minf(.18,float(definition["length_m"])*.23)
        geometry.mesh = body
        joint.add_child(geometry)
        joints[joint.name] = joint
    print("EXPEDITION_RIG_READY " + str(skeleton.get("world_digest", "")))

func _process(_delta: float) -> void:
    var poses: Array = source.get("sampled_poses", [])
    if poses.is_empty():
        return
    var pose: Dictionary = poses[tick % poses.size()]
    var angles: Array = pose.get("angles", [])
    var names: Array = joints.keys()
    for i in range(mini(names.size(),angles.size())):
        var joint: Node3D = joints[names[i]]
        joint.rotation_degrees.z = float(angles[i])
    tick += 1
"""

def export_actor_rig_godot(rig:Rig,clip:AnimationClip)->dict[str,str]:
    if not isinstance(rig,Rig) or clip.rig_digest!=rig.digest:
        raise ExpeditionError("original skeleton rig/export source changed")
    poses=[sample_pose(rig,clip,i) for i in range(clip.duration_frames)]
    return {"game/frontier/actor_rig.json":_json({
                "schema":"skeleton.game.original_actor_rig.v1",
                "rig":rig.as_dict(),"animation":clip.digest,
                "sampled_poses":poses}).decode("utf-8"),
            "game/frontier/actor_rig.gd":_GODOT_RIG}
