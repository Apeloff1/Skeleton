"""FLGB-11 deterministic rendering, asset-streaming, and recovery contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_NODES=100_000
MAX_RESOURCES=100_000
MAX_VARIANTS=100_000
MAX_TEXTURE_BYTES=10_000_000_000
MAX_MESH_ELEMENTS=100_000_000
MAX_LIGHTS=1_000_000
MAX_SHADOW_MAP=32768
MAX_CAMERA_COORD=10**15
MAX_PARTICLES=100_000_000
MAX_LODS=64
MAX_SCORE_PPM=1_000_000

class RenderContractError(ValueError):
    """Fail-closed FLGB-11 contract error."""

def _is_int(value:Any)->bool: return isinstance(value,int) and not isinstance(value,bool)

def require_id(value:str,name:str)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>MAX_ID_CHARS or any(ord(ch)<32 for ch in value): raise RenderContractError(f"invalid {name}")
    return value

def require_digest(value:str,name:str)->str:
    if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value): raise RenderContractError(f"invalid {name}")
    return value

def digest_json(value:Any)->str:
    try: raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError) as exc: raise RenderContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class RenderPass:
    pass_id:str
    reads:tuple[str,...]
    writes:tuple[str,...]
    dependencies:tuple[str,...]=()

    def __post_init__(self)->None:
        require_id(self.pass_id,"pass_id")
        reads=tuple(sorted(self.reads)); writes=tuple(sorted(self.writes)); deps=tuple(sorted(self.dependencies))
        if len(set(reads))!=len(reads) or len(set(writes))!=len(writes) or len(set(deps))!=len(deps): raise RenderContractError("duplicate render pass edge")
        if set(reads)&set(writes): raise RenderContractError("render pass cannot read and write same logical resource")
        if self.pass_id in deps: raise RenderContractError("render pass cannot depend on itself")
        for value in reads+writes: require_id(value,"resource_id")
        for value in deps: require_id(value,"dependency")
        object.__setattr__(self,"reads",reads); object.__setattr__(self,"writes",writes); object.__setattr__(self,"dependencies",deps)

class RenderGraph:
    def __init__(self,passes:Sequence[RenderPass])->None:
        if not passes or len(passes)>MAX_NODES: raise RenderContractError("render pass count out of bounds")
        by_id={p.pass_id:p for p in passes}
        if len(by_id)!=len(passes): raise RenderContractError("duplicate render pass")
        for p in passes:
            if set(p.dependencies)-set(by_id): raise RenderContractError("unknown render dependency")
        writers={}
        for p in passes:
            for resource in p.writes:
                if resource in writers: raise RenderContractError("resource has multiple render writers")
                writers[resource]=p.pass_id
        self._passes=MappingProxyType(by_id); self._order=self._topological_order()

    def _topological_order(self)->tuple[str,...]:
        remaining=set(self._passes); done=set(); order=[]
        while remaining:
            ready=sorted(pid for pid in remaining if set(self._passes[pid].dependencies).issubset(done))
            if not ready: raise RenderContractError("render graph cycle")
            order.extend(ready); done.update(ready); remaining.difference_update(ready)
        return tuple(order)

    @property
    def execution_order(self)->tuple[str,...]: return self._order

    @property
    def digest(self)->str:
        return digest_json([{"pass_id":p.pass_id,"reads":list(p.reads),"writes":list(p.writes),"dependencies":list(p.dependencies)} for p in sorted(self._passes.values(),key=lambda x:x.pass_id)])

@dataclass(frozen=True)
class MaterialNode:
    node_id:str
    op:str
    input_nodes:tuple[str,...]
    parameter_digest:str

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id"); require_id(self.op,"op"); require_digest(self.parameter_digest,"parameter_digest")
        inputs=tuple(sorted(self.input_nodes))
        if len(set(inputs))!=len(inputs) or self.node_id in inputs: raise RenderContractError("invalid material inputs")
        for value in inputs: require_id(value,"input_node")
        object.__setattr__(self,"input_nodes",inputs)

class MaterialGraph:
    def __init__(self,nodes:Sequence[MaterialNode],output_node:str)->None:
        if not nodes or len(nodes)>MAX_NODES: raise RenderContractError("material node count out of bounds")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise RenderContractError("duplicate material node")
        output_node=require_id(output_node,"output_node")
        if output_node not in by_id: raise RenderContractError("unknown material output")
        for node in nodes:
            if set(node.input_nodes)-set(by_id): raise RenderContractError("unknown material input node")
        self._nodes=MappingProxyType(by_id); self.output_node=output_node; self._validate()

    def _validate(self)->None:
        state={}
        def visit(node_id:str)->None:
            mark=state.get(node_id,0)
            if mark==1: raise RenderContractError("material graph cycle")
            if mark==2:return
            state[node_id]=1
            for dep in self._nodes[node_id].input_nodes: visit(dep)
            state[node_id]=2
        visit(self.output_node)

    @property
    def digest(self)->str: return digest_json({"output_node":self.output_node,"nodes":[{"node_id":n.node_id,"op":n.op,"input_nodes":list(n.input_nodes),"parameter_digest":n.parameter_digest} for n in sorted(self._nodes.values(),key=lambda n:n.node_id)]})

@dataclass(frozen=True)
class ShaderCompileRequest:
    shader_id:str
    source_digest:str
    stage:str
    target:str
    defines:tuple[str,...]=()

    def __post_init__(self)->None:
        require_id(self.shader_id,"shader_id"); require_digest(self.source_digest,"source_digest"); require_id(self.target,"target")
        if self.stage not in {"vertex","fragment","compute","geometry","mesh","task"}: raise RenderContractError("invalid shader stage")
        defines=tuple(sorted(self.defines))
        if len(defines)>MAX_VARIANTS or len(set(defines))!=len(defines): raise RenderContractError("invalid shader defines")
        for define in defines: require_id(define,"define")
        object.__setattr__(self,"defines",defines)

    @property
    def digest(self)->str: return digest_json({"shader_id":self.shader_id,"source_digest":self.source_digest,"stage":self.stage,"target":self.target,"defines":list(self.defines)})

@dataclass(frozen=True)
class ShaderCompileReceipt:
    request_digest:str
    compiler_digest:str
    binary_digest:str
    reflection_digest:str
    warnings_digest:str

    def __post_init__(self)->None:
        for name in ("request_digest","compiler_digest","binary_digest","reflection_digest","warnings_digest"): require_digest(getattr(self,name),name)

    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class TextureRequest:
    texture_id:str
    content_digest:str
    bytes:int
    priority:int
    min_mip:int
    max_mip:int

    def __post_init__(self)->None:
        require_id(self.texture_id,"texture_id"); require_digest(self.content_digest,"content_digest")
        if not _is_int(self.bytes) or not 1<=self.bytes<=MAX_TEXTURE_BYTES: raise RenderContractError("invalid texture bytes")
        if not _is_int(self.priority): raise RenderContractError("invalid texture priority")
        if not _is_int(self.min_mip) or not _is_int(self.max_mip) or not 0<=self.min_mip<=self.max_mip<=64: raise RenderContractError("invalid mip range")

def plan_texture_streaming(requests:Sequence[TextureRequest],byte_budget:int)->tuple[str,...]:
    if not _is_int(byte_budget) or byte_budget<0: raise RenderContractError("invalid texture budget")
    ids=[r.texture_id for r in requests]
    if len(set(ids))!=len(ids): raise RenderContractError("duplicate texture request")
    used=0; selected=[]
    for req in sorted(requests,key=lambda r:(-r.priority,r.bytes,r.texture_id)):
        if used+req.bytes<=byte_budget: selected.append(req.texture_id); used+=req.bytes
    return tuple(selected)

@dataclass(frozen=True)
class MeshArtifact:
    mesh_id:str
    source_digest:str
    vertex_count:int
    index_count:int
    topology:str
    bounds_digest:str

    def __post_init__(self)->None:
        require_id(self.mesh_id,"mesh_id"); require_digest(self.source_digest,"source_digest"); require_digest(self.bounds_digest,"bounds_digest")
        for name in ("vertex_count","index_count"):
            value=getattr(self,name)
            if not _is_int(value) or not 0<=value<=MAX_MESH_ELEMENTS: raise RenderContractError(f"invalid {name}")
        if self.vertex_count==0 and self.index_count>0: raise RenderContractError("indexed mesh requires vertices")
        if self.topology not in {"triangles","lines","points"}: raise RenderContractError("invalid topology")

    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class Light:
    light_id:str
    kind:str
    intensity_milli:int
    range_mm:int
    color_digest:str
    casts_shadow:bool

    def __post_init__(self)->None:
        require_id(self.light_id,"light_id"); require_digest(self.color_digest,"color_digest")
        if self.kind not in {"directional","point","spot","area"}: raise RenderContractError("invalid light kind")
        if not _is_int(self.intensity_milli) or self.intensity_milli<0: raise RenderContractError("invalid intensity")
        if not _is_int(self.range_mm) or self.range_mm<0: raise RenderContractError("invalid range")
        if not isinstance(self.casts_shadow,bool): raise RenderContractError("casts_shadow must be boolean")

def order_lights(lights:Sequence[Light],limit:int)->tuple[Light,...]:
    if not _is_int(limit) or not 0<=limit<=MAX_LIGHTS: raise RenderContractError("invalid light limit")
    ids=[l.light_id for l in lights]
    if len(set(ids))!=len(ids): raise RenderContractError("duplicate light")
    return tuple(sorted(lights,key=lambda l:(-l.intensity_milli,l.light_id))[:limit])

@dataclass(frozen=True)
class ShadowRequest:
    light_id:str
    resolution:int
    cascade_count:int
    priority:int

    def __post_init__(self)->None:
        require_id(self.light_id,"light_id")
        if not _is_int(self.resolution) or not 1<=self.resolution<=MAX_SHADOW_MAP: raise RenderContractError("invalid shadow resolution")
        if self.resolution&(self.resolution-1): raise RenderContractError("shadow resolution must be power of two")
        if not _is_int(self.cascade_count) or not 1<=self.cascade_count<=16: raise RenderContractError("invalid cascade_count")
        if not _is_int(self.priority): raise RenderContractError("invalid shadow priority")

    @property
    def texel_cost(self)->int:return self.resolution*self.resolution*self.cascade_count

def plan_shadows(requests:Sequence[ShadowRequest],texel_budget:int)->tuple[str,...]:
    if not _is_int(texel_budget) or texel_budget<0: raise RenderContractError("invalid shadow budget")
    ids=[r.light_id for r in requests]
    if len(set(ids))!=len(ids): raise RenderContractError("duplicate shadow request")
    used=0; selected=[]
    for req in sorted(requests,key=lambda r:(-r.priority,r.texel_cost,r.light_id)):
        if used+req.texel_cost<=texel_budget: selected.append(req.light_id); used+=req.texel_cost
    return tuple(selected)

@dataclass(frozen=True)
class CameraRig:
    camera_id:str
    pos_x:int; pos_y:int; pos_z:int
    target_x:int; target_y:int; target_z:int
    fov_mdeg:int
    near_mm:int
    far_mm:int

    def __post_init__(self)->None:
        require_id(self.camera_id,"camera_id")
        for name in ("pos_x","pos_y","pos_z","target_x","target_y","target_z"):
            v=getattr(self,name)
            if not _is_int(v) or abs(v)>MAX_CAMERA_COORD: raise RenderContractError(f"invalid {name}")
        if (self.pos_x,self.pos_y,self.pos_z)==(self.target_x,self.target_y,self.target_z): raise RenderContractError("camera target cannot equal position")
        if not _is_int(self.fov_mdeg) or not 1000<=self.fov_mdeg<179000: raise RenderContractError("invalid fov")
        if not _is_int(self.near_mm) or not _is_int(self.far_mm) or not 1<=self.near_mm<self.far_mm: raise RenderContractError("invalid clip planes")

    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class PostEffect:
    effect_id:str
    stage:int
    parameter_digest:str
    enabled:bool=True

    def __post_init__(self)->None:
        require_id(self.effect_id,"effect_id"); require_digest(self.parameter_digest,"parameter_digest")
        if not _is_int(self.stage) or self.stage<0: raise RenderContractError("invalid post stage")
        if not isinstance(self.enabled,bool): raise RenderContractError("enabled must be boolean")

def order_post_effects(effects:Sequence[PostEffect])->tuple[PostEffect,...]:
    ids=[e.effect_id for e in effects]
    if len(set(ids))!=len(ids): raise RenderContractError("duplicate post effect")
    return tuple(sorted((e for e in effects if e.enabled),key=lambda e:(e.stage,e.effect_id)))

@dataclass(frozen=True)
class ParticleEmitter:
    emitter_id:str
    seed_digest:str
    rate_milli_per_second:int
    max_particles:int
    lifetime_ms:int

    def __post_init__(self)->None:
        require_id(self.emitter_id,"emitter_id"); require_digest(self.seed_digest,"seed_digest")
        if not _is_int(self.rate_milli_per_second) or self.rate_milli_per_second<0: raise RenderContractError("invalid particle rate")
        if not _is_int(self.max_particles) or not 0<=self.max_particles<=MAX_PARTICLES: raise RenderContractError("invalid max_particles")
        if not _is_int(self.lifetime_ms) or self.lifetime_ms<1: raise RenderContractError("invalid lifetime_ms")

    def emitted_count(self,elapsed_ms:int)->int:
        if not _is_int(elapsed_ms) or elapsed_ms<0: raise RenderContractError("invalid elapsed_ms")
        produced=(self.rate_milli_per_second*elapsed_ms)//1_000_000
        return min(self.max_particles,produced)

@dataclass(frozen=True)
class LODLevel:
    level:int
    enter_distance_mm:int
    asset_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.level) or not 0<=self.level<MAX_LODS: raise RenderContractError("invalid LOD level")
        if not _is_int(self.enter_distance_mm) or self.enter_distance_mm<0: raise RenderContractError("invalid LOD distance")
        require_digest(self.asset_digest,"asset_digest")

class LODPolicy:
    def __init__(self,levels:Sequence[LODLevel])->None:
        if not levels or len(levels)>MAX_LODS: raise RenderContractError("LOD count out of bounds")
        ordered=tuple(sorted(levels,key=lambda x:x.level))
        if [x.level for x in ordered]!=list(range(len(ordered))): raise RenderContractError("LOD levels must be contiguous")
        distances=[x.enter_distance_mm for x in ordered]
        if distances!=sorted(distances) or len(set(distances))!=len(distances): raise RenderContractError("LOD distances must strictly increase")
        self.levels=ordered

    def choose(self,distance_mm:int)->LODLevel:
        if not _is_int(distance_mm) or distance_mm<0: raise RenderContractError("invalid LOD query distance")
        selected=self.levels[0]
        for level in self.levels:
            if distance_mm>=level.enter_distance_mm: selected=level
            else: break
        return selected

    @property
    def digest(self)->str:return digest_json([x.__dict__ for x in self.levels])

@dataclass(frozen=True)
class RenderCheckpoint:
    frame_id:int
    graph_digest:str
    resource_state_digest:str
    pipeline_cache_digest:str
    prior_checkpoint_digest:str|None=None

    def __post_init__(self)->None:
        if not _is_int(self.frame_id) or self.frame_id<0: raise RenderContractError("invalid frame_id")
        for name in ("graph_digest","resource_state_digest","pipeline_cache_digest"): require_digest(getattr(self,name),name)
        if self.prior_checkpoint_digest is not None: require_digest(self.prior_checkpoint_digest,"prior_checkpoint_digest")
        if self.frame_id==0 and self.prior_checkpoint_digest is not None: raise RenderContractError("genesis render checkpoint cannot have parent")
        if self.frame_id>0 and self.prior_checkpoint_digest is None: raise RenderContractError("render checkpoint requires parent")

    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class RenderRecoveryDecision:
    checkpoint_digest:str
    action:str
    preserved_graph_digest:str

    def __post_init__(self)->None:
        require_digest(self.checkpoint_digest,"checkpoint_digest"); require_digest(self.preserved_graph_digest,"preserved_graph_digest")
        if self.action not in {"resume","rebuild-resources","rebuild-pipelines","safe-render"}: raise RenderContractError("invalid render recovery action")

def recover_render(checkpoint:RenderCheckpoint,fault:str)->RenderRecoveryDecision:
    fault=require_id(fault,"fault")
    mapping={"resource-lost":"rebuild-resources","pipeline-invalid":"rebuild-pipelines","device-lost":"safe-render","none":"resume"}
    action=mapping.get(fault,"safe-render")
    return RenderRecoveryDecision(checkpoint.digest,action,checkpoint.graph_digest)
