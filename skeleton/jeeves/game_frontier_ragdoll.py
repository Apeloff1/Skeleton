"""Deterministic floor-colliding position-based ragdoll and constraint receipts.

Uses symplectic Verlet integration, floor impacts and fixed-length projection
on a source-bound rig. This is a reduced-order game simulation, not a
biomechanically validated full-body rigid-body solver.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from math import hypot,isfinite
from .game_frontier_expedition import ExpeditionError,_digest
from .game_frontier_expedition_animation import Rig

@dataclass(frozen=True,slots=True)
class RagdollPolicy:
    dt:float=1/60
    gravity:float=9.81
    damping:float=.04
    floor_y:float=0.
    iterations:int=8
    def __post_init__(self):
        vals=(self.dt,self.gravity,self.damping,self.floor_y)
        if any(type(x) not in (float,int) or not isfinite(x) for x in vals):
            raise ExpeditionError("ragdoll physics parameters nonfinite")
        if not (.001<=self.dt<=.025 and 0<=self.gravity<=60 and
                0<=self.damping<=.5 and -1000<=self.floor_y<=1000):
            raise ExpeditionError("ragdoll material/clock outside game constraints")
        if type(self.iterations) is not int or not 2<=self.iterations<=32:
            raise ExpeditionError("ragdoll solver iteration limit invalid")

def simulate_ragdoll(rig:Rig,*,frames:int=60,policy:RagdollPolicy=RagdollPolicy())->dict:
    if not isinstance(rig,Rig) or not isinstance(policy,RagdollPolicy) or type(frames) is not int or not 1<=frames<=3000:
        raise ExpeditionError("ragdoll frame budget or source invalid")
    n=len(rig.bones)
    positions=[]
    for i,bone in enumerate(rig.bones):
        if bone.parent:
            parent=next(j for j,other in enumerate(rig.bones) if other.name==bone.parent)
            positions.append([positions[parent][0],positions[parent][1]+bone.length_m])
        else:
            positions.append([0.,policy.floor_y+2.])
    previous=[[x,y] for x,y in positions]
    parent_index={bone.name:i for i,bone in enumerate(rig.bones)}
    previous_receipt=_digest({"rig":rig.digest,"policy":asdict(policy),"initial":positions})
    records=[]
    for tick in range(frames):
        for i,(bone,pos) in enumerate(zip(rig.bones,positions)):
            if i==0:
                continue
            x,y=pos
            vx=(x-previous[i][0])*(1-policy.damping)
            vy=(y-previous[i][1])*(1-policy.damping)
            previous[i]=[x,y]
            pos[0]+=vx
            pos[1]+=vy-policy.gravity*policy.dt*policy.dt
        for _ in range(policy.iterations):
            for i,bone in enumerate(rig.bones):
                if not bone.parent:
                    continue
                j=parent_index[bone.parent]
                px,py=positions[j]
                x,y=positions[i]
                dx,dy=x-px,y-py
                span=hypot(dx,dy)
                if span<1e-9:
                    dx,dy,span=0.,1.,1.
                error=(span-bone.length_m)/span
                if j==0:
                    positions[i][0]-=dx*error
                    positions[i][1]-=dy*error
                else:
                    positions[i][0]-=dx*error*.5
                    positions[i][1]-=dy*error*.5
                    positions[j][0]+=dx*error*.5
                    positions[j][1]+=dy*error*.5
            for i in range(n):
                positions[i][1]=max(policy.floor_y,positions[i][1])
        if any(not isfinite(v) or abs(v)>1e6 for pos in positions for v in pos):
            raise ExpeditionError("ragdoll simulation diverged from finite world")
        row={"frame":tick,"positions":[[round(x,7),round(y,7)] for x,y in positions],
             "floor":policy.floor_y,"previous":previous_receipt}
        previous_receipt=_digest(row)
        records.append({**row,"receipt_digest":previous_receipt})
    report={"schema":"skeleton.game.ragdoll_verlet.v1",
            "rig":rig.digest,"world":rig.world_digest,
            "policy":asdict(policy),"frames":frames,
            "states":records,"receipt_head":previous_receipt,
            "native_rigid_body_validated":False}
    report["receipt_digest"]=_digest(report)
    return report

def verify_ragdoll(rig:Rig,candidate:dict,*,frames:int=60,policy:RagdollPolicy=RagdollPolicy())->None:
    if candidate!=simulate_ragdoll(rig,frames=frames,policy=policy):
        raise ExpeditionError("ragdoll states do not reproduce against original rig")
