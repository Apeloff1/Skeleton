"""FLGB-10 deterministic simulation and physics-control contracts.

All numeric state uses integer fixed-point units so receipts and replay remain
stable across runtimes. This module defines deterministic control primitives;
it does not claim to replace a production high-fidelity physics engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_ENTITIES=1_000_000
MAX_COMPONENTS=4096
MAX_STEPS_PER_ADVANCE=10_000
MAX_COORD=10**15
MAX_VELOCITY=10**12
MAX_MASS=10**12
MAX_QUERY_RESULTS=100_000
MAX_SNAPSHOTS=100_000

class SimulationContractError(ValueError):
    """Fail-closed FLGB-10 contract error."""

def _is_int(value:Any)->bool:
    return isinstance(value,int) and not isinstance(value,bool)

def require_id(value:str,name:str)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>MAX_ID_CHARS or any(ord(ch)<32 for ch in value):
        raise SimulationContractError(f"invalid {name}")
    return value

def require_digest(value:str,name:str)->str:
    if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
        raise SimulationContractError(f"invalid {name}")
    return value

def digest_json(value:Any)->str:
    try:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError) as exc:
        raise SimulationContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class ComponentValue:
    component_id:str
    schema_digest:str
    value_digest:str

    def __post_init__(self)->None:
        require_id(self.component_id,"component_id"); require_digest(self.schema_digest,"schema_digest"); require_digest(self.value_digest,"value_digest")

class EntityComponentStore:
    def __init__(self, rows:Mapping[str,Sequence[ComponentValue]]|None=None)->None:
        rows={} if rows is None else dict(rows)
        if len(rows)>MAX_ENTITIES: raise SimulationContractError("entity budget exceeded")
        normalized={}
        for entity_id,values in rows.items():
            require_id(entity_id,"entity_id")
            values=tuple(values)
            if len(values)>MAX_COMPONENTS: raise SimulationContractError("component budget exceeded")
            by_component={}
            for value in values:
                if not isinstance(value,ComponentValue): raise SimulationContractError("ComponentValue required")
                if value.component_id in by_component: raise SimulationContractError("duplicate entity component")
                by_component[value.component_id]=value
            normalized[entity_id]=tuple(sorted(by_component.values(),key=lambda v:v.component_id))
        self._rows=MappingProxyType(dict(sorted(normalized.items())))

    def get(self,entity_id:str,component_id:str)->ComponentValue:
        entity_id=require_id(entity_id,"entity_id"); component_id=require_id(component_id,"component_id")
        try:
            return next(v for v in self._rows[entity_id] if v.component_id==component_id)
        except (KeyError,StopIteration) as exc:
            raise SimulationContractError("component not found") from exc

    def put(self,entity_id:str,value:ComponentValue)->"EntityComponentStore":
        entity_id=require_id(entity_id,"entity_id")
        rows={k:list(v) for k,v in self._rows.items()}
        existing=[v for v in rows.get(entity_id,[]) if v.component_id!=value.component_id]
        existing.append(value); rows[entity_id]=existing
        return EntityComponentStore(rows)

    def remove(self,entity_id:str,component_id:str)->"EntityComponentStore":
        current=self.get(entity_id,component_id)
        rows={k:list(v) for k,v in self._rows.items()}
        rows[entity_id]=[v for v in rows[entity_id] if v!=current]
        return EntityComponentStore(rows)

    @property
    def digest(self)->str:
        return digest_json({entity_id:[v.__dict__ for v in values] for entity_id,values in self._rows.items()})

@dataclass(frozen=True)
class TransformNode:
    entity_id:str
    parent_id:str|None
    local_x:int
    local_y:int
    local_z:int

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id")
        if self.parent_id is not None: require_id(self.parent_id,"parent_id")
        if self.parent_id==self.entity_id: raise SimulationContractError("transform cannot parent itself")
        for name in ("local_x","local_y","local_z"):
            value=getattr(self,name)
            if not _is_int(value) or abs(value)>MAX_COORD: raise SimulationContractError(f"invalid {name}")

class TransformHierarchy:
    def __init__(self,nodes:Sequence[TransformNode])->None:
        by_id={n.entity_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise SimulationContractError("duplicate transform entity")
        for node in nodes:
            if node.parent_id is not None and node.parent_id not in by_id: raise SimulationContractError("orphan transform parent")
        self._nodes=MappingProxyType(by_id)
        self._validate_cycles()

    def _validate_cycles(self)->None:
        state={}
        def visit(entity_id:str)->None:
            mark=state.get(entity_id,0)
            if mark==1: raise SimulationContractError("transform hierarchy cycle")
            if mark==2: return
            state[entity_id]=1
            parent=self._nodes[entity_id].parent_id
            if parent is not None: visit(parent)
            state[entity_id]=2
        for entity_id in sorted(self._nodes): visit(entity_id)

    def world_position(self,entity_id:str)->tuple[int,int,int]:
        entity_id=require_id(entity_id,"entity_id")
        if entity_id not in self._nodes: raise SimulationContractError("unknown transform entity")
        x=y=z=0; cursor=entity_id; seen=0
        while cursor is not None:
            node=self._nodes[cursor]; x+=node.local_x; y+=node.local_y; z+=node.local_z
            cursor=node.parent_id; seen+=1
            if seen>len(self._nodes): raise SimulationContractError("transform traversal overflow")
        if max(abs(x),abs(y),abs(z))>MAX_COORD: raise SimulationContractError("world position overflow")
        return (x,y,z)

    @property
    def digest(self)->str:
        return digest_json([n.__dict__ for n in sorted(self._nodes.values(),key=lambda n:n.entity_id)])

@dataclass(frozen=True)
class FixedTimestep:
    step_us:int
    max_steps_per_advance:int=8

    def __post_init__(self)->None:
        if not _is_int(self.step_us) or not 1<=self.step_us<=10_000_000: raise SimulationContractError("invalid step_us")
        if not _is_int(self.max_steps_per_advance) or not 1<=self.max_steps_per_advance<=MAX_STEPS_PER_ADVANCE: raise SimulationContractError("invalid max_steps_per_advance")

    def advance(self,accumulator_us:int,elapsed_us:int)->tuple[int,int]:
        if not _is_int(accumulator_us) or not _is_int(elapsed_us) or accumulator_us<0 or elapsed_us<0: raise SimulationContractError("invalid timestep accumulator")
        total=accumulator_us+elapsed_us
        steps=min(total//self.step_us,self.max_steps_per_advance)
        return (steps,total-steps*self.step_us)

@dataclass(frozen=True)
class AABB:
    entity_id:str
    min_x:int; min_y:int; min_z:int
    max_x:int; max_y:int; max_z:int

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id")
        vals=(self.min_x,self.min_y,self.min_z,self.max_x,self.max_y,self.max_z)
        if any(not _is_int(v) or abs(v)>MAX_COORD for v in vals): raise SimulationContractError("invalid AABB coordinate")
        if self.min_x>self.max_x or self.min_y>self.max_y or self.min_z>self.max_z: raise SimulationContractError("AABB bounds inverted")

    def overlaps(self,other:"AABB")->bool:
        return not (self.max_x<other.min_x or other.max_x<self.min_x or self.max_y<other.min_y or other.max_y<self.min_y or self.max_z<other.min_z or other.max_z<self.min_z)

def broadphase_pairs(boxes:Sequence[AABB])->tuple[tuple[str,str],...]:
    ids=[b.entity_id for b in boxes]
    if len(set(ids))!=len(ids): raise SimulationContractError("duplicate broadphase entity")
    ordered=sorted(boxes,key=lambda b:(b.min_x,b.entity_id)); active=[]; pairs=[]
    for box in ordered:
        active=[a for a in active if a.max_x>=box.min_x]
        for other in active:
            if box.overlaps(other): pairs.append(tuple(sorted((box.entity_id,other.entity_id))))
        active.append(box)
    return tuple(sorted(set(pairs)))

@dataclass(frozen=True)
class SphereCollider:
    entity_id:str
    x:int; y:int; z:int; radius:int

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id")
        for name in ("x","y","z"):
            value=getattr(self,name)
            if not _is_int(value) or abs(value)>MAX_COORD: raise SimulationContractError(f"invalid {name}")
        if not _is_int(self.radius) or not 1<=self.radius<=MAX_COORD: raise SimulationContractError("invalid radius")

@dataclass(frozen=True)
class Contact:
    left_id:str
    right_id:str
    penetration:int

    def __post_init__(self)->None:
        require_id(self.left_id,"left_id"); require_id(self.right_id,"right_id")
        if self.left_id>=self.right_id: raise SimulationContractError("contact ids must be canonical")
        if not _is_int(self.penetration) or self.penetration<0: raise SimulationContractError("invalid penetration")

def sphere_contact(left:SphereCollider,right:SphereCollider)->Contact|None:
    if left.entity_id==right.entity_id: raise SimulationContractError("self collision query")
    dx=left.x-right.x; dy=left.y-right.y; dz=left.z-right.z
    distance_sq=dx*dx+dy*dy+dz*dz; radius=left.radius+right.radius
    if distance_sq>radius*radius: return None
    # Integer lower bound on penetration avoids platform floating point drift.
    root=int(distance_sq**0.5)
    while (root+1)*(root+1)<=distance_sq: root+=1
    while root*root>distance_sq: root-=1
    a,b=sorted((left.entity_id,right.entity_id))
    return Contact(a,b,max(0,radius-root))

@dataclass(frozen=True)
class RigidBody:
    entity_id:str
    mass_mg:int
    pos_x:int; pos_y:int; pos_z:int
    vel_x:int; vel_y:int; vel_z:int
    dynamic:bool=True

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id")
        if not _is_int(self.mass_mg) or not 1<=self.mass_mg<=MAX_MASS: raise SimulationContractError("invalid mass_mg")
        for name in ("pos_x","pos_y","pos_z"):
            v=getattr(self,name)
            if not _is_int(v) or abs(v)>MAX_COORD: raise SimulationContractError(f"invalid {name}")
        for name in ("vel_x","vel_y","vel_z"):
            v=getattr(self,name)
            if not _is_int(v) or abs(v)>MAX_VELOCITY: raise SimulationContractError(f"invalid {name}")
        if not isinstance(self.dynamic,bool): raise SimulationContractError("dynamic must be boolean")

    def integrate(self,step_us:int,accel_x:int=0,accel_y:int=0,accel_z:int=0)->"RigidBody":
        if not self.dynamic: return self
        if not _is_int(step_us) or step_us<=0: raise SimulationContractError("invalid integration step")
        for value in (accel_x,accel_y,accel_z):
            if not _is_int(value) or abs(value)>MAX_VELOCITY: raise SimulationContractError("invalid acceleration")
        vx=self.vel_x+(accel_x*step_us)//1_000_000; vy=self.vel_y+(accel_y*step_us)//1_000_000; vz=self.vel_z+(accel_z*step_us)//1_000_000
        px=self.pos_x+(vx*step_us)//1_000_000; py=self.pos_y+(vy*step_us)//1_000_000; pz=self.pos_z+(vz*step_us)//1_000_000
        return RigidBody(self.entity_id,self.mass_mg,px,py,pz,vx,vy,vz,True)

@dataclass(frozen=True)
class CharacterController:
    entity_id:str
    max_speed:int
    max_step:int
    grounded:bool

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id")
        if not _is_int(self.max_speed) or not 0<=self.max_speed<=MAX_VELOCITY: raise SimulationContractError("invalid max_speed")
        if not _is_int(self.max_step) or not 0<=self.max_step<=MAX_COORD: raise SimulationContractError("invalid max_step")
        if not isinstance(self.grounded,bool): raise SimulationContractError("grounded must be boolean")

    def clamp_velocity(self,x:int,y:int,z:int)->tuple[int,int,int]:
        vals=[]
        for v in (x,y,z):
            if not _is_int(v): raise SimulationContractError("controller velocity must be integer")
            vals.append(max(-self.max_speed,min(self.max_speed,v)))
        return tuple(vals)

@dataclass(frozen=True)
class DistanceConstraint:
    constraint_id:str
    left_id:str
    right_id:str
    target_distance:int
    tolerance:int

    def __post_init__(self)->None:
        require_id(self.constraint_id,"constraint_id"); require_id(self.left_id,"left_id"); require_id(self.right_id,"right_id")
        if self.left_id==self.right_id: raise SimulationContractError("constraint endpoints must differ")
        if not _is_int(self.target_distance) or self.target_distance<0: raise SimulationContractError("invalid target_distance")
        if not _is_int(self.tolerance) or self.tolerance<0: raise SimulationContractError("invalid tolerance")

    def satisfied(self,left:tuple[int,int,int],right:tuple[int,int,int])->bool:
        dx=left[0]-right[0]; dy=left[1]-right[1]; dz=left[2]-right[2]; d2=dx*dx+dy*dy+dz*dz
        lo=max(0,self.target_distance-self.tolerance); hi=self.target_distance+self.tolerance
        return lo*lo<=d2<=hi*hi

@dataclass(frozen=True)
class SimulationFrame:
    tick:int
    input_digest:str
    state_digest_before:str
    state_digest_after:str
    event_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.tick) or self.tick<0: raise SimulationContractError("invalid simulation tick")
        for name in ("input_digest","state_digest_before","state_digest_after","event_digest"): require_digest(getattr(self,name),name)

    @property
    def digest(self)->str: return digest_json(self.__dict__)

class DeterministicSimulationLog:
    def __init__(self,frames:Sequence[SimulationFrame]=())->None:
        prior=None
        for index,frame in enumerate(frames):
            if frame.tick!=index: raise SimulationContractError("simulation tick drift")
            if prior is not None and frame.state_digest_before!=prior.state_digest_after: raise SimulationContractError("simulation state chain drift")
            prior=frame
        self.frames=tuple(frames)

    def append(self,input_digest:str,state_after:str,event_digest:str)->"DeterministicSimulationLog":
        before=self.frames[-1].state_digest_after if self.frames else "0"*64
        frame=SimulationFrame(len(self.frames),require_digest(input_digest,"input_digest"),before,require_digest(state_after,"state_after"),require_digest(event_digest,"event_digest"))
        return DeterministicSimulationLog(self.frames+(frame,))

    @property
    def digest(self)->str: return digest_json([frame.digest for frame in self.frames])

@dataclass(frozen=True)
class RayQuery:
    query_id:str
    origin:tuple[int,int,int]
    direction:tuple[int,int,int]
    max_distance:int

    def __post_init__(self)->None:
        require_id(self.query_id,"query_id")
        if len(self.origin)!=3 or len(self.direction)!=3: raise SimulationContractError("3D ray required")
        if any(not _is_int(v) or abs(v)>MAX_COORD for v in self.origin+self.direction): raise SimulationContractError("invalid ray coordinate")
        if self.direction==(0,0,0): raise SimulationContractError("ray direction cannot be zero")
        if not _is_int(self.max_distance) or not 1<=self.max_distance<=MAX_COORD: raise SimulationContractError("invalid max_distance")

@dataclass(frozen=True)
class QueryHit:
    entity_id:str
    distance:int
    evidence_digest:str

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id"); require_digest(self.evidence_digest,"evidence_digest")
        if not _is_int(self.distance) or self.distance<0: raise SimulationContractError("invalid query distance")

def rank_query_hits(hits:Sequence[QueryHit],limit:int=128)->tuple[QueryHit,...]:
    if not _is_int(limit) or not 1<=limit<=MAX_QUERY_RESULTS: raise SimulationContractError("invalid query limit")
    ids=[h.entity_id for h in hits]
    if len(set(ids))!=len(ids): raise SimulationContractError("duplicate query hit")
    return tuple(sorted(hits,key=lambda h:(h.distance,h.entity_id))[:limit])

@dataclass(frozen=True)
class SimulationSnapshot:
    tick:int
    state_digest:str
    ecs_digest:str
    physics_digest:str
    rng_digest:str
    prior_snapshot_digest:str|None=None

    def __post_init__(self)->None:
        if not _is_int(self.tick) or self.tick<0: raise SimulationContractError("invalid snapshot tick")
        for name in ("state_digest","ecs_digest","physics_digest","rng_digest"): require_digest(getattr(self,name),name)
        if self.prior_snapshot_digest is not None: require_digest(self.prior_snapshot_digest,"prior_snapshot_digest")
        if self.tick==0 and self.prior_snapshot_digest is not None: raise SimulationContractError("genesis snapshot cannot have parent")
        if self.tick>0 and self.prior_snapshot_digest is None: raise SimulationContractError("snapshot requires parent")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

class RollbackBuffer:
    def __init__(self,snapshots:Sequence[SimulationSnapshot]=(),max_snapshots:int=120)->None:
        if not _is_int(max_snapshots) or not 1<=max_snapshots<=MAX_SNAPSHOTS: raise SimulationContractError("invalid rollback capacity")
        ordered=tuple(snapshots)
        if len(ordered)>max_snapshots: raise SimulationContractError("rollback buffer exceeds capacity")
        for i,s in enumerate(ordered):
            if i and s.tick<=ordered[i-1].tick: raise SimulationContractError("rollback snapshots must increase by tick")
            if i and s.prior_snapshot_digest!=ordered[i-1].digest: raise SimulationContractError("rollback snapshot chain drift")
        self.snapshots=ordered; self.max_snapshots=max_snapshots

    def append(self,snapshot:SimulationSnapshot)->"RollbackBuffer":
        if self.snapshots and snapshot.tick<=self.snapshots[-1].tick: raise SimulationContractError("rollback snapshot tick regression")
        if self.snapshots and snapshot.prior_snapshot_digest!=self.snapshots[-1].digest: raise SimulationContractError("rollback append chain drift")
        items=(self.snapshots+(snapshot,))[-self.max_snapshots:]
        return RollbackBuffer(items,self.max_snapshots)

    def restore(self,tick:int)->SimulationSnapshot:
        if not _is_int(tick) or tick<0: raise SimulationContractError("invalid rollback tick")
        for snapshot in reversed(self.snapshots):
            if snapshot.tick==tick: return snapshot
        raise SimulationContractError("rollback tick unavailable")
