"""FLGB-15 deterministic networking, saves, mods, localization, and platform contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence
MAX_ID=256; MAX_ITEMS=100000; MAX_TICK=2**63-1
class PlatformContractError(ValueError): pass
def _int(v): return isinstance(v,int) and not isinstance(v,bool)
def req_id(v,n):
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID: raise PlatformContractError(f"invalid {n}")
    return v
def req_digest(v,n):
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise PlatformContractError(f"invalid {n}")
    return v
def dig(v):
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode()
    except (TypeError,ValueError) as exc: raise PlatformContractError("non-canonical value") from exc
    return sha256(raw).hexdigest()
@dataclass(frozen=True)
class NetworkProtocol:
    protocol_id:str; version:int; schema_digest:str; max_packet_bytes:int; compatibility_floor:int
    def __post_init__(self):
        req_id(self.protocol_id,"protocol_id"); req_digest(self.schema_digest,"schema_digest")
        if not _int(self.version) or self.version<1 or not _int(self.compatibility_floor) or not 1<=self.compatibility_floor<=self.version: raise PlatformContractError("invalid protocol version")
        if not _int(self.max_packet_bytes) or not 1<=self.max_packet_bytes<=16*1024*1024: raise PlatformContractError("invalid packet budget")
    def compatible(self,peer_version:int)->bool: return _int(peer_version) and self.compatibility_floor<=peer_version<=self.version
@dataclass(frozen=True)
class ReplicatedField:
    entity_id:str; field_id:str; tick:int; value_digest:str; authority_id:str
    def __post_init__(self):
        req_id(self.entity_id,"entity_id"); req_id(self.field_id,"field_id"); req_id(self.authority_id,"authority_id"); req_digest(self.value_digest,"value_digest")
        if not _int(self.tick) or not 0<=self.tick<=MAX_TICK: raise PlatformContractError("invalid replication tick")
def merge_replication(records:Sequence[ReplicatedField])->tuple[ReplicatedField,...]:
    best={}
    for r in records:
        key=(r.entity_id,r.field_id); prior=best.get(key)
        if prior is None or (r.tick,r.authority_id)>(prior.tick,prior.authority_id): best[key]=r
    return tuple(sorted(best.values(),key=lambda r:(r.entity_id,r.field_id)))
@dataclass(frozen=True)
class PredictionFrame:
    tick:int; input_digest:str; predicted_state_digest:str; authoritative_state_digest:str|None=None
    def __post_init__(self):
        if not _int(self.tick) or self.tick<0: raise PlatformContractError("invalid prediction tick")
        req_digest(self.input_digest,"input_digest"); req_digest(self.predicted_state_digest,"predicted_state_digest")
        if self.authoritative_state_digest is not None: req_digest(self.authoritative_state_digest,"authoritative_state_digest")
    @property
    def reconciled(self): return self.authoritative_state_digest is None or self.predicted_state_digest==self.authoritative_state_digest
@dataclass(frozen=True)
class RollbackFrame:
    tick:int; state_digest:str; input_digest:str; prior_frame_digest:str|None=None
    def __post_init__(self):
        if not _int(self.tick) or self.tick<0: raise PlatformContractError("invalid rollback tick")
        req_digest(self.state_digest,"state_digest"); req_digest(self.input_digest,"input_digest")
        if self.prior_frame_digest is not None: req_digest(self.prior_frame_digest,"prior_frame_digest")
        if self.tick==0 and self.prior_frame_digest is not None: raise PlatformContractError("genesis rollback frame cannot have parent")
        if self.tick>0 and self.prior_frame_digest is None: raise PlatformContractError("rollback frame requires parent")
    @property
    def digest(self): return dig(self.__dict__)
def validate_rollback_chain(frames:Sequence[RollbackFrame])->None:
    for i,f in enumerate(frames):
        if f.tick!=i: raise PlatformContractError("rollback tick drift")
        expected=frames[i-1].digest if i else None
        if f.prior_frame_digest!=expected: raise PlatformContractError("rollback chain drift")
@dataclass(frozen=True)
class SaveSchema:
    schema_id:str; version:int; state_digest:str; world_digest:str; metadata_digest:str
    def __post_init__(self):
        req_id(self.schema_id,"schema_id");
        if not _int(self.version) or self.version<1: raise PlatformContractError("invalid save version")
        for n in ("state_digest","world_digest","metadata_digest"): req_digest(getattr(self,n),n)
    @property
    def digest(self): return dig(self.__dict__)
@dataclass(frozen=True)
class CloudSaveRevision:
    slot_id:str; revision:int; save_digest:str; device_id:str; parent_digest:str|None=None
    def __post_init__(self):
        req_id(self.slot_id,"slot_id"); req_id(self.device_id,"device_id"); req_digest(self.save_digest,"save_digest")
        if not _int(self.revision) or self.revision<0: raise PlatformContractError("invalid cloud revision")
        if self.parent_digest is not None: req_digest(self.parent_digest,"parent_digest")
        if self.revision==0 and self.parent_digest is not None: raise PlatformContractError("genesis cloud save cannot have parent")
        if self.revision>0 and self.parent_digest is None: raise PlatformContractError("cloud revision requires parent")
    @property
    def digest(self): return dig(self.__dict__)
@dataclass(frozen=True)
class ModManifest:
    mod_id:str; version:str; api_version:int; capability_requests:tuple[str,...]; content_digest:str; signer_digest:str|None=None
    def __post_init__(self):
        req_id(self.mod_id,"mod_id"); req_id(self.version,"version"); req_digest(self.content_digest,"content_digest")
        if not _int(self.api_version) or self.api_version<1: raise PlatformContractError("invalid mod api version")
        caps=tuple(sorted(self.capability_requests));
        if len(set(caps))!=len(caps): raise PlatformContractError("duplicate mod capability")
        for c in caps: req_id(c,"capability")
        object.__setattr__(self,"capability_requests",caps)
        if self.signer_digest is not None: req_digest(self.signer_digest,"signer_digest")
@dataclass(frozen=True)
class PluginPolicy:
    plugin_id:str; allowed_capabilities:tuple[str,...]; writable_roots:tuple[str,...]; network_mode:str
    def __post_init__(self):
        req_id(self.plugin_id,"plugin_id"); caps=tuple(sorted(self.allowed_capabilities)); roots=tuple(sorted(self.writable_roots))
        if len(set(caps))!=len(caps) or len(set(roots))!=len(roots): raise PlatformContractError("duplicate plugin boundary")
        for c in caps: req_id(c,"capability")
        for r in roots:
            if not isinstance(r,str) or not r.startswith("/") or ".." in r.split("/"): raise PlatformContractError("invalid plugin root")
        if self.network_mode not in {"deny","allowlisted-read","allowlisted"}: raise PlatformContractError("invalid plugin network mode")
        object.__setattr__(self,"allowed_capabilities",caps); object.__setattr__(self,"writable_roots",roots)
    def authorizes(self,capability:str)->bool: return req_id(capability,"capability") in self.allowed_capabilities
@dataclass(frozen=True)
class LocalizationEntry:
    key:str; locale:str; text_digest:str; source_locale:str
    def __post_init__(self): req_id(self.key,"key"); req_id(self.locale,"locale"); req_id(self.source_locale,"source_locale"); req_digest(self.text_digest,"text_digest")
def localization_index(entries:Sequence[LocalizationEntry])->Mapping[tuple[str,str],LocalizationEntry]:
    out={}
    for e in entries:
        key=(e.key,e.locale)
        if key in out: raise PlatformContractError("duplicate localization entry")
        out[key]=e
    return out
@dataclass(frozen=True)
class PlatformIdentity:
    platform:str; account_id:str; subject_digest:str; entitlement_digest:str
    def __post_init__(self): req_id(self.platform,"platform"); req_id(self.account_id,"account_id"); req_digest(self.subject_digest,"subject_digest"); req_digest(self.entitlement_digest,"entitlement_digest")
    @property
    def digest(self): return dig(self.__dict__)
@dataclass(frozen=True)
class AchievementRule:
    achievement_id:str; condition_digest:str; irreversible:bool=True
    def __post_init__(self): req_id(self.achievement_id,"achievement_id"); req_digest(self.condition_digest,"condition_digest");
@dataclass(frozen=True)
class AchievementReceipt:
    achievement_id:str; subject_digest:str; unlocked_tick:int; evidence_digest:str
    def __post_init__(self):
        req_id(self.achievement_id,"achievement_id"); req_digest(self.subject_digest,"subject_digest"); req_digest(self.evidence_digest,"evidence_digest")
        if not _int(self.unlocked_tick) or self.unlocked_tick<0: raise PlatformContractError("invalid achievement tick")
@dataclass(frozen=True)
class VersionMigration:
    migration_id:str; from_version:int; to_version:int; transform_digest:str; rollback_digest:str|None
    def __post_init__(self):
        req_id(self.migration_id,"migration_id"); req_digest(self.transform_digest,"transform_digest")
        if not _int(self.from_version) or not _int(self.to_version) or self.from_version<1 or self.to_version!=self.from_version+1: raise PlatformContractError("migration must advance one version")
        if self.rollback_digest is not None: req_digest(self.rollback_digest,"rollback_digest")
def migration_path(steps:Sequence[VersionMigration],start:int,end:int)->tuple[VersionMigration,...]:
    by={s.from_version:s for s in steps}
    if len(by)!=len(steps): raise PlatformContractError("duplicate migration source")
    out=[]; cur=start
    while cur<end:
        if cur not in by: raise PlatformContractError("migration gap")
        step=by[cur]; out.append(step); cur=step.to_version
    if cur!=end: raise PlatformContractError("migration overshoot")
    return tuple(out)
