"""FLGB-12 deterministic animation, audio, UI, input, accessibility, and replay contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Sequence

MAX_ID_CHARS=256
MAX_NODES=100_000
MAX_JOINTS=10_000
MAX_SCORE_PPM=1_000_000
MAX_DURATION_MS=86_400_000
MAX_COORD=10**12

class PresentationContractError(ValueError):pass
def _is_int(v:Any)->bool:return isinstance(v,int) and not isinstance(v,bool)
def require_id(v:str,name:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID_CHARS or any(ord(c)<32 for c in v):raise PresentationContractError(f"invalid {name}")
    return v
def require_digest(v:str,name:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):raise PresentationContractError(f"invalid {name}")
    return v
def digest_json(v:Any)->str:
    try:raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode("utf-8")
    except (TypeError,ValueError) as exc:raise PresentationContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class AnimationState:
    state_id:str
    clip_digest:str
    loop:bool
    speed_milli:int=1000
    def __post_init__(self)->None:
        require_id(self.state_id,"state_id");require_digest(self.clip_digest,"clip_digest")
        if not isinstance(self.loop,bool):raise PresentationContractError("loop must be boolean")
        if not _is_int(self.speed_milli) or self.speed_milli<=0:raise PresentationContractError("invalid speed_milli")
@dataclass(frozen=True)
class AnimationTransition:
    from_state:str
    event:str
    to_state:str
    blend_ms:int
    def __post_init__(self)->None:
        require_id(self.from_state,"from_state");require_id(self.event,"event");require_id(self.to_state,"to_state")
        if not _is_int(self.blend_ms) or not 0<=self.blend_ms<=MAX_DURATION_MS:raise PresentationContractError("invalid blend_ms")
class AnimationGraph:
    def __init__(self,states:Sequence[AnimationState],transitions:Sequence[AnimationTransition],initial_state:str)->None:
        by_id={s.state_id:s for s in states}
        if not by_id or len(by_id)!=len(states) or initial_state not in by_id:raise PresentationContractError("invalid animation states")
        seen=set()
        for t in transitions:
            if t.from_state not in by_id or t.to_state not in by_id:raise PresentationContractError("animation transition references unknown state")
            key=(t.from_state,t.event)
            if key in seen:raise PresentationContractError("ambiguous animation transition")
            seen.add(key)
        self.states=tuple(sorted(states,key=lambda s:s.state_id));self.transitions=tuple(sorted(transitions,key=lambda t:(t.from_state,t.event,t.to_state)));self.initial_state=initial_state
    def transition(self,state_id:str,event:str)->str:
        for t in self.transitions:
            if t.from_state==state_id and t.event==event:return t.to_state
        return state_id
    @property
    def digest(self)->str:return digest_json({"states":[s.__dict__ for s in self.states],"transitions":[t.__dict__ for t in self.transitions],"initial_state":self.initial_state})

@dataclass(frozen=True)
class Joint:
    joint_id:str
    parent_id:str|None
    bind_translation:tuple[int,int,int]
    def __post_init__(self)->None:
        require_id(self.joint_id,"joint_id")
        if self.parent_id is not None:require_id(self.parent_id,"parent_id")
        if self.parent_id==self.joint_id:raise PresentationContractError("joint cannot parent itself")
        if not isinstance(self.bind_translation,tuple) or len(self.bind_translation)!=3 or any(not _is_int(v) or abs(v)>MAX_COORD for v in self.bind_translation):raise PresentationContractError("invalid bind translation")
class Skeleton:
    def __init__(self,joints:Sequence[Joint])->None:
        if not joints or len(joints)>MAX_JOINTS:raise PresentationContractError("joint count out of bounds")
        by_id={j.joint_id:j for j in joints}
        if len(by_id)!=len(joints):raise PresentationContractError("duplicate joint")
        roots=[j for j in joints if j.parent_id is None]
        if len(roots)!=1:raise PresentationContractError("skeleton requires one root")
        state={}
        def visit(jid:str)->None:
            m=state.get(jid,0)
            if m==1:raise PresentationContractError("skeleton cycle")
            if m==2:return
            state[jid]=1;p=by_id[jid].parent_id
            if p is not None:
                if p not in by_id:raise PresentationContractError("unknown joint parent")
                visit(p)
            state[jid]=2
        for jid in by_id:visit(jid)
        self.joints=tuple(sorted(joints,key=lambda j:j.joint_id));self.root_id=roots[0].joint_id
    @property
    def digest(self)->str:return digest_json([j.__dict__ for j in self.joints])

@dataclass(frozen=True)
class ProceduralModifier:
    modifier_id:str
    kind:str
    config_digest:str
    seed:int
    weight_ppm:int
    def __post_init__(self)->None:
        require_id(self.modifier_id,"modifier_id");require_id(self.kind,"kind");require_digest(self.config_digest,"config_digest")
        if not _is_int(self.seed):raise PresentationContractError("invalid seed")
        if not _is_int(self.weight_ppm) or not 0<=self.weight_ppm<=MAX_SCORE_PPM:raise PresentationContractError("invalid weight_ppm")
    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class AudioNode:
    node_id:str
    kind:str
    inputs:tuple[str,...]
    config_digest:str
    def __post_init__(self)->None:
        require_id(self.node_id,"node_id");require_id(self.kind,"kind");require_digest(self.config_digest,"config_digest")
        values=tuple(sorted(self.inputs))
        if len(set(values))!=len(values):raise PresentationContractError("duplicate audio input")
        for value in values:require_id(value,"audio input")
        object.__setattr__(self,"inputs",values)
def validate_audio_graph(nodes:Sequence[AudioNode],output_id:str)->tuple[AudioNode,...]:
    output_id=require_id(output_id,"output_id");by_id={n.node_id:n for n in nodes}
    if not by_id or len(by_id)!=len(nodes) or output_id not in by_id:raise PresentationContractError("invalid audio graph")
    state={}
    def visit(nid:str)->None:
        m=state.get(nid,0)
        if m==1:raise PresentationContractError("audio graph cycle")
        if m==2:return
        state[nid]=1
        for dep in by_id[nid].inputs:
            if dep not in by_id:raise PresentationContractError("unknown audio input")
            visit(dep)
        state[nid]=2
    visit(output_id)
    return tuple(sorted((by_id[nid] for nid in state),key=lambda n:n.node_id))

@dataclass(frozen=True)
class MusicState:
    state_id:str
    track_digest:str
    intensity_ppm:int
    def __post_init__(self)->None:
        require_id(self.state_id,"state_id");require_digest(self.track_digest,"track_digest")
        if not _is_int(self.intensity_ppm) or not 0<=self.intensity_ppm<=MAX_SCORE_PPM:raise PresentationContractError("invalid intensity_ppm")
@dataclass(frozen=True)
class MusicTransition:
    from_state:str
    event:str
    to_state:str
    crossfade_ms:int
    def __post_init__(self)->None:
        require_id(self.from_state,"from_state");require_id(self.event,"event");require_id(self.to_state,"to_state")
        if not _is_int(self.crossfade_ms) or not 0<=self.crossfade_ms<=MAX_DURATION_MS:raise PresentationContractError("invalid crossfade_ms")
def next_music_state(current:str,event:str,states:Sequence[MusicState],transitions:Sequence[MusicTransition])->str:
    ids={s.state_id for s in states};require_id(current,"current");require_id(event,"event")
    if current not in ids:raise PresentationContractError("unknown music state")
    matches=[t for t in transitions if t.from_state==current and t.event==event]
    if len(matches)>1:raise PresentationContractError("ambiguous music transition")
    if not matches:return current
    if matches[0].to_state not in ids:raise PresentationContractError("unknown target music state")
    return matches[0].to_state

@dataclass(frozen=True)
class SpatialAudioSource:
    source_id:str
    position:tuple[int,int,int]
    gain_milli:int
    max_distance:int
    clip_digest:str
    def __post_init__(self)->None:
        require_id(self.source_id,"source_id");require_digest(self.clip_digest,"clip_digest")
        if not isinstance(self.position,tuple) or len(self.position)!=3 or any(not _is_int(v) or abs(v)>MAX_COORD for v in self.position):raise PresentationContractError("invalid spatial position")
        if not _is_int(self.gain_milli) or self.gain_milli<0:raise PresentationContractError("invalid gain_milli")
        if not _is_int(self.max_distance) or self.max_distance<=0:raise PresentationContractError("invalid max_distance")

@dataclass(frozen=True)
class UINode:
    node_id:str
    parent_id:str|None
    role:str
    rect:tuple[int,int,int,int]
    visible:bool=True
    def __post_init__(self)->None:
        require_id(self.node_id,"node_id");require_id(self.role,"role")
        if self.parent_id is not None:require_id(self.parent_id,"parent_id")
        if self.parent_id==self.node_id:raise PresentationContractError("UI node cannot parent itself")
        if not isinstance(self.rect,tuple) or len(self.rect)!=4 or any(not _is_int(v) for v in self.rect) or self.rect[2]<0 or self.rect[3]<0:raise PresentationContractError("invalid UI rect")
        if not isinstance(self.visible,bool):raise PresentationContractError("visible must be boolean")
def validate_ui_layout(nodes:Sequence[UINode])->tuple[UINode,...]:
    by_id={n.node_id:n for n in nodes}
    if not by_id or len(by_id)!=len(nodes):raise PresentationContractError("invalid UI nodes")
    state={}
    def visit(nid:str)->None:
        m=state.get(nid,0)
        if m==1:raise PresentationContractError("UI hierarchy cycle")
        if m==2:return
        state[nid]=1;p=by_id[nid].parent_id
        if p is not None:
            if p not in by_id:raise PresentationContractError("unknown UI parent")
            visit(p)
        state[nid]=2
    for nid in by_id:visit(nid)
    return tuple(sorted(nodes,key=lambda n:n.node_id))

@dataclass(frozen=True)
class InputBinding:
    action_id:str
    device_kind:str
    control_id:str
    scale_milli:int=1000
    def __post_init__(self)->None:
        require_id(self.action_id,"action_id");require_id(self.device_kind,"device_kind");require_id(self.control_id,"control_id")
        if not _is_int(self.scale_milli) or self.scale_milli==0:raise PresentationContractError("invalid scale_milli")
def validate_input_map(bindings:Sequence[InputBinding])->tuple[InputBinding,...]:
    physical=[(b.device_kind,b.control_id) for b in bindings]
    if len(set(physical))!=len(physical):raise PresentationContractError("physical control bound ambiguously")
    return tuple(sorted(bindings,key=lambda b:(b.action_id,b.device_kind,b.control_id)))

@dataclass(frozen=True)
class ControllerDescriptor:
    controller_id:str
    vendor_id:str
    product_id:str
    capabilities:tuple[str,...]
    def __post_init__(self)->None:
        require_id(self.controller_id,"controller_id");require_id(self.vendor_id,"vendor_id");require_id(self.product_id,"product_id")
        caps=tuple(sorted(self.capabilities))
        if len(set(caps))!=len(caps):raise PresentationContractError("duplicate controller capability")
        for cap in caps:require_id(cap,"controller capability")
        object.__setattr__(self,"capabilities",caps)
    def supports(self,capability:str)->bool:return require_id(capability,"capability") in self.capabilities

@dataclass(frozen=True)
class AccessibilityNode:
    node_id:str
    role:str
    name:str
    description:str
    focus_order:int|None
    enabled:bool=True
    def __post_init__(self)->None:
        require_id(self.node_id,"node_id");require_id(self.role,"role")
        if not isinstance(self.name,str) or not self.name.strip():raise PresentationContractError("accessibility name required")
        if not isinstance(self.description,str):raise PresentationContractError("invalid accessibility description")
        if self.focus_order is not None and (not _is_int(self.focus_order) or self.focus_order<0):raise PresentationContractError("invalid focus_order")
        if not isinstance(self.enabled,bool):raise PresentationContractError("enabled must be boolean")
def validate_accessibility(nodes:Sequence[AccessibilityNode])->tuple[AccessibilityNode,...]:
    ids=[n.node_id for n in nodes]
    if len(set(ids))!=len(ids):raise PresentationContractError("duplicate accessibility node")
    focus=[n.focus_order for n in nodes if n.focus_order is not None and n.enabled]
    if len(set(focus))!=len(focus):raise PresentationContractError("duplicate accessibility focus order")
    return tuple(sorted(nodes,key=lambda n:(n.focus_order if n.focus_order is not None else 10**12,n.node_id)))

@dataclass(frozen=True)
class HapticPoint:
    time_ms:int
    intensity_ppm:int
    def __post_init__(self)->None:
        if not _is_int(self.time_ms) or not 0<=self.time_ms<=MAX_DURATION_MS:raise PresentationContractError("invalid haptic time")
        if not _is_int(self.intensity_ppm) or not 0<=self.intensity_ppm<=MAX_SCORE_PPM:raise PresentationContractError("invalid haptic intensity")
def validate_haptic_envelope(points:Sequence[HapticPoint])->tuple[HapticPoint,...]:
    if not points:raise PresentationContractError("haptic envelope empty")
    ordered=tuple(points)
    times=[p.time_ms for p in ordered]
    if times!=sorted(times) or len(set(times))!=len(times):raise PresentationContractError("haptic times must strictly increase")
    return ordered

@dataclass(frozen=True)
class PresentationFrame:
    frame_id:int
    simulation_tick:int
    animation_digest:str
    audio_digest:str
    ui_digest:str
    input_digest:str
    prior_frame_digest:str|None=None
    def __post_init__(self)->None:
        if not _is_int(self.frame_id) or self.frame_id<0 or not _is_int(self.simulation_tick) or self.simulation_tick<0:raise PresentationContractError("invalid frame identity")
        for name in ("animation_digest","audio_digest","ui_digest","input_digest"):require_digest(getattr(self,name),name)
        if self.prior_frame_digest is not None:require_digest(self.prior_frame_digest,"prior_frame_digest")
        if self.frame_id==0 and self.prior_frame_digest is not None:raise PresentationContractError("genesis frame cannot have parent")
        if self.frame_id>0 and self.prior_frame_digest is None:raise PresentationContractError("presentation frame requires parent")
    @property
    def digest(self)->str:return digest_json(self.__dict__)
def append_presentation_frame(frames:Sequence[PresentationFrame],simulation_tick:int,animation_digest:str,audio_digest:str,ui_digest:str,input_digest:str)->tuple[PresentationFrame,...]:
    for i,f in enumerate(frames):
        if f.frame_id!=i:raise PresentationContractError("presentation frame sequence drift")
        expected=frames[i-1].digest if i else None
        if f.prior_frame_digest!=expected:raise PresentationContractError("presentation frame chain drift")
    prior=frames[-1].digest if frames else None
    frame=PresentationFrame(len(frames),simulation_tick,animation_digest,audio_digest,ui_digest,input_digest,prior)
    return tuple(frames)+(frame,)
