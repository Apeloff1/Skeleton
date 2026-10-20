"""Two-link articulated inverse kinematics with source-bound, constrained feet.

Solves the target analytically in game-space, emits original joint coordinates
and root/target/source receipts, and rejects unreachable targets unless clamping
was explicitly requested. Does not pretend to have measured native biomechanics.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from math import atan2,acos,cos,sin,hypot,degrees,isfinite,pi
from .game_frontier_expedition import ExpeditionError,_digest
from .game_frontier_expedition_animation import Rig,Bone

@dataclass(frozen=True,slots=True)
class LimbTarget:
    actor:str
    upper:str
    lower:str
    root_x:float
    root_y:float
    target_x:float
    target_y:float
    bend:int=1
    clamp_unreachable:bool=False
    def __post_init__(self):
        for key in ("actor","upper","lower"):
            val=getattr(self,key)
            if not isinstance(val,str) or not val.isidentifier():
                raise ExpeditionError("IK target has invalid original rig identity")
        if any(type(getattr(self,k)) not in (float,int) or not isfinite(getattr(self,k)) or abs(getattr(self,k))>1e5
               for k in ("root_x","root_y","target_x","target_y")):
            raise ExpeditionError("IK target coordinates must be finite game positions")
        if type(self.bend) is not int or self.bend not in (-1,1):
            raise ExpeditionError("IK joint bend side invalid")
        if type(self.clamp_unreachable) is not bool:
            raise ExpeditionError("IK reach clamp must be explicit")

def solve_limb_ik(rig:Rig,target:LimbTarget)->dict:
    if not isinstance(rig,Rig) or not isinstance(target,LimbTarget) or target.actor!=rig.actor_id:
        raise ExpeditionError("IK solver needs authoritative actor rig")
    nodes={bone.name:bone for bone in rig.bones}
    if target.upper not in nodes or target.lower not in nodes or nodes[target.lower].parent!=target.upper:
        raise ExpeditionError("IK chain cannot skip disconnected bone joints")
    a,b=nodes[target.upper].length_m,nodes[target.lower].length_m
    dx=target.target_x-target.root_x
    dy=target.target_y-target.root_y
    raw=hypot(dx,dy)
    minimum=abs(a-b)+1e-7
    maximum=a+b-1e-7
    if (raw<minimum or raw>maximum) and not target.clamp_unreachable:
        raise ExpeditionError("IK requested an unreachable target")
    reach=max(minimum,min(maximum,raw))
    angle=atan2(dy,dx) if raw>1e-9 else 0.
    cosine=max(-1.,min(1.,(a*a+reach*reach-b*b)/(2*a*reach)))
    shoulder=angle+target.bend*acos(cosine)
    knee_x=target.root_x+a*cos(shoulder)
    knee_y=target.root_y+a*sin(shoulder)
    direction=atan2(target.target_y-knee_y,target.target_x-knee_x)
    if raw!=reach:
        end_x=target.root_x+reach*cos(angle)
        end_y=target.root_y+reach*sin(angle)
        direction=atan2(end_y-knee_y,end_x-knee_x)
    else:
        end_x,end_y=target.target_x,target.target_y
    # Joint limits here represent absolute motor excursions from the canonical rest axis.
    shoulder_degrees=((degrees(shoulder)+180)%360)-180
    relative=((degrees(direction-shoulder)+180)%360)-180
    # Legs rest pointing downward; authored joint angles are relative to that axis.
    motor_angle=((shoulder_degrees+90+180)%360)-180 if target.upper.endswith("_leg") else shoulder_degrees
    if abs(motor_angle)>nodes[target.upper].limit_deg or abs(relative)>nodes[target.lower].limit_deg:
        raise ExpeditionError("IK solution exceeds authored joint limits")
    result={
        "schema":"skeleton.game.analytic_ik.v1","world":rig.world_digest,"rig":rig.digest,
        "target":asdict(target),
        "joint":{"x":round(knee_x,7),"y":round(knee_y,7)},
        "end":{"x":round(end_x,7),"y":round(end_y,7)},
        "angles_deg":[round(shoulder_degrees,7),round(relative,7)],
        "error_m":round(hypot(end_x-target.target_x,end_y-target.target_y),7),
        "clamped":raw!=reach,"native_ik_verified":False,
    }
    result["receipt_digest"]=_digest(result)
    return result

def solve_foot_plant(rig:Rig,*,frame:int,ground_y:float=-1.0)->dict:
    if type(frame) is not int or not 0<=frame<=100000 or type(ground_y) not in (int,float) or not isfinite(ground_y):
        raise ExpeditionError("IK foot ground/frame invalid")
    # A shorter reachable stride produces a stable planted foot while pelvis advances.
    phase=(frame%60)/60
    x=(phase-.5)*.14
    root_y=ground_y+1.15
    results={}
    for side in ("left","right"):
        upper=next(b for b in rig.bones if b.name==side+"_leg")
        # The original single-bone leg is complemented by a virtual ankle link
        # with the same source digest and strict mechanical reach.
        virtual=Rig(rig.world_digest,rig.actor_id,rig.bones+(
            Bone(side+"_shin",side+"_leg",.50,2.,170.),))
        result=solve_limb_ik(virtual,LimbTarget(
            rig.actor_id,side+"_leg",side+"_shin",x,root_y,
            x+(.04 if side=="left" else -.04),ground_y,1,True))
        results[side]=result
    proof={"schema":"skeleton.game.foot_plant.v1","rig":rig.digest,
           "frame":frame,"ground_y":ground_y,"feet":results,
           "native_colliders_verified":False}
    proof["receipt_digest"]=_digest(proof)
    return proof
