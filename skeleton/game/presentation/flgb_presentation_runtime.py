"""FLGB-12 deterministic animation, audio, UI, input, accessibility, and replay contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_NODES=100_000
MAX_BONES=16_384
MAX_CHANNELS=4096
MAX_UI_NODES=100_000
MAX_BINDINGS=100_000
MAX_HAPTIC_SEGMENTS=4096
MAX_COORD=10**12
MAX_DURATION_MS=24*60*60*1000
MAX_SCORE_PPM=1_000_000

class PresentationContractError(ValueError):
    """Fail-closed FLGB-12 contract error."""

def _is_int(value:Any)->bool:return isinstance(value,int) and not isinstance(value,bool)

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
class AnimationState:
    state_id:str
    clip_digest:str
    loop:bool

    def __post_init__(self)->None:
        require_id(self.state_id,"state_id"); require_digest(self.clip_digest,"clip_digest")
        if not isinstance(self.loop,bool): raise PresentationContractError("loop must be boolean")

@dataclass(frozen=True)
class AnimationTransition:
    transition_id:str
    source_state:str
    target_state:str
    condition_digest:str
    priority:int
    blend_ms:int

    def __post_init__(self)->None:
        require_id(self.transition_id,"transition_id"); require_id(self.source_state,"source_state"); require_id(self.target_state,"target_state"); require_digest(self.condition_digest,"condition_digest")
        if self.source_state==self.target_state: raise PresentationContractError("self animation transition forbidden")
        if not _is_int(self.priority): raise PresentationContractError("invalid transition priority")
        if not _is_int(self.blend_ms) or not 0<=self.blend_ms<=MAX_DURATION_MS: raise PresentationContractError("invalid blend_ms")

class AnimationGraph:
    def __init__(self,states:Sequence[AnimationState],transitions:Sequence[AnimationTransition],initial_state:str)->None:
        if not states or len(states)>MAX_NODES or len(transitions)>MAX_NODES: raise PresentationContractError("animation graph size out of bounds")
        by_state={s.state_id:s for s in states}
        if len(by_state)!=len(states): raise PresentationContractError("duplicate animation state")
        initial_state=require_id(initial_state,"initial_state")
        if initial_state not in by_state: raise PresentationContractError("unknown initial state")
        transition_ids=set()
        for t in transitions:
            if t.transition_id in transition_ids: raise PresentationContractError("duplicate animation transition")
            transition_ids.add(t.transition_id)
            if t.source_state not in by_state or t.target_state not in by_state: raise PresentationContractError("animation transition references unknown state")
        self._states=MappingProxyType(by_state); self.transitions=tuple(transitions); self.initial_state=initial_state

    def resolve(self,current_state:str,satisfied_transition_ids:Sequence[str])->str:
        current_state=require_id(current_state,"current_state")
        if current_state not in self._states: raise PresentationContractError("unknown current state")
        satisfied=set(satisfied_transition_ids)
        if len(satisfied)!=len(tuple(satisfied_transition_ids)): raise PresentationContractError("duplicate satisfied transition")
        candidates=[t for t in self.transitions if t.source_state==current_state and t.transition_id in satisfied]
        if not candidates:return current_state
        return sorted(candidates,key=lambda t:(-t.priority,t.transition_id))[0].target_state

    @property
    def digest(self)->str:return digest_json({"initial_state":self.initial_state,"states":[s.__dict__ for s in sorted(self._states.values(),key=lambda s:s.state_id)],"transitions":[t.__dict__ for t in sorted(self.transitions,key=lambda t:t.transition_id)]})

@dataclass(frozen=True)
class Bone:
    bone_id:str
    parent_id:str|None
    bind_pose_digest:str

    def __post_init__(self)->None:
        require_id(self.bone_id,"bone_id")
        if self.parent_id is not None:require_id(self.parent_id,"parent_id")
        if self.parent_id==self.bone_id:raise PresentationContractError("bone cannot parent itself")
        require_digest(self.bind_pose_digest,"bind_pose_digest")

class Skeleton:
    def __init__(self,bones:Sequence[Bone])->None:
        if not bones or len(bones)>MAX_BONES:raise PresentationContractError("skeleton bone count out of bounds")
        by_id={b.bone_id:b for b in bones}
        if len(by_id)!=len(bones):raise PresentationContractError("duplicate bone")
        for bone in bones:
            if bone.parent_id is not None and bone.parent_id not in by_id:raise PresentationContractError("orphan bone")
        self._bones=MappingProxyType(by_id); self._validate()

    def _validate(self)->None:
        state={}
        def visit(bone_id:str)->None:
            mark=state.get(bone_id,0)
            if mark==1:raise PresentationContractError("skeleton cycle")
            if mark==2:return
            state[bone_id]=1; parent=self._bones[bone_id].parent_id
            if parent is not None:visit(parent)
            state[bone_id]=2
        for bone_id in sorted(self._bones):visit(bone_id)

    @property
    def digest(self)->str:return digest_json([b.__dict__ for b in sorted(self._bones.values(),key=lambda b:b.bone_id)])

@dataclass(frozen=True)
class Pose:
    skeleton_digest:str
    local_pose_digests:Mapping[str,str]

    def __post_init__(self)->None:
        require_digest(self.skeleton_digest,"skeleton_digest")
        values=dict(self.local_pose_digests)
        if len(values)>MAX_BONES:raise PresentationContractError("pose bone budget exceeded")
        for bone_id,pose_digest in values.items():require_id(bone_id,"bone_id");require_digest(pose_digest,"pose_digest")
        object.__setattr__(self,"local_pose_digests",MappingProxyType(dict(sorted(values.items()))))

    @property
    def digest(self)->str:return digest_json({"skeleton_digest":self.skeleton_digest,"local_pose_digests":dict(self.local_pose_digests)})

@dataclass(frozen=True)
class ProceduralLayer:
    layer_id:str
    algorithm_id:str
    seed_digest:str
    input_pose_digest:str
    parameter_digest:str
    weight_ppm:int

    def __post_init__(self)->None:
        require_id(self.layer_id,"layer_id");require_id(self.algorithm_id,"algorithm_id")
        for name in ("seed_digest","input_pose_digest","parameter_digest"):require_digest(getattr(self,name),name)
        if not _is_int(self.weight_ppm) or not 0<=self.weight_ppm<=MAX_SCORE_PPM:raise PresentationContractError("invalid procedural weight")

    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class AudioNode:
    node_id:str
    kind:str
    inputs:tuple[str,...]
    parameter_digest:str

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id");require_id(self.kind,"kind");require_digest(self.parameter_digest,"parameter_digest")
        inputs=tuple(sorted(self.inputs))
        if self.node_id in inputs or len(set(inputs))!=len(inputs):raise PresentationContractError("invalid audio graph inputs")
        for item in inputs:require_id(item,"audio input")
        object.__setattr__(self,"inputs",inputs)

class AudioGraph:
    def __init__(self,nodes:Sequence[AudioNode],output_node:str)->None:
        if not nodes or len(nodes)>MAX_NODES:raise PresentationContractError("audio graph size out of bounds")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes):raise PresentationContractError("duplicate audio node")
        output_node=require_id(output_node,"output_node")
        if output_node not in by_id:raise PresentationContractError("unknown audio output")
        for node in nodes:
            if set(node.inputs)-set(by_id):raise PresentationContractError("unknown audio input")
        self._nodes=MappingProxyType(by_id);self.output_node=output_node;self._validate()

    def _validate(self)->None:
        state={}
        def visit(node_id:str)->None:
            mark=state.get(node_id,0)
            if mark==1:raise PresentationContractError("audio graph cycle")
            if mark==2:return
            state[node_id]=1
            for dep in self._nodes[node_id].inputs:visit(dep)
            state[node_id]=2
        for node_id in sorted(self._nodes):visit(node_id)

    @property
    def digest(self)->str:return digest_json({"output_node":self.output_node,"nodes":[{"node_id":n.node_id,"kind":n.kind,"inputs":list(n.inputs),"parameter_digest":n.parameter_digest} for n in sorted(self._nodes.values(),key=lambda n:n.node_id)]})

@dataclass(frozen=True)
class MusicState:
    state_id:str
    stem_digests:tuple[str,...]
    bpm_milli:int
    beats_per_bar:int

    def __post_init__(self)->None:
        require_id(self.state_id,"state_id")
        stems=tuple(sorted(self.stem_digests))
        if not stems or len(stems)>MAX_CHANNELS or len(set(stems))!=len(stems):raise PresentationContractError("invalid music stems")
        for stem in stems:require_digest(stem,"stem_digest")
        object.__setattr__(self,"stem_digests",stems)
        if not _is_int(self.bpm_milli) or not 1<=self.bpm_milli<=1_000_000:raise PresentationContractError("invalid bpm")
        if not _is_int(self.beats_per_bar) or not 1<=self.beats_per_bar<=32:raise PresentationContractError("invalid beats_per_bar")

    def next_bar_boundary_ms(self,elapsed_ms:int)->int:
        if not _is_int(elapsed_ms) or elapsed_ms<0:raise PresentationContractError("invalid elapsed_ms")
        bar_num=60_000_000*self.beats_per_bar
        bar_ms=max(1,bar_num//self.bpm_milli)
        return ((elapsed_ms+bar_ms-1)//bar_ms)*bar_ms

@dataclass(frozen=True)
class SpatialSource:
    source_id:str
    x:int;y:int;z:int
    gain_ppm:int
    max_distance:int

    def __post_init__(self)->None:
        require_id(self.source_id,"source_id")
        for name in ("x","y","z"):
            value=getattr(self,name)
            if not _is_int(value) or abs(value)>MAX_COORD:raise PresentationContractError(f"invalid {name}")
        if not _is_int(self.gain_ppm) or not 0<=self.gain_ppm<=MAX_SCORE_PPM:raise PresentationContractError("invalid gain_ppm")
        if not _is_int(self.max_distance) or not 1<=self.max_distance<=MAX_COORD:raise PresentationContractError("invalid max_distance")

    def attenuated_gain(self,listener:tuple[int,int,int])->int:
        if len(listener)!=3 or any(not _is_int(v) for v in listener):raise PresentationContractError("invalid listener position")
        dx=self.x-listener[0];dy=self.y-listener[1];dz=self.z-listener[2];d2=dx*dx+dy*dy+dz*dz
        if d2>=self.max_distance*self.max_distance:return 0
        return (self.gain_ppm*(self.max_distance*self.max_distance-d2))//(self.max_distance*self.max_distance)

@dataclass(frozen=True)
class UINode:
    node_id:str
    parent_id:str|None
    x:int;y:int;width:int;height:int
    z_index:int=0

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id")
        if self.parent_id is not None:require_id(self.parent_id,"parent_id")
        if self.parent_id==self.node_id:raise PresentationContractError("UI node cannot parent itself")
        for name in ("x","y","width","height","z_index"):
            value=getattr(self,name)
            if not _is_int(value):raise PresentationContractError(f"invalid {name}")
        if self.width<0 or self.height<0:raise PresentationContractError("negative UI extent")

class UILayout:
    def __init__(self,nodes:Sequence[UINode])->None:
        if len(nodes)>MAX_UI_NODES:raise PresentationContractError("UI node budget exceeded")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes):raise PresentationContractError("duplicate UI node")
        for node in nodes:
            if node.parent_id is not None and node.parent_id not in by_id:raise PresentationContractError("orphan UI parent")
        self._nodes=MappingProxyType(by_id);self._validate()

    def _validate(self)->None:
        state={}
        def visit(node_id:str)->None:
            mark=state.get(node_id,0)
            if mark==1:raise PresentationContractError("UI hierarchy cycle")
            if mark==2:return
            state[node_id]=1;parent=self._nodes[node_id].parent_id
            if parent is not None:visit(parent)
            state[node_id]=2
        for node_id in sorted(self._nodes):visit(node_id)

    @property
    def paint_order(self)->tuple[str,...]:return tuple(n.node_id for n in sorted(self._nodes.values(),key=lambda n:(n.z_index,n.node_id)))

@dataclass(frozen=True)
class InputBinding:
    binding_id:str
    action_id:str
    device_class:str
    control_path:str
    modifiers:tuple[str,...]=()

    def __post_init__(self)->None:
        require_id(self.binding_id,"binding_id");require_id(self.action_id,"action_id");require_id(self.device_class,"device_class");require_id(self.control_path,"control_path")
        mods=tuple(sorted(self.modifiers))
        if len(set(mods))!=len(mods):raise PresentationContractError("duplicate input modifier")
        for mod in mods:require_id(mod,"modifier")
        object.__setattr__(self,"modifiers",mods)

class InputMap:
    def __init__(self,bindings:Sequence[InputBinding])->None:
        if len(bindings)>MAX_BINDINGS:raise PresentationContractError("input binding budget exceeded")
        ids=[b.binding_id for b in bindings]
        if len(set(ids))!=len(ids):raise PresentationContractError("duplicate binding id")
        chords=set()
        for binding in bindings:
            chord=(binding.device_class,binding.control_path,binding.modifiers)
            if chord in chords:raise PresentationContractError("ambiguous input chord")
            chords.add(chord)
        self.bindings=tuple(sorted(bindings,key=lambda b:b.binding_id))

    def actions_for_device(self,device_class:str)->tuple[str,...]:
        device_class=require_id(device_class,"device_class")
        return tuple(sorted({b.action_id for b in self.bindings if b.device_class==device_class}))

@dataclass(frozen=True)
class ControllerProfile:
    controller_id:str
    vendor_id:int
    product_id:int
    controls:tuple[str,...]
    rumble_supported:bool

    def __post_init__(self)->None:
        require_id(self.controller_id,"controller_id")
        for name in ("vendor_id","product_id"):
            value=getattr(self,name)
            if not _is_int(value) or not 0<=value<=65535:raise PresentationContractError(f"invalid {name}")
        controls=tuple(sorted(self.controls))
        if not controls or len(set(controls))!=len(controls):raise PresentationContractError("invalid controller controls")
        for control in controls:require_id(control,"control")
        object.__setattr__(self,"controls",controls)
        if not isinstance(self.rumble_supported,bool):raise PresentationContractError("rumble_supported must be boolean")

    def supports(self,control:str)->bool:return require_id(control,"control") in self.controls

@dataclass(frozen=True)
class AccessibilityNode:
    node_id:str
    role:str
    label:str
    focusable:bool
    order:int

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id")
        if self.role not in {"button","link","text","heading","image","slider","checkbox","dialog","list","listitem","status"}:raise PresentationContractError("invalid accessibility role")
        if not isinstance(self.label,str) or not self.label.strip() or len(self.label)>4096:raise PresentationContractError("invalid accessibility label")
        if not isinstance(self.focusable,bool):raise PresentationContractError("focusable must be boolean")
        if not _is_int(self.order) or self.order<0:raise PresentationContractError("invalid accessibility order")

def accessibility_focus_order(nodes:Sequence[AccessibilityNode])->tuple[str,...]:
    ids=[n.node_id for n in nodes]
    if len(set(ids))!=len(ids):raise PresentationContractError("duplicate accessibility node")
    return tuple(n.node_id for n in sorted((n for n in nodes if n.focusable),key=lambda n:(n.order,n.node_id)))

@dataclass(frozen=True)
class HapticSegment:
    duration_ms:int
    low_motor_ppm:int
    high_motor_ppm:int

    def __post_init__(self)->None:
        if not _is_int(self.duration_ms) or not 1<=self.duration_ms<=MAX_DURATION_MS:raise PresentationContractError("invalid haptic duration")
        for name in ("low_motor_ppm","high_motor_ppm"):
            value=getattr(self,name)
            if not _is_int(value) or not 0<=value<=MAX_SCORE_PPM:raise PresentationContractError(f"invalid {name}")

@dataclass(frozen=True)
class HapticPattern:
    pattern_id:str
    segments:tuple[HapticSegment,...]

    def __post_init__(self)->None:
        require_id(self.pattern_id,"pattern_id")
        if not self.segments or len(self.segments)>MAX_HAPTIC_SEGMENTS:raise PresentationContractError("haptic segment count out of bounds")

    @property
    def total_duration_ms(self)->int:return sum(s.duration_ms for s in self.segments)

    @property
    def digest(self)->str:return digest_json({"pattern_id":self.pattern_id,"segments":[s.__dict__ for s in self.segments]})

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
        if not _is_int(self.frame_id) or self.frame_id<0:raise PresentationContractError("invalid frame_id")
        if not _is_int(self.simulation_tick) or self.simulation_tick<0:raise PresentationContractError("invalid simulation_tick")
        for name in ("animation_digest","audio_digest","ui_digest","input_digest"):require_digest(getattr(self,name),name)
        if self.prior_frame_digest is not None:require_digest(self.prior_frame_digest,"prior_frame_digest")
        if self.frame_id==0 and self.prior_frame_digest is not None:raise PresentationContractError("genesis presentation frame cannot have parent")
        if self.frame_id>0 and self.prior_frame_digest is None:raise PresentationContractError("presentation frame requires parent")

    @property
    def digest(self)->str:return digest_json(self.__dict__)

class PresentationReplay:
    def __init__(self,frames:Sequence[PresentationFrame]=())->None:
        for index,frame in enumerate(frames):
            if frame.frame_id!=index:raise PresentationContractError("presentation frame sequence drift")
            expected=frames[index-1].digest if index else None
            if frame.prior_frame_digest!=expected:raise PresentationContractError("presentation replay chain drift")
        self.frames=tuple(frames)

    def append(self,simulation_tick:int,animation_digest:str,audio_digest:str,ui_digest:str,input_digest:str)->"PresentationReplay":
        prior=self.frames[-1].digest if self.frames else None
        frame=PresentationFrame(len(self.frames),simulation_tick,animation_digest,audio_digest,ui_digest,input_digest,prior)
        return PresentationReplay(self.frames+(frame,))

    @property
    def digest(self)->str:return digest_json([frame.digest for frame in self.frames])
