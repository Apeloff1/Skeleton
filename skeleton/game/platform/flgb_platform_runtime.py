"""FLGB-15 deterministic game networking, save, mod, localization, and platform contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID=256;MAX_MESSAGE_BYTES=16_000_000;MAX_REPL_FIELDS=100_000;MAX_ROLLBACK=10_000;MAX_CAPS=1024;MAX_SAVE_FIELDS=10000;MAX_SCORE=1_000_000
class PlatformContractError(ValueError):pass
def _int(v:Any)->bool:return isinstance(v,int) and not isinstance(v,bool)
def rid(v:str,n:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID:raise PlatformContractError(f"invalid {n}")
    return v
def rdig(v:str,n:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):raise PlatformContractError(f"invalid {n}")
    return v
def dig(v:Any)->str:return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class ProtocolEnvelope:
    protocol_id:str;version:int;session_id:str;sequence:int;message_type:str;payload_digest:str;payload_bytes:int
    def __post_init__(self):
        rid(self.protocol_id,"protocol_id");rid(self.session_id,"session_id");rid(self.message_type,"message_type");rdig(self.payload_digest,"payload_digest")
        if not _int(self.version) or self.version<1:raise PlatformContractError("invalid protocol version")
        if not _int(self.sequence) or self.sequence<0:raise PlatformContractError("invalid protocol sequence")
        if not _int(self.payload_bytes) or not 0<=self.payload_bytes<=MAX_MESSAGE_BYTES:raise PlatformContractError("invalid payload size")
    @property
    def digest(self):return dig(self.__dict__)

def validate_protocol_sequence(messages:Sequence[ProtocolEnvelope])->tuple[ProtocolEnvelope,...]:
    if not messages:return ()
    session=messages[0].session_id;version=messages[0].version;protocol=messages[0].protocol_id
    for i,msg in enumerate(messages):
        if msg.session_id!=session or msg.version!=version or msg.protocol_id!=protocol or msg.sequence!=i:raise PlatformContractError("protocol sequence drift")
    return tuple(messages)

@dataclass(frozen=True)
class ReplicatedField:
    field_id:str;value_digest:str
    def __post_init__(self):rid(self.field_id,"field_id");rdig(self.value_digest,"value_digest")

@dataclass(frozen=True)
class ReplicationDelta:
    entity_id:str;base_revision:int;target_revision:int;fields:tuple[ReplicatedField,...]
    def __post_init__(self):
        rid(self.entity_id,"entity_id")
        if not _int(self.base_revision) or not _int(self.target_revision) or self.base_revision<0 or self.target_revision!=self.base_revision+1:raise PlatformContractError("replication revision must advance once")
        fields=tuple(sorted(self.fields,key=lambda f:f.field_id))
        if len(fields)>MAX_REPL_FIELDS or len({f.field_id for f in fields})!=len(fields):raise PlatformContractError("invalid replicated fields")
        object.__setattr__(self,"fields",fields)
    @property
    def digest(self):return dig({"entity_id":self.entity_id,"base_revision":self.base_revision,"target_revision":self.target_revision,"fields":[f.__dict__ for f in self.fields]})

@dataclass(frozen=True)
class PredictionFrame:
    tick:int;input_digest:str;predicted_state_digest:str;prior_frame_digest:str|None=None
    def __post_init__(self):
        if not _int(self.tick) or self.tick<0:raise PlatformContractError("invalid prediction tick")
        rdig(self.input_digest,"input_digest");rdig(self.predicted_state_digest,"predicted_state_digest")
        if self.prior_frame_digest is not None:rdig(self.prior_frame_digest,"prior_frame_digest")
        if self.tick==0 and self.prior_frame_digest is not None:raise PlatformContractError("genesis prediction cannot have parent")
        if self.tick>0 and self.prior_frame_digest is None:raise PlatformContractError("prediction frame requires parent")
    @property
    def digest(self):return dig(self.__dict__)

@dataclass(frozen=True)
class RollbackCorrection:
    authoritative_tick:int;authoritative_state_digest:str;predicted_state_digest:str;replay_input_digests:tuple[str,...]
    def __post_init__(self):
        if not _int(self.authoritative_tick) or self.authoritative_tick<0:raise PlatformContractError("invalid authoritative tick")
        rdig(self.authoritative_state_digest,"authoritative_state_digest");rdig(self.predicted_state_digest,"predicted_state_digest")
        if len(self.replay_input_digests)>MAX_ROLLBACK:raise PlatformContractError("rollback window exceeded")
        for value in self.replay_input_digests:rdig(value,"replay_input_digest")
    @property
    def correction_required(self):return self.authoritative_state_digest!=self.predicted_state_digest

@dataclass(frozen=True)
class SaveField:
    field_id:str;type_id:str;required:bool
    def __post_init__(self):rid(self.field_id,"field_id");rid(self.type_id,"type_id");

@dataclass(frozen=True)
class SaveSchema:
    schema_id:str;version:int;fields:tuple[SaveField,...]
    def __post_init__(self):
        rid(self.schema_id,"schema_id")
        if not _int(self.version) or self.version<1:raise PlatformContractError("invalid save version")
        fields=tuple(sorted(self.fields,key=lambda f:f.field_id))
        if len(fields)>MAX_SAVE_FIELDS or len({f.field_id for f in fields})!=len(fields):raise PlatformContractError("invalid save fields")
        object.__setattr__(self,"fields",fields)
    @property
    def digest(self):return dig({"schema_id":self.schema_id,"version":self.version,"fields":[f.__dict__ for f in self.fields]})

@dataclass(frozen=True)
class CloudSaveRevision:
    save_id:str;revision:int;content_digest:str;parent_digest:str|None;device_id:str
    def __post_init__(self):
        rid(self.save_id,"save_id");rid(self.device_id,"device_id");rdig(self.content_digest,"content_digest")
        if not _int(self.revision) or self.revision<0:raise PlatformContractError("invalid cloud revision")
        if self.parent_digest is not None:rdig(self.parent_digest,"parent_digest")
        if self.revision==0 and self.parent_digest is not None:raise PlatformContractError("genesis cloud save cannot have parent")
        if self.revision>0 and self.parent_digest is None:raise PlatformContractError("cloud revision requires parent")
    @property
    def digest(self):return dig(self.__dict__)

def resolve_cloud_save(left:CloudSaveRevision,right:CloudSaveRevision)->CloudSaveRevision:
    if left.save_id!=right.save_id:raise PlatformContractError("cross-save conflict")
    if left.digest==right.digest:return left
    if left.revision!=right.revision: return left if left.revision>right.revision else right
    raise PlatformContractError("concurrent cloud-save conflict requires explicit merge")

def _caps(values:Sequence[str])->tuple[str,...]:
    caps=tuple(sorted(values))
    if len(caps)>MAX_CAPS or len(set(caps))!=len(caps):raise PlatformContractError("invalid capabilities")
    for cap in caps:rid(cap,"capability")
    return caps

@dataclass(frozen=True)
class ModManifest:
    mod_id:str;version:str;content_digest:str;api_version:str;requested_capabilities:tuple[str,...]
    def __post_init__(self):
        rid(self.mod_id,"mod_id");rid(self.version,"version");rdig(self.content_digest,"content_digest");rid(self.api_version,"api_version")
        object.__setattr__(self,"requested_capabilities",_caps(self.requested_capabilities))
    @property
    def digest(self):return dig({"mod_id":self.mod_id,"version":self.version,"content_digest":self.content_digest,"api_version":self.api_version,"requested_capabilities":list(self.requested_capabilities)})

@dataclass(frozen=True)
class PluginIsolationPolicy:
    allowed_capabilities:tuple[str,...];memory_bytes:int;cpu_ms:int;network_mode:str
    def __post_init__(self):
        object.__setattr__(self,"allowed_capabilities",_caps(self.allowed_capabilities))
        if not _int(self.memory_bytes) or self.memory_bytes<=0 or not _int(self.cpu_ms) or self.cpu_ms<=0:raise PlatformContractError("invalid plugin budget")
        if self.network_mode not in {"deny","allowlisted-read","allowlisted"}:raise PlatformContractError("invalid plugin network mode")
    def authorizes(self,manifest:ModManifest)->bool:return set(manifest.requested_capabilities).issubset(self.allowed_capabilities)

@dataclass(frozen=True)
class LocalizationEntry:
    key:str;text_digest:str
    def __post_init__(self):rid(self.key,"localization key");rdig(self.text_digest,"text_digest")

class LocalizationCatalog:
    def __init__(self,locale:str,entries:Sequence[LocalizationEntry],fallback_locale:str|None=None):
        self.locale=rid(locale,"locale");self.fallback_locale=None if fallback_locale is None else rid(fallback_locale,"fallback_locale")
        if self.fallback_locale==self.locale:raise PlatformContractError("locale cannot fall back to itself")
        mapping={e.key:e for e in entries}
        if len(mapping)!=len(entries):raise PlatformContractError("duplicate localization key")
        self._entries=MappingProxyType(mapping)
    def resolve(self,key:str)->str:
        try:return self._entries[rid(key,"localization key")].text_digest
        except KeyError as exc:raise PlatformContractError("missing localization key") from exc

@dataclass(frozen=True)
class PlatformIdentity:
    platform:str;account_subject_digest:str;display_handle_digest:str
    def __post_init__(self):rid(self.platform,"platform");rdig(self.account_subject_digest,"account_subject_digest");rdig(self.display_handle_digest,"display_handle_digest")
    @property
    def digest(self):return dig(self.__dict__)

@dataclass(frozen=True)
class Achievement:
    achievement_id:str;target:int;hidden:bool
    def __post_init__(self):
        rid(self.achievement_id,"achievement_id")
        if not _int(self.target) or self.target<=0:raise PlatformContractError("invalid achievement target")
        if not isinstance(self.hidden,bool):raise PlatformContractError("hidden must be boolean")

@dataclass(frozen=True)
class AchievementProgress:
    definition:Achievement;current:int=0
    def __post_init__(self):
        if not _int(self.current) or not 0<=self.current<=self.definition.target:raise PlatformContractError("invalid achievement progress")
    def advance(self,value:int)->"AchievementProgress":
        if not _int(value) or value<self.current:raise PlatformContractError("achievement progress cannot regress")
        return AchievementProgress(self.definition,min(value,self.definition.target))
    @property
    def unlocked(self):return self.current>=self.definition.target

@dataclass(frozen=True)
class VersionMigration:
    step_id:str;from_version:int;to_version:int;transform_digest:str;backward_compatible:bool
    def __post_init__(self):
        rid(self.step_id,"step_id");rdig(self.transform_digest,"transform_digest")
        if not _int(self.from_version) or not _int(self.to_version) or self.from_version<1 or self.to_version!=self.from_version+1:raise PlatformContractError("migration must advance one version")
        if not isinstance(self.backward_compatible,bool):raise PlatformContractError("backward_compatible must be boolean")

def validate_version_path(steps:Sequence[VersionMigration],start:int,target:int)->tuple[VersionMigration,...]:
    if not _int(start) or not _int(target) or start<1 or target<start:raise PlatformContractError("invalid version bounds")
    current=start
    for step in steps:
        if step.from_version!=current:raise PlatformContractError("migration path gap")
        current=step.to_version
    if current!=target:raise PlatformContractError("migration target not reached")
    return tuple(steps)
