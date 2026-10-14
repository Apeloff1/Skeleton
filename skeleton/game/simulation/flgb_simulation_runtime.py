"""FLGB-10 deterministic ECS, fixed-step physics, snapshot, and rollback contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_ENTITIES=1_000_000
MAX_COMPONENT_TYPES=4096
MAX_TICK=2**63-1
MAX_COORD=10**15
MAX_BODY_VALUE=10**15
MAX_CATCHUP_TICKS=1024
MAX_SNAPSHOTS=100_000

class SimulationContractError(ValueError):
    """Fail-closed FLGB-10 contract error."""

def _is_int(v:Any)->bool:return isinstance(v,int) and not isinstance(v,bool)

def require_id(v:str,name:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID_CHARS or any(ord(c)<32 for c in v):
        raise SimulationContractError(f"invalid {name}")
    return v

def require_digest(v:str,name:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):
        raise SimulationContractError(f"invalid {name}")
    return v

def digest_json(v:Any)->str:
    try:raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode("utf-8")
    except (TypeError,ValueError) as exc:raise SimulationContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class ComponentValue:
    component_id:str
    schema_digest:str
    value_digest:str

    def __post_init__(self)->None:
        require_id(self.component_id,"component_id");require_digest(self.schema_digest,"schema_digest");require_digest(self.value_digest,"value_digest")

class EntityComponentStore:
    def __init__(self,entities:Mapping[str,Sequence[ComponentValue]]|None=None)->None:
        raw={} if entities is None else dict(entities)
        if len(raw)>MAX_ENTITIES:raise SimulationContractError("entity budget exceeded")
        normalized={}
        for entity_id,components in raw.items():
            require_id(entity_id,"entity_id")
            comps=tuple(sorted(components,key=lambda c:c.component_id))
            if len(comps)>MAX_COMPONENT_TYPES:raise SimulationContractError("component budget exceeded")
            ids=[c.component_id for c in comps]
            if len(set(ids))!=len(ids):raise SimulationContractError("duplicate entity component")
            normalized[entity_id]=comps
        self._entities=MappingProxyType(normalized)

    def components(self,entity_id:str)->tuple[ComponentValue,...]:
        return self._entities.get(require_id(entity_id,"entity_id"),())

    def set_component(self,entity_id:str,component:ComponentValue)->"EntityComponentStore":
        require_id(entity_id,"entity_id")
        current={c.component_id:c for c in self.components(entity_id)}
        current[component.component_id]=component
        data=dict(self._entities);data[entity_id]=tuple(current.values())
        return EntityComponentStore(data)

    def remove_entity(self,entity_id:str)->"EntityComponentStore":
        entity_id=require_id(entity_id,"entity_id")
        if entity_id not in self._entities:raise SimulationContractError("unknown entity")
        data=dict(self._entities);del data[entity_id]
        return EntityComponentStore(data)

    @property
    def digest(self)->str:
        return digest_json({eid:[c.__dict__ for c in comps] for eid,comps in sorted(self._entities.items())})

@dataclass(frozen=True)
class TransformNode:
    entity_id:str
    parent_id:str|None
    local_position:tuple[int,int,int]

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id")
        if self.parent_id is not None:require_id(self.parent_id,"parent_id")
        if self.parent_id==self.entity_id:raise SimulationContractError("transform cannot parent itself")
        if not isinstance(self.local_position,tuple) or len(self.local_position)!=3 or any(not _is_int(v) or abs(v)>MAX_COORD for v in self.local_position):
            raise SimulationContractError("invalid local_position")

class TransformHierarchy:
    def __init__(self,nodes:Sequence[TransformNode])->None:
        by_id={n.entity_id:n for n in nodes}
        if len(by_id)!=len(nodes):raise SimulationContractError("duplicate transform entity")
        for node in nodes:
            if node.parent_id is not None and node.parent_id not in by_id:raise SimulationContractError("unknown transform parent")
        state={}
        def visit(eid:str)->None:
            mark=state.get(eid,0)
            if mark==1:raise SimulationContractError("transform hierarchy cycle")
            if mark==2:return
            state[eid]=1
            parent=by_id[eid].parent_id
            if parent is not None:visit(parent)
            state[eid]=2
        for eid in by_id:visit(eid)
        self._nodes=MappingProxyType(by_id)

    def world_position(self,entity_id:str)->tuple[int,int,int]:
        entity_id=require_id(entity_id,"entity_id")
        if entity_id not in self._nodes:raise SimulationContractError("unknown transform entity")
        total=[0,0,0];current=entity_id
        while current is not None:
            node=self._nodes[current]
            for i,v in enumerate(node.local_position):
                total[i]+=v
                if abs(total[i])>MAX_COORD:raise SimulationContractError("world transform overflow")
            current=node.parent_id
        return tuple(total)

    @property
    def digest(self)->str:return digest_json([n.__dict__ for n in sorted(self._nodes.values(),key=lambda n:n.entity_id)])

@dataclass(frozen=True)
class FixedTimestep:
    step_ns:int
    max_catchup_ticks:int=8

    def __post_init__(self)->None:
        if not _is_int(self.step_ns) or self.step_ns<=0:raise SimulationContractError("invalid step_ns")
        if not _is_int(self.max_catchup_ticks) or not 1<=self.max_catchup_ticks<=MAX_CATCHUP_TICKS:raise SimulationContractError("invalid max_catchup_ticks")

    def consume(self,accumulator_ns:int,elapsed_ns:int)->tuple[int,int]:
        if not _is_int(accumulator_ns) or accumulator_ns<0 or not _is_int(elapsed_ns) or elapsed_ns<0:raise SimulationContractError("invalid timestep input")
        total=accumulator_ns+elapsed_ns
        ticks=min(total//self.step_ns,self.max_catchup_ticks)
        return ticks,total-ticks*self.step_ns

@dataclass(frozen=True)
class AABB:
    collider_id:str
    min_xyz:tuple[int,int,int]
    max_xyz:tuple[int,int,int]

    def __post_init__(self)->None:
        require_id(self.collider_id,"collider_id")
        for values in (self.min_xyz,self.max_xyz):
            if not isinstance(values,tuple) or len(values)!=3 or any(not _is_int(v) or abs(v)>MAX_COORD for v in values):raise SimulationContractError("invalid AABB coordinate")
        if any(a>=b for a,b in zip(self.min_xyz,self.max_xyz)):raise SimulationContractError("AABB must have positive extent")

def broadphase_pairs(boxes:Sequence[AABB])->tuple[tuple[str,str],...]:
    ids=[b.collider_id for b in boxes]
    if len(set(ids))!=len(ids):raise SimulationContractError("duplicate collider id")
    ordered=sorted(boxes,key=lambda b:(b.min_xyz[0],b.collider_id));active=[];pairs=[]
    for box in ordered:
        active=[a for a in active if a.max_xyz[0]>box.min_xyz[0]]
        for other in active:
            if all(other.min_xyz[i]<box.max_xyz[i] and box.min_xyz[i]<other.max_xyz[i] for i in (1,2)):
                pairs.append(tuple(sorted((other.collider_id,box.collider_id))))
        active.append(box)
    return tuple(sorted(set(pairs)))

@dataclass(frozen=True)
class Contact:
    left_id:str
    right_id:str
    penetration_xyz:tuple[int,int,int]

    def __post_init__(self)->None:
        require_id(self.left_id,"left_id");require_id(self.right_id,"right_id")
        if self.left_id==self.right_id:raise SimulationContractError("contact requires distinct colliders")
        if not isinstance(self.penetration_xyz,tuple) or len(self.penetration_xyz)!=3 or any(not _is_int(v) or v<=0 for v in self.penetration_xyz):raise SimulationContractError("invalid penetration")

def narrowphase_aabb(left:AABB,right:AABB)->Contact|None:
    penetration=tuple(min(left.max_xyz[i],right.max_xyz[i])-max(left.min_xyz[i],right.min_xyz[i]) for i in range(3))
    if any(v<=0 for v in penetration):return None
    ids=sorted((left.collider_id,right.collider_id))
    return Contact(ids[0],ids[1],penetration)

@dataclass(frozen=True)
class RigidBody:
    body_id:str
    mass_milli:int
    position:tuple[int,int,int]
    velocity_per_sec:tuple[int,int,int]
    dynamic:bool=True

    def __post_init__(self)->None:
        require_id(self.body_id,"body_id")
        if not _is_int(self.mass_milli) or self.mass_milli<=0 or self.mass_milli>MAX_BODY_VALUE:raise SimulationContractError("invalid mass_milli")
        for name in ("position","velocity_per_sec"):
            values=getattr(self,name)
            if not isinstance(values,tuple) or len(values)!=3 or any(not _is_int(v) or abs(v)>MAX_BODY_VALUE for v in values):raise SimulationContractError(f"invalid {name}")
        if not isinstance(self.dynamic,bool):raise SimulationContractError("dynamic must be boolean")

    def integrate(self,step_ns:int)->"RigidBody":
        if not _is_int(step_ns) or step_ns<=0:raise SimulationContractError("invalid step_ns")
        if not self.dynamic:return self
        next_pos=tuple(self.position[i]+(self.velocity_per_sec[i]*step_ns)//1_000_000_000 for i in range(3))
        if any(abs(v)>MAX_BODY_VALUE for v in next_pos):raise SimulationContractError("rigid-body integration overflow")
        return RigidBody(self.body_id,self.mass_milli,next_pos,self.velocity_per_sec,self.dynamic)

@dataclass(frozen=True)
class CharacterController:
    entity_id:str
    position:tuple[int,int,int]
    max_speed_per_sec:int
    grounded:bool

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id")
        if not isinstance(self.position,tuple) or len(self.position)!=3 or any(not _is_int(v) for v in self.position):raise SimulationContractError("invalid controller position")
        if not _is_int(self.max_speed_per_sec) or self.max_speed_per_sec<=0:raise SimulationContractError("invalid max_speed_per_sec")
        if not isinstance(self.grounded,bool):raise SimulationContractError("grounded must be boolean")

    def move(self,delta:tuple[int,int,int],step_ns:int)->"CharacterController":
        if not isinstance(delta,tuple) or len(delta)!=3 or any(not _is_int(v) for v in delta):raise SimulationContractError("invalid movement delta")
        max_delta=(self.max_speed_per_sec*step_ns)//1_000_000_000
        if any(abs(v)>max_delta for v in delta):raise SimulationContractError("character speed budget exceeded")
        return CharacterController(self.entity_id,tuple(self.position[i]+delta[i] for i in range(3)),self.max_speed_per_sec,self.grounded)

@dataclass(frozen=True)
class Constraint:
    constraint_id:str
    kind:str
    body_a:str
    body_b:str|None
    limit_value:int

    def __post_init__(self)->None:
        require_id(self.constraint_id,"constraint_id");require_id(self.body_a,"body_a")
        if self.body_b is not None:require_id(self.body_b,"body_b")
        if self.body_b==self.body_a:raise SimulationContractError("constraint body identities must differ")
        if self.kind not in {"distance","hinge","fixed","spring","limit"}:raise SimulationContractError("invalid constraint kind")
        if not _is_int(self.limit_value) or abs(self.limit_value)>MAX_BODY_VALUE:raise SimulationContractError("invalid constraint limit")

@dataclass(frozen=True)
class SimulationState:
    tick:int
    ecs_digest:str
    transform_digest:str
    physics_digest:str
    rng_state_digest:str
    input_digest:str
    system_order:tuple[str,...]

    def __post_init__(self)->None:
        if not _is_int(self.tick) or not 0<=self.tick<=MAX_TICK:raise SimulationContractError("invalid tick")
        for name in ("ecs_digest","transform_digest","physics_digest","rng_state_digest","input_digest"):require_digest(getattr(self,name),name)
        order=tuple(self.system_order)
        if not order or len(set(order))!=len(order):raise SimulationContractError("invalid system order")
        for system in order:require_id(system,"system_id")

    @property
    def digest(self)->str:return digest_json({"tick":self.tick,"ecs_digest":self.ecs_digest,"transform_digest":self.transform_digest,"physics_digest":self.physics_digest,"rng_state_digest":self.rng_state_digest,"input_digest":self.input_digest,"system_order":list(self.system_order)})

    def next(self,*,ecs_digest:str,transform_digest:str,physics_digest:str,rng_state_digest:str,input_digest:str)->"SimulationState":
        if self.tick>=MAX_TICK:raise SimulationContractError("tick exhausted")
        return SimulationState(self.tick+1,ecs_digest,transform_digest,physics_digest,rng_state_digest,input_digest,self.system_order)

@dataclass(frozen=True)
class QueryHit:
    collider_id:str
    distance_units:int

    def __post_init__(self)->None:
        require_id(self.collider_id,"collider_id")
        if not _is_int(self.distance_units) or self.distance_units<0:raise SimulationContractError("invalid query distance")

def query_aabb(boxes:Sequence[AABB],query:AABB)->tuple[QueryHit,...]:
    hits=[]
    qcenter=tuple((query.min_xyz[i]+query.max_xyz[i])//2 for i in range(3))
    for box in boxes:
        if box.collider_id==query.collider_id:continue
        if narrowphase_aabb(box,query) is not None:
            center=tuple((box.min_xyz[i]+box.max_xyz[i])//2 for i in range(3))
            distance=sum(abs(center[i]-qcenter[i]) for i in range(3))
            hits.append(QueryHit(box.collider_id,distance))
    return tuple(sorted(hits,key=lambda h:(h.distance_units,h.collider_id)))

@dataclass(frozen=True)
class SimulationSnapshot:
    tick:int
    state_digest:str
    ecs_digest:str
    physics_digest:str
    rng_state_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.tick) or self.tick<0:raise SimulationContractError("invalid snapshot tick")
        for name in ("state_digest","ecs_digest","physics_digest","rng_state_digest"):require_digest(getattr(self,name),name)

    @property
    def digest(self)->str:return digest_json(self.__dict__)

class RollbackBuffer:
    def __init__(self,snapshots:Sequence[SimulationSnapshot]=(),max_snapshots:int=120)->None:
        if not _is_int(max_snapshots) or not 1<=max_snapshots<=MAX_SNAPSHOTS:raise SimulationContractError("invalid rollback capacity")
        ordered=tuple(sorted(snapshots,key=lambda s:s.tick))
        ticks=[s.tick for s in ordered]
        if len(set(ticks))!=len(ticks):raise SimulationContractError("duplicate rollback tick")
        self.snapshots=ordered[-max_snapshots:];self.max_snapshots=max_snapshots

    def append(self,snapshot:SimulationSnapshot)->"RollbackBuffer":
        if self.snapshots and snapshot.tick<=self.snapshots[-1].tick:raise SimulationContractError("rollback snapshots must advance")
        return RollbackBuffer(self.snapshots+(snapshot,),self.max_snapshots)

    def restore(self,tick:int)->SimulationSnapshot:
        if not _is_int(tick) or tick<0:raise SimulationContractError("invalid rollback tick")
        for snapshot in self.snapshots:
            if snapshot.tick==tick:return snapshot
        raise SimulationContractError("rollback snapshot unavailable")

@dataclass(frozen=True)
class RollbackReplayReceipt:
    restored_snapshot_digest:str
    target_tick:int
    input_chain_digest:str
    resulting_state_digest:str

    def __post_init__(self)->None:
        require_digest(self.restored_snapshot_digest,"restored_snapshot_digest");require_digest(self.input_chain_digest,"input_chain_digest");require_digest(self.resulting_state_digest,"resulting_state_digest")
        if not _is_int(self.target_tick) or self.target_tick<0:raise SimulationContractError("invalid target_tick")

    @property
    def digest(self)->str:return digest_json(self.__dict__)
