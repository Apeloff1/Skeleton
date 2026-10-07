"""FLGB-12 deterministic animation, audio, input, accessibility, haptics, and replay contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_NODES=100_000
MAX_JOINTS=16_384
MAX_LAYERS=4096
MAX_AUDIO_NODES=100_000
MAX_UI_NODES=100_000
MAX_BINDINGS=100_000
MAX_CONTROLS=4096
MAX_HAPTIC_SEGMENTS=4096
MAX_DURATION_MS=86_400_000
MAX_SCORE_PPM=1_000_000
MAX_COORD=10**12

class PresentationContractError(ValueError):
    """Fail-closed FLGB-12 contract error."""

def _is_int(value:Any)->bool: return isinstance(value,int) and not isinstance(value,bool)

def require_id(value:str,name:str)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>MAX_ID_CHARS or any(ord(ch)<32 for ch in value): raise PresentationContractError(f"invalid {name}")
    return value

def require_digest(value:str,name:str)->str:
    if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value): raise PresentationContractError(f"invalid {name}")
    return value

def digest_json(value:Any)->str:
    try: raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError) as exc: raise PresentationContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class AnimationNode:
    node_id:str
    kind:str
    inputs:tuple[str,...]
    parameter_digest:str

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id"); require_id(self.kind,"kind"); require_digest(self.parameter_digest,"parameter_digest")
        inputs=tuple(sorted(self.inputs))
        if len(set(inputs))!=len(inputs) or self.node_id in inputs: raise PresentationContractError("invalid animation inputs")
        for item in inputs: require_id(item,"animation input")
        object.__setattr__(self,"inputs",inputs)

class AnimationGraph:
    def __init__(self,nodes:Sequence[AnimationNode],output_node:str)->None:
        if not nodes or len(nodes)>MAX_NODES: raise PresentationContractError("animation node count out of bounds")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise PresentationContractError("duplicate animation node")
        output_node=require_id(output_node,"output_node")
        if output_node not in by_id: raise PresentationContractError("unknown animation output")
        for n in nodes:
            if set(n.inputs)-set(by_id): raise PresentationContractError("unknown animation input")
        self._nodes=MappingProxyType(by_id); self.output_node=output_node; self._validate()

    def _validate(self)->None:
        state={}
        def visit(node_id:str)->None:
            mark=state.get(node_id,0)
            if mark==1: raise PresentationContractError("animation graph cycle")
            if mark==2:return
            state[node_id]=1
            for dep in self._nodes[node_id].inputs: visit(dep)
            state[node_id]=2
        for node_id in sorted(self._nodes): visit(node_id)

    @property
    def digest(self)->str:return digest_json({"output_node":self.output_node,"nodes":[{"node_id":n.node_id,"kind":n.kind,"inputs":list(n.inputs),"parameter_digest":n.parameter_digest} for n in sorted(self._nodes.values(),key=lambda n:n.node_id)]})

@dataclass(frozen=True)
class SkeletonJoint:
    joint_id:str
    parent_id:str|None
    bind_pose_digest:str

    def __post_init__(self)->None:
        require_id(self.joint_id,"joint_id"); require_digest(self.bind_pose_digest,"bind_pose_digest")
        if self.parent_id is not None: require_id(self.parent_id,"parent_id")
        if self.parent_id==self.joint_id: raise PresentationContractError("joint cannot parent itself")

class Skeleton:
    def __init__(self,joints:Sequence[SkeletonJoint])->None:
        if not joints or len(joints)>MAX_JOINTS: raise PresentationContractError("joint count out of bounds")
        by_id={j.joint_id:j for j in joints}
        if len(by_id)!=len(joints): raise PresentationContractError("duplicate joint")
        roots=[j.joint_id for j in joints if j.parent_id is None]
        if len(roots)!=1: raise PresentationContractError("skeleton requires exactly one root")
        for j in joints:
            if j.parent_id is not None and j.parent_id not in by_id: raise PresentationContractError("orphan joint")
        self._joints=MappingProxyType(by_id); self.root_id=roots[0]; self._validate()

    def _validate(self)->None:
        seen=set(); active=set()
        def visit(jid:str)->None:
            if jid in active: raise PresentationContractError("skeleton cycle")
            if jid in seen:return
            active.add(jid)
            parent=self._joints[jid].parent_id
            if parent is not None: visit(parent)
            active.remove(jid); seen.add(jid)
        for jid in sorted(self._joints): visit(jid)

    @property
    def digest(self)->str:return digest_json([j.__dict__ for j in sorted(self._joints.values(),key=lambda j:j.joint_id)])

@dataclass(frozen=True)
class ProceduralLayer:
    layer_id:str
    algorithm:str
    seed_digest:str
    parameter_digest:str
    priority:int

    def __post_init__(self)->None:
        require_id(self.layer_id,"layer_id"); require_id(self.algorithm,"algorithm"); require_digest(self.seed_digest,"seed_digest"); require_digest(self.parameter_digest,"parameter_digest")
        if not _is_int(self.priority): raise PresentationContractError("invalid procedural priority")

def order_procedural_layers(layers:Sequence[ProceduralLayer])->tuple[ProceduralLayer,...]:
    if len(layers)>MAX_LAYERS: raise PresentationContractError("procedural layer budget exceeded")
    ids=[x.layer_id for x in layers]
    if len(set(ids))!=len(ids): raise PresentationContractError("duplicate procedural layer")
    return tuple(sorted(layers,key=lambda x:(x.priority,x.layer_id)))

@dataclass(frozen=True)
class AudioNode:
    node_id:str
    kind:str
    inputs:tuple[str,...]
    parameter_digest:str

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id"); require_id(self.kind,"kind"); require_digest(self.parameter_digest,"parameter_digest")
        inputs=tuple(sorted(self.inputs))
        if self.node_id in inputs or len(set(inputs))!=len(inputs): raise PresentationContractError("invalid audio inputs")
        for item in inputs: require_id(item,"audio input")
        object.__setattr__(self,"inputs",inputs)

class AudioGraph:
    def __init__(self,nodes:Sequence[AudioNode],output_node:str)->None:
        if not nodes or len(nodes)>MAX_AUDIO_NODES: raise PresentationContractError("audio node count out of bounds")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise PresentationContractError("duplicate audio node")
        output_node=require_id(output_node,"output_node")
        if output_node not in by_id: raise PresentationContractError("unknown audio output")
        for n in nodes:
            if set(n.inputs)-set(by_id): raise PresentationContractError("unknown audio input")
        self._nodes=MappingProxyType(by_id); self.output_node=output_node; self._validate()

    def _validate(self)->None:
        state={}
        def visit(nid:str)->None:
            mark=state.get(nid,0)
            if mark==1: raise PresentationContractError("audio graph cycle")
            if mark==2:return
            state[nid]=1
            for dep in self._nodes[nid].inputs: visit(dep)
            state[nid]=2
        for nid in sorted(self._nodes): visit(nid)

    @property
    def digest(self)->str:return digest_json({"output_node":self.output_node,"nodes":[{"node_id":n.node_id,"kind":n.kind,"inputs":list(n.inputs),"parameter_digest":n.parameter_digest} for n in sorted(self._nodes.values(),key=lambda n:n.node_id)]})

@dataclass(frozen=True)
class MusicState:
    state_id:str
    track_digest:str
    bpm_milli:int
    bar_beats:int
    allowed_next:tuple[str,...]=()

    def __post_init__(self)->None:
        require_id(self.state_id,"state_id"); require_digest(self.track_digest,"track_digest")
        if not _is_int(self.bpm_milli) or self.bpm_milli<=0: raise PresentationContractError("invalid bpm_milli")
        if not _is_int(self.bar_beats) or not 1<=self.bar_beats<=32: raise PresentationContractError("invalid bar_beats")
        nxt=tuple(sorted(self.allowed_next))
        if len(set(nxt))!=len(nxt) or self.state_id in nxt: raise PresentationContractError("invalid music transitions")
        for item in nxt: require_id(item,"music state")
        object.__setattr__(self,"allowed_next",nxt)

    def can_transition(self,target:str)->bool:return require_id(target,"target") in self.allowed_next

@dataclass(frozen=True)
class SpatialEmitter:
    emitter_id:str
    x_mm:int; y_mm:int; z_mm:int
    gain_milli:int
    min_distance_mm:int
    max_distance_mm:int

    def __post_init__(self)->None:
        require_id(self.emitter_id,"emitter_id")
        for name in ("x_mm","y_mm","z_mm"):
            v=getattr(self,name)
            if not _is_int(v) or abs(v)>MAX_COORD: raise PresentationContractError(f"invalid {name}")
        if not _is_int(self.gain_milli) or not 0<=self.gain_milli<=1_000_000: raise PresentationContractError("invalid gain_milli")
        if not _is_int(self.min_distance_mm) or not _is_int(self.max_distance_mm) or not 0<=self.min_distance_mm<self.max_distance_mm: raise PresentationContractError("invalid spatial distance range")

    def attenuation_milli(self,distance_mm:int)->int:
        if not _is_int(distance_mm) or distance_mm<0: raise PresentationContractError("invalid distance_mm")
        if distance_mm<=self.min_distance_mm:return self.gain_milli
        if distance_mm>=self.max_distance_mm:return 0
        span=self.max_distance_mm-self.min_distance_mm
        remaining=self.max_distance_mm-distance_mm
        return (self.gain_milli*remaining)//span

@dataclass(frozen=True)
class UILayoutNode:
    node_id:str
    parent_id:str|None
    x:int; y:int; width:int; height:int
    z_index:int

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id")
        if self.parent_id is not None: require_id(self.parent_id,"parent_id")
        if self.parent_id==self.node_id: raise PresentationContractError("UI node cannot parent itself")
        for name in ("x","y","width","height","z_index"):
            v=getattr(self,name)
            if not _is_int(v): raise PresentationContractError(f"invalid {name}")
        if self.width<0 or self.height<0: raise PresentationContractError("negative UI size")

class UILayout:
    def __init__(self,nodes:Sequence[UILayoutNode])->None:
        if len(nodes)>MAX_UI_NODES: raise PresentationContractError("UI node budget exceeded")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise PresentationContractError("duplicate UI node")
        for n in nodes:
            if n.parent_id is not None and n.parent_id not in by_id: raise PresentationContractError("orphan UI parent")
        self._nodes=MappingProxyType(by_id); self._validate()

    def _validate(self)->None:
        state={}
        def visit(nid:str)->None:
            mark=state.get(nid,0)
            if mark==1: raise PresentationContractError("UI hierarchy cycle")
            if mark==2:return
            state[nid]=1
            parent=self._nodes[nid].parent_id
            if parent is not None: visit(parent)
            state[nid]=2
        for nid in sorted(self._nodes): visit(nid)

    @property
    def paint_order(self)->tuple[str,...]: return tuple(n.node_id for n in sorted(self._nodes.values(),key=lambda n:(n.z_index,n.node_id)))

    @property
    def digest(self)->str:return digest_json([n.__dict__ for n in sorted(self._nodes.values(),key=lambda n:n.node_id)])

@dataclass(frozen=True)
class InputBinding:
    binding_id:str
    action_id:str
    device_class:str
    control:str
    modifiers:tuple[str,...]=()

    def __post_init__(self)->None:
        require_id(self.binding_id,"binding_id"); require_id(self.action_id,"action_id"); require_id(self.device_class,"device_class"); require_id(self.control,"control")
        mods=tuple(sorted(self.modifiers))
        if len(set(mods))!=len(mods): raise PresentationContractError("duplicate input modifier")
        for mod in mods: require_id(mod,"modifier")
        object.__setattr__(self,"modifiers",mods)

    @property
    def chord(self)->tuple[str,str,tuple[str,...]]: return (self.device_class,self.control,self.modifiers)

class InputMap:
    def __init__(self,bindings:Sequence[InputBinding])->None:
        if len(bindings)>MAX_BINDINGS: raise PresentationContractError("input binding budget exceeded")
        ids=[b.binding_id for b in bindings]
        if len(set(ids))!=len(ids): raise PresentationContractError("duplicate binding id")
        chords={}
        for binding in bindings:
            prior=chords.get(binding.chord)
            if prior is not None and prior!=binding.action_id: raise PresentationContractError("input chord conflict")
            chords[binding.chord]=binding.action_id
        self.bindings=tuple(sorted(bindings,key=lambda b:b.binding_id))

    @property
    def digest(self)->str:return digest_json([{"binding_id":b.binding_id,"action_id":b.action_id,"device_class":b.device_class,"control":b.control,"modifiers":list(b.modifiers)} for b in self.bindings])

@dataclass(frozen=True)
class ControllerProfile:
    controller_id:str
    vendor_id:int
    product_id:int
    controls:tuple[str,...]
    haptics:bool

    def __post_init__(self)->None:
        require_id(self.controller_id,"controller_id")
        for name in ("vendor_id","product_id"):
            v=getattr(self,name)
            if not _is_int(v) or not 0<=v<=65535: raise PresentationContractError(f"invalid {name}")
        controls=tuple(sorted(self.controls))
        if not controls or len(controls)>MAX_CONTROLS or len(set(controls))!=len(controls): raise PresentationContractError("invalid controller controls")
        for control in controls: require_id(control,"control")
        object.__setattr__(self,"controls",controls)
        if not isinstance(self.haptics,bool): raise PresentationContractError("haptics must be boolean")

    def supports(self,control:str)->bool:return require_id(control,"control") in self.controls

@dataclass(frozen=True)
class AccessibilityNode:
    node_id:str
    role:str
    label:str
    focus_order:int|None
    hidden:bool=False

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id"); require_id(self.role,"role")
        if not isinstance(self.label,str) or (not self.label.strip() and not self.hidden): raise PresentationContractError("visible accessibility node requires label")
        if self.focus_order is not None and (not _is_int(self.focus_order) or self.focus_order<0): raise PresentationContractError("invalid focus_order")
        if not isinstance(self.hidden,bool): raise PresentationContractError("hidden must be boolean")

def validate_accessibility(nodes:Sequence[AccessibilityNode])->tuple[AccessibilityNode,...]:
    ids=[n.node_id for n in nodes]
    if len(set(ids))!=len(ids): raise PresentationContractError("duplicate accessibility node")
    orders=[n.focus_order for n in nodes if n.focus_order is not None and not n.hidden]
    if len(set(orders))!=len(orders): raise PresentationContractError("duplicate focus order")
    return tuple(sorted(nodes,key=lambda n:(n.focus_order is None,n.focus_order if n.focus_order is not None else 0,n.node_id)))

@dataclass(frozen=True)
class HapticSegment:
    start_ms:int
    duration_ms:int
    low_milli:int
    high_milli:int

    def __post_init__(self)->None:
        if not _is_int(self.start_ms) or not 0<=self.start_ms<=MAX_DURATION_MS: raise PresentationContractError("invalid haptic start")
        if not _is_int(self.duration_ms) or not 1<=self.duration_ms<=MAX_DURATION_MS: raise PresentationContractError("invalid haptic duration")
        if self.start_ms+self.duration_ms>MAX_DURATION_MS: raise PresentationContractError("haptic segment exceeds duration budget")
        for name in ("low_milli","high_milli"):
            v=getattr(self,name)
            if not _is_int(v) or not 0<=v<=1000: raise PresentationContractError(f"invalid {name}")

class HapticPattern:
    def __init__(self,pattern_id:str,segments:Sequence[HapticSegment])->None:
        self.pattern_id=require_id(pattern_id,"pattern_id")
        if not segments or len(segments)>MAX_HAPTIC_SEGMENTS: raise PresentationContractError("haptic segment count out of bounds")
        ordered=tuple(sorted(segments,key=lambda s:s.start_ms))
        for i in range(1,len(ordered)):
            if ordered[i].start_ms<ordered[i-1].start_ms+ordered[i-1].duration_ms: raise PresentationContractError("haptic segments overlap")
        self.segments=ordered

    @property
    def digest(self)->str:return digest_json({"pattern_id":self.pattern_id,"segments":[s.__dict__ for s in self.segments]})

@dataclass(frozen=True)
class PresentationFrame:
    frame_id:int
    input_digest:str
    animation_digest:str
    audio_digest:str
    ui_digest:str
    haptic_digest:str
    presentation_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.frame_id) or self.frame_id<0: raise PresentationContractError("invalid frame_id")
        for name in ("input_digest","animation_digest","audio_digest","ui_digest","haptic_digest","presentation_digest"): require_digest(getattr(self,name),name)

    @property
    def digest(self)->str:return digest_json(self.__dict__)

class PresentationReplay:
    def __init__(self,frames:Sequence[PresentationFrame]=())->None:
        for index,frame in enumerate(frames):
            if frame.frame_id!=index: raise PresentationContractError("presentation frame sequence drift")
        self.frames=tuple(frames)

    def append(self,input_digest:str,animation_digest:str,audio_digest:str,ui_digest:str,haptic_digest:str,presentation_digest:str)->"PresentationReplay":
        frame=PresentationFrame(len(self.frames),require_digest(input_digest,"input_digest"),require_digest(animation_digest,"animation_digest"),require_digest(audio_digest,"audio_digest"),require_digest(ui_digest,"ui_digest"),require_digest(haptic_digest,"haptic_digest"),require_digest(presentation_digest,"presentation_digest"))
        return PresentationReplay(self.frames+(frame,))

    @property
    def digest(self)->str:return digest_json([f.digest for f in self.frames])
