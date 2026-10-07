"""FLGB-11 engine-neutral render, material, camera, VFX, LOD, and recovery contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Sequence

MAX_ID_CHARS=256
MAX_GRAPH_NODES=100_000
MAX_RESOURCES=100_000
MAX_TEXTURE_BYTES=10_000_000_000
MAX_MIPS=32
MAX_PARTICLES=10_000_000
MAX_DISTANCE=10**15
MAX_SCORE_PPM=1_000_000

class RenderContractError(ValueError):
    """Fail-closed FLGB-11 contract error."""

def _is_int(v:Any)->bool:return isinstance(v,int) and not isinstance(v,bool)

def require_id(v:str,name:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID_CHARS or any(ord(c)<32 for c in v):raise RenderContractError(f"invalid {name}")
    return v

def require_digest(v:str,name:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):raise RenderContractError(f"invalid {name}")
    return v

def digest_json(v:Any)->str:
    try:raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode("utf-8")
    except (TypeError,ValueError) as exc:raise RenderContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class RenderPass:
    pass_id:str
    dependencies:tuple[str,...]
    reads:tuple[str,...]
    writes:tuple[str,...]

    def __post_init__(self)->None:
        require_id(self.pass_id,"pass_id")
        for name in ("dependencies","reads","writes"):
            values=tuple(sorted(getattr(self,name)))
            if len(set(values))!=len(values):raise RenderContractError(f"duplicate {name}")
            for value in values:require_id(value,name)
            object.__setattr__(self,name,values)
        if self.pass_id in self.dependencies:raise RenderContractError("render pass cannot depend on itself")
        if set(self.reads)&set(self.writes):raise RenderContractError("render pass cannot read/write same resource without explicit split")

class RenderGraph:
    def __init__(self,passes:Sequence[RenderPass])->None:
        if not passes or len(passes)>MAX_GRAPH_NODES:raise RenderContractError("render pass count out of bounds")
        by_id={p.pass_id:p for p in passes}
        if len(by_id)!=len(passes):raise RenderContractError("duplicate render pass")
        for p in passes:
            if not set(p.dependencies).issubset(by_id):raise RenderContractError("unknown render dependency")
        remaining=set(by_id);done=set();waves=[]
        while remaining:
            ready=sorted(pid for pid in remaining if set(by_id[pid].dependencies).issubset(done))
            if not ready:raise RenderContractError("render graph cycle")
            waves.append(tuple(ready));done.update(ready);remaining.difference_update(ready)
        self.passes=tuple(sorted(passes,key=lambda p:p.pass_id));self.waves=tuple(waves)

    @property
    def digest(self)->str:return digest_json([{"pass_id":p.pass_id,"dependencies":list(p.dependencies),"reads":list(p.reads),"writes":list(p.writes)} for p in self.passes])

@dataclass(frozen=True)
class MaterialNode:
    node_id:str
    operation:str
    inputs:tuple[str,...]
    output_type:str

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id");require_id(self.operation,"operation")
        inputs=tuple(sorted(self.inputs))
        if len(set(inputs))!=len(inputs):raise RenderContractError("duplicate material input")
        for item in inputs:require_id(item,"material input")
        object.__setattr__(self,"inputs",inputs)
        if self.output_type not in {"scalar","vec2","vec3","vec4","color","texture","normal"}:raise RenderContractError("invalid material output_type")

def validate_material_graph(nodes:Sequence[MaterialNode],output_node_id:str)->tuple[MaterialNode,...]:
    output_node_id=require_id(output_node_id,"output_node_id")
    if not nodes or len(nodes)>MAX_GRAPH_NODES:raise RenderContractError("material node count out of bounds")
    by_id={n.node_id:n for n in nodes}
    if len(by_id)!=len(nodes) or output_node_id not in by_id:raise RenderContractError("invalid material node identity")
    state={}
    def visit(nid:str)->None:
        mark=state.get(nid,0)
        if mark==1:raise RenderContractError("material graph cycle")
        if mark==2:return
        state[nid]=1
        for dep in by_id[nid].inputs:
            if dep not in by_id:raise RenderContractError("unknown material input")
            visit(dep)
        state[nid]=2
    visit(output_node_id)
    return tuple(sorted((by_id[n] for n in state),key=lambda n:n.node_id))

@dataclass(frozen=True)
class ShaderCompileRequest:
    shader_id:str
    source_digest:str
    stage:str
    backend:str
    defines:tuple[str,...]
    compiler_digest:str

    def __post_init__(self)->None:
        require_id(self.shader_id,"shader_id");require_digest(self.source_digest,"source_digest");require_digest(self.compiler_digest,"compiler_digest")
        if self.stage not in {"vertex","fragment","compute","geometry","mesh","task"}:raise RenderContractError("invalid shader stage")
        if self.backend not in {"spirv","dxil","msl","wgsl","glsl"}:raise RenderContractError("invalid shader backend")
        defines=tuple(sorted(self.defines))
        if len(set(defines))!=len(defines):raise RenderContractError("duplicate shader define")
        for define in defines:require_id(define,"shader define")
        object.__setattr__(self,"defines",defines)

    @property
    def digest(self)->str:return digest_json({"shader_id":self.shader_id,"source_digest":self.source_digest,"stage":self.stage,"backend":self.backend,"defines":list(self.defines),"compiler_digest":self.compiler_digest})

@dataclass(frozen=True)
class ShaderCompileReceipt:
    request_digest:str
    binary_digest:str
    reflection_digest:str

    def __post_init__(self)->None:
        require_digest(self.request_digest,"request_digest");require_digest(self.binary_digest,"binary_digest");require_digest(self.reflection_digest,"reflection_digest")

@dataclass(frozen=True)
class TextureMip:
    level:int
    content_digest:str
    byte_size:int

    def __post_init__(self)->None:
        if not _is_int(self.level) or not 0<=self.level<MAX_MIPS:raise RenderContractError("invalid mip level")
        require_digest(self.content_digest,"content_digest")
        if not _is_int(self.byte_size) or not 1<=self.byte_size<=MAX_TEXTURE_BYTES:raise RenderContractError("invalid mip byte_size")

def texture_residency(mips:Sequence[TextureMip],byte_budget:int)->tuple[int,...]:
    if not _is_int(byte_budget) or byte_budget<0:raise RenderContractError("invalid texture byte budget")
    ordered=tuple(sorted(mips,key=lambda m:m.level,reverse=True))
    levels=[m.level for m in ordered]
    if len(set(levels))!=len(levels):raise RenderContractError("duplicate texture mip")
    used=0;resident=[]
    for mip in ordered:
        if used+mip.byte_size<=byte_budget:resident.append(mip.level);used+=mip.byte_size
    return tuple(sorted(resident))

@dataclass(frozen=True)
class MeshArtifact:
    mesh_id:str
    vertex_digest:str
    index_digest:str
    vertex_count:int
    index_count:int
    topology:str
    provenance_digest:str

    def __post_init__(self)->None:
        require_id(self.mesh_id,"mesh_id");require_digest(self.vertex_digest,"vertex_digest");require_digest(self.index_digest,"index_digest");require_digest(self.provenance_digest,"provenance_digest")
        for name in ("vertex_count","index_count"):
            value=getattr(self,name)
            if not _is_int(value) or value<=0:raise RenderContractError(f"invalid {name}")
        if self.topology not in {"triangles","lines","points"}:raise RenderContractError("invalid mesh topology")

    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class Light:
    light_id:str
    kind:str
    intensity_milli:int
    color_milli:tuple[int,int,int]
    casts_shadow:bool

    def __post_init__(self)->None:
        require_id(self.light_id,"light_id")
        if self.kind not in {"directional","point","spot","area","environment"}:raise RenderContractError("invalid light kind")
        if not _is_int(self.intensity_milli) or self.intensity_milli<0:raise RenderContractError("invalid light intensity")
        if not isinstance(self.color_milli,tuple) or len(self.color_milli)!=3 or any(not _is_int(v) or not 0<=v<=1000 for v in self.color_milli):raise RenderContractError("invalid light color")
        if not isinstance(self.casts_shadow,bool):raise RenderContractError("casts_shadow must be boolean")

@dataclass(frozen=True)
class ShadowAllocation:
    light_id:str
    x:int
    y:int
    size:int

    def __post_init__(self)->None:
        require_id(self.light_id,"light_id")
        for name in ("x","y"):
            if not _is_int(getattr(self,name)) or getattr(self,name)<0:raise RenderContractError(f"invalid {name}")
        if not _is_int(self.size) or self.size<=0:raise RenderContractError("invalid shadow size")

def validate_shadow_atlas(allocations:Sequence[ShadowAllocation],atlas_size:int)->tuple[ShadowAllocation,...]:
    if not _is_int(atlas_size) or atlas_size<=0:raise RenderContractError("invalid atlas_size")
    ids=[a.light_id for a in allocations]
    if len(set(ids))!=len(ids):raise RenderContractError("duplicate shadow allocation")
    ordered=tuple(sorted(allocations,key=lambda a:(a.y,a.x,a.light_id)))
    for i,a in enumerate(ordered):
        if a.x+a.size>atlas_size or a.y+a.size>atlas_size:raise RenderContractError("shadow allocation out of atlas")
        for b in ordered[i+1:]:
            overlap=a.x<b.x+b.size and b.x<a.x+a.size and a.y<b.y+b.size and b.y<a.y+a.size
            if overlap:raise RenderContractError("shadow atlas overlap")
    return ordered

@dataclass(frozen=True)
class Camera:
    camera_id:str
    position:tuple[int,int,int]
    rotation_microrad:tuple[int,int,int]
    fov_millideg:int
    near_milli:int
    far_milli:int

    def __post_init__(self)->None:
        require_id(self.camera_id,"camera_id")
        for name in ("position","rotation_microrad"):
            values=getattr(self,name)
            if not isinstance(values,tuple) or len(values)!=3 or any(not _is_int(v) for v in values):raise RenderContractError(f"invalid {name}")
        if not _is_int(self.fov_millideg) or not 1000<=self.fov_millideg<=179000:raise RenderContractError("invalid fov")
        if not _is_int(self.near_milli) or not _is_int(self.far_milli) or not 0<self.near_milli<self.far_milli:raise RenderContractError("invalid camera clip planes")

@dataclass(frozen=True)
class CameraRig:
    rig_id:str
    cameras:tuple[Camera,...]
    active_camera_id:str

    def __post_init__(self)->None:
        require_id(self.rig_id,"rig_id");require_id(self.active_camera_id,"active_camera_id")
        ids=[c.camera_id for c in self.cameras]
        if not ids or len(set(ids))!=len(ids) or self.active_camera_id not in ids:raise RenderContractError("invalid camera rig")

@dataclass(frozen=True)
class PostProcessPass:
    pass_id:str
    effect:str
    config_digest:str
    enabled:bool=True

    def __post_init__(self)->None:
        require_id(self.pass_id,"pass_id");require_id(self.effect,"effect");require_digest(self.config_digest,"config_digest")
        if not isinstance(self.enabled,bool):raise RenderContractError("enabled must be boolean")

def post_process_order(passes:Sequence[PostProcessPass])->tuple[PostProcessPass,...]:
    ids=[p.pass_id for p in passes]
    if len(set(ids))!=len(ids):raise RenderContractError("duplicate post-process pass")
    return tuple(p for p in passes if p.enabled)

@dataclass(frozen=True)
class ParticleEmitter:
    emitter_id:str
    max_particles:int
    spawn_rate_milli:int
    seed:int
    material_digest:str

    def __post_init__(self)->None:
        require_id(self.emitter_id,"emitter_id");require_digest(self.material_digest,"material_digest")
        if not _is_int(self.max_particles) or not 1<=self.max_particles<=MAX_PARTICLES:raise RenderContractError("invalid max_particles")
        if not _is_int(self.spawn_rate_milli) or self.spawn_rate_milli<0:raise RenderContractError("invalid spawn rate")
        if not _is_int(self.seed):raise RenderContractError("invalid particle seed")

    def spawn_count(self,elapsed_ms:int,current_particles:int)->int:
        if not _is_int(elapsed_ms) or elapsed_ms<0 or not _is_int(current_particles) or not 0<=current_particles<=self.max_particles:raise RenderContractError("invalid particle state")
        requested=(self.spawn_rate_milli*elapsed_ms)//1_000_000
        return min(requested,self.max_particles-current_particles)

@dataclass(frozen=True)
class LODLevel:
    level:int
    min_distance:int
    mesh_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.level) or self.level<0:raise RenderContractError("invalid LOD level")
        if not _is_int(self.min_distance) or not 0<=self.min_distance<=MAX_DISTANCE:raise RenderContractError("invalid LOD distance")
        require_digest(self.mesh_digest,"mesh_digest")

def select_lod(levels:Sequence[LODLevel],distance:int)->LODLevel:
    if not _is_int(distance) or not 0<=distance<=MAX_DISTANCE:raise RenderContractError("invalid LOD query distance")
    ordered=tuple(sorted(levels,key=lambda l:(l.min_distance,l.level)))
    if not ordered or ordered[0].min_distance!=0:raise RenderContractError("LOD chain must begin at zero")
    if len({l.level for l in ordered})!=len(ordered) or len({l.min_distance for l in ordered})!=len(ordered):raise RenderContractError("duplicate LOD boundary")
    chosen=ordered[0]
    for level in ordered:
        if level.min_distance<=distance:chosen=level
        else:break
    return chosen

@dataclass(frozen=True)
class RenderRecoveryReceipt:
    frame_id:int
    render_graph_digest:str
    resource_manifest_digest:str
    failed_backend:str
    fallback_backend:str
    restored_state_digest:str
    expected_state_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.frame_id) or self.frame_id<0:raise RenderContractError("invalid frame_id")
        for name in ("render_graph_digest","resource_manifest_digest","restored_state_digest","expected_state_digest"):require_digest(getattr(self,name),name)
        require_id(self.failed_backend,"failed_backend");require_id(self.fallback_backend,"fallback_backend")
        if self.failed_backend==self.fallback_backend:raise RenderContractError("fallback backend must differ")
        if self.restored_state_digest!=self.expected_state_digest:raise RenderContractError("render recovery state mismatch")

    @property
    def digest(self)->str:return digest_json(self.__dict__)
