"""Authored symmetric three-dimensional articulated wing membrane topology.

The wing uses a triangular lattice between three digit rays sharing a root.
Every lattice point is derived from posed landmarks; boundary vertices are
pinned to those authored anchors, not to arbitrary frame coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from skeleton.app.recovered_evidence import EvidenceError,fields,integer,array,canonical
from skeleton.jeeves.game_frontier_production import (
    Vec3,Bone,CharacterSkeleton,SkinnedMesh,CollisionCapsule,
    AnimationClip,AnimationKeyframe,BonePose,
)
from skeleton.jeeves.game_frontier_elastic_skin3d import ElasticBodySkin3D
from skeleton.jeeves.game_frontier_dynamics import PresentationClock

ZERO=Vec3(0,0,0)
MAX_FRAMES=10_000
MAX_VERTEX_SUBSTEPS=4_000_000
MAX_EDGE_SUBSTEPS=12_000_000


def finite(value,lo,hi):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
        raise EvidenceError("wing parameter outside finite bounds")
    return float(value)


def vec(value,limit):
    return Vec3(*(finite(v,-limit,limit) for v in array(value,3,3)))


@dataclass(frozen=True)
class Phase:
    mode:str
    frames:int
    wind:Vec3
    rain:float
    temperature:float


@dataclass(frozen=True)
class Order:
    fps:int
    subdivisions:int
    span:float
    chord:float
    height:float
    frequency:float
    amplitude:float
    transition_frames:int
    checkpoint_stride:int
    phases:tuple
    frames:int
    skin:ElasticBodySkin3D
    maximum_step_m:float
    strain_limit:float


def load_order(raw):
    fields(raw,{"schema","fps","subdivisions","span_m","chord_m","body_height_m",
                "frequency_hz","amplitude_deg","transition_frames","checkpoint_stride",
                "phases","material","maximum_step_m","strain_limit"})
    if raw["schema"]!="skeleton.frontier-wing-replay.order.v1":
        raise EvidenceError("unknown wing order")
    canonical(raw)
    fps=PresentationClock(integer(raw["fps"],1,120)).fps
    subdiv=integer(raw["subdivisions"],3,24)
    span=finite(raw["span_m"],.2,8)
    chord=finite(raw["chord_m"],.1,4)
    height=finite(raw["body_height_m"],.5,20)
    amplitude=math.radians(finite(raw["amplitude_deg"],5,55))
    if height < span*math.sin(amplitude)+.25:
        raise EvidenceError("wing anchor stroke may intersect reference floor")
    phases=[]
    for row in array(raw["phases"],1,32):
        fields(row,{"mode","frames","wind","rain","temperature"})
        if row["mode"] not in ("flap","glide"):
            raise EvidenceError("unsupported flight mode")
        phases.append(Phase(row["mode"],integer(row["frames"],1,MAX_FRAMES),
                           vec(row["wind"],50),finite(row["rain"],0,1000),
                           finite(row["temperature"],-80,70)))
    frames=sum(p.frames for p in phases)
    transition=integer(raw["transition_frames"],4,240)
    if frames>MAX_FRAMES or any(p.frames<transition for p in phases):
        raise EvidenceError("phase or total frame ceiling")
    stride=integer(raw["checkpoint_stride"],1,MAX_FRAMES)
    if (frames+stride-1)//stride>256:
        raise EvidenceError("checkpoint count ceiling")
    m=fields(raw["material"],{"mass","anchor_stiffness","shear_stiffness","damping","wind_drag","water_absorption"})
    skin=ElasticBodySkin3D(mass_per_vertex_kg=finite(m["mass"],.01,1),
        anchor_stiffness_n_m=finite(m["anchor_stiffness"],1,1000),
        shear_stiffness_n_m=finite(m["shear_stiffness"],1,1000),
        damping_n_s_m=finite(m["damping"],.01,100),
        wind_drag=finite(m["wind_drag"],0,10),
        water_absorption=finite(m["water_absorption"],0,1),
        maximum_strain=finite(raw["strain_limit"],.05,.8),
        collision_ground_z_m=0.,maximum_vertices=4096)
    # Two wings, two triangular sectors each. Upper bound includes shared boundary.
    vertices=4*(subdiv+1)*(subdiv+2)//2
    edges=12*subdiv*subdiv
    substeps=math.ceil(1/fps/.005)
    if frames*vertices*substeps>MAX_VERTEX_SUBSTEPS or frames*edges*substeps>MAX_EDGE_SUBSTEPS:
        raise EvidenceError("membrane simulation workload ceiling")
    return Order(fps,subdiv,span,chord,height,finite(raw["frequency_hz"],.1,4),
                 amplitude,transition,stride,tuple(phases),frames,skin,
                 finite(raw["maximum_step_m"],.001,10),skin.maximum_strain)


def landmarks(order,side):
    # Shoulder, elbow, three digit tips. Positive/negative x are mirror wings.
    s=float(side)
    return (Vec3(0,0,order.height),Vec3(s*order.span*.45,0,order.height),
            Vec3(s*order.span,0,order.height),
            Vec3(s*order.span*.82,-order.chord*.65,order.height),
            Vec3(s*order.span*.38,-order.chord,order.height))


@dataclass(frozen=True)
class Geometry:
    skeleton:CharacterSkeleton
    mesh:SkinnedMesh
    clip:AnimationClip
    coordinates:tuple
    pins:tuple
    triangles:tuple


def create_geometry(order):
    bones=[Bone("body",-1,Vec3(0,.2,order.height),Vec3(0,-.2,order.height),.12)]
    vertices=[]
    influences=[]
    triangles=[]
    coordinates=[]
    pins=[]
    index={}
    n=order.subdivisions
    for side in (-1,1):
        root,elbow,a,b,c=landmarks(order,side)
        prefix="left" if side<0 else "right"
        base=len(bones)
        bones.extend((Bone(prefix+"_upper",0,root,elbow,.04),
            Bone(prefix+"_outer",base,elbow,a,.025),
            Bone(prefix+"_digit_mid",base,elbow,b,.018),
            Bone(prefix+"_digit_rear",base,elbow,c,.018)))
        tips=(a,b,c)
        for sector in (0,1):
            def vertex(i,j):
                # Adjacent sectors share the same interior radial seam.
                weights=[0,0,0]
                weights[sector]=i
                weights[sector+1]=j
                key=(side,*weights)
                if key in index:
                    return index[key]
                k=len(vertices)
                index[key]=k
                f=(n-i-j)/n
                pos=root.scaled(f)+tips[sector].scaled(i/n)+tips[sector+1].scaled(j/n)
                vertices.append(pos)
                influences.append(base+1+sector if i>=j else base+2+sector)
                coordinates.append((side,tuple(weights)))
                if i==0 or j==0 or i+j==n:
                    pins.append(k)
                return k
            for i in range(n):
                for j in range(n-i):
                    face=(vertex(i,j),vertex(i+1,j),vertex(i,j+1))
                    triangles.append(face if side>0 else tuple(reversed(face)))
                    if i+j<n-1:
                        face=(vertex(i+1,j),vertex(i+1,j+1),vertex(i,j+1))
                        triangles.append(face if side>0 else tuple(reversed(face)))
    skeleton=CharacterSkeleton(tuple(bones))
    caps=tuple(CollisionCapsule(i,b.head,b.tail,b.radius_m) for i,b in enumerate(bones))
    mesh=SkinnedMesh(tuple(vertices),tuple(triangles),tuple(influences),caps,"next",1.)
    poses=tuple(BonePose(ZERO) for _ in bones)
    clip=AnimationClip("explicit_wing_anchors",(AnimationKeyframe(0,poses),AnimationKeyframe(1000,poses)))
    return Geometry(skeleton,mesh,clip,tuple(coordinates),tuple(sorted(set(pins))),tuple(triangles))
