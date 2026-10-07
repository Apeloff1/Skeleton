"""FLGB-09 deterministic project/editor/world transaction contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_ENTITIES=1_000_000
MAX_COMPONENTS=1_000_000
MAX_NODES=1_000_000
MAX_EDGES=4_000_000
MAX_ASSETS=1_000_000
MAX_PARTITIONS=1_000_000
MAX_HISTORY=1_000_000
MAX_MIGRATIONS=10_000

class CreatorContractError(ValueError):
    """Fail-closed FLGB-09 creator/editor contract error."""

def _is_int(v:Any)->bool: return isinstance(v,int) and not isinstance(v,bool)

def require_id(v:str,name:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID_CHARS or any(ord(c)<32 for c in v):
        raise CreatorContractError(f"invalid {name}")
    return v

def require_digest(v:str,name:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):
        raise CreatorContractError(f"invalid {name}")
    return v

def digest_json(v:Any)->str:
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode("utf-8")
    except (TypeError,ValueError) as exc: raise CreatorContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class ProjectManifest:
    project_id:str
    schema_version:int
    world_ids:tuple[str,...]
    asset_manifest_digest:str
    settings_digest:str
    parent_manifest_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.project_id,"project_id")
        if not _is_int(self.schema_version) or self.schema_version<1: raise CreatorContractError("invalid schema_version")
        worlds=tuple(sorted(self.world_ids))
        if len(worlds)>MAX_NODES or len(set(worlds))!=len(worlds): raise CreatorContractError("invalid world_ids")
        for world in worlds: require_id(world,"world_id")
        object.__setattr__(self,"world_ids",worlds)
        require_digest(self.asset_manifest_digest,"asset_manifest_digest"); require_digest(self.settings_digest,"settings_digest")
        if self.parent_manifest_digest is not None: require_digest(self.parent_manifest_digest,"parent_manifest_digest")

    @property
    def digest(self)->str: return digest_json({"project_id":self.project_id,"schema_version":self.schema_version,"world_ids":list(self.world_ids),"asset_manifest_digest":self.asset_manifest_digest,"settings_digest":self.settings_digest,"parent_manifest_digest":self.parent_manifest_digest})

@dataclass(frozen=True)
class EditorOperation:
    operation_id:str
    target_id:str
    before_digest:str
    after_digest:str
    reversible:bool=True

    def __post_init__(self)->None:
        require_id(self.operation_id,"operation_id"); require_id(self.target_id,"target_id")
        require_digest(self.before_digest,"before_digest"); require_digest(self.after_digest,"after_digest")
        if not isinstance(self.reversible,bool): raise CreatorContractError("reversible must be boolean")

@dataclass(frozen=True)
class EditorTransaction:
    transaction_id:str
    base_state_digest:str
    operations:tuple[EditorOperation,...]
    author_id:str

    def __post_init__(self)->None:
        require_id(self.transaction_id,"transaction_id"); require_digest(self.base_state_digest,"base_state_digest"); require_id(self.author_id,"author_id")
        if not self.operations or len(self.operations)>MAX_HISTORY: raise CreatorContractError("editor operation count out of bounds")
        ids=[o.operation_id for o in self.operations]
        if len(set(ids))!=len(ids): raise CreatorContractError("duplicate editor operation id")

    @property
    def result_state_digest(self)->str:
        return digest_json({"base":self.base_state_digest,"ops":[o.__dict__ for o in self.operations]})

    @property
    def digest(self)->str: return digest_json({"transaction_id":self.transaction_id,"base_state_digest":self.base_state_digest,"operations":[o.__dict__ for o in self.operations],"author_id":self.author_id})

@dataclass(frozen=True)
class WorldIdentity:
    world_id:str
    project_id:str
    generation:int
    seed_digest:str

    def __post_init__(self)->None:
        require_id(self.world_id,"world_id"); require_id(self.project_id,"project_id"); require_digest(self.seed_digest,"seed_digest")
        if not _is_int(self.generation) or self.generation<0: raise CreatorContractError("invalid world generation")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class SceneNode:
    node_id:str
    parent_id:str|None
    entity_id:str|None
    local_transform_digest:str

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id")
        if self.parent_id is not None: require_id(self.parent_id,"parent_id")
        if self.entity_id is not None: require_id(self.entity_id,"entity_id")
        if self.parent_id==self.node_id: raise CreatorContractError("scene node cannot parent itself")
        require_digest(self.local_transform_digest,"local_transform_digest")

class SceneGraph:
    def __init__(self,nodes:Sequence[SceneNode])->None:
        if not nodes or len(nodes)>MAX_NODES: raise CreatorContractError("scene node count out of bounds")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise CreatorContractError("duplicate scene node")
        for node in nodes:
            if node.parent_id is not None and node.parent_id not in by_id: raise CreatorContractError("orphan scene parent")
        self._nodes=MappingProxyType(by_id)
        self._order=self._topological_order()

    def _topological_order(self)->tuple[str,...]:
        remaining=set(self._nodes); ordered=[]
        while remaining:
            ready=sorted(n for n in remaining if self._nodes[n].parent_id is None or self._nodes[n].parent_id in ordered)
            if not ready: raise CreatorContractError("scene graph cycle")
            ordered.extend(ready); remaining.difference_update(ready)
        return tuple(ordered)

    @property
    def order(self)->tuple[str,...]: return self._order

    @property
    def digest(self)->str: return digest_json([self._nodes[n].__dict__ for n in self._order])

@dataclass(frozen=True)
class EntityIdentity:
    entity_id:str
    world_id:str
    generation:int=0

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id"); require_id(self.world_id,"world_id")
        if not _is_int(self.generation) or self.generation<0: raise CreatorContractError("invalid entity generation")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

    def next_generation(self)->"EntityIdentity":
        return EntityIdentity(self.entity_id,self.world_id,self.generation+1)

@dataclass(frozen=True)
class ComponentField:
    name:str
    field_type:str
    required:bool

    def __post_init__(self)->None:
        require_id(self.name,"field name")
        if self.field_type not in {"bool","int","float","string","vec2","vec3","quat","entity_ref","asset_ref","json"}: raise CreatorContractError("invalid component field type")
        if not isinstance(self.required,bool): raise CreatorContractError("required must be boolean")

@dataclass(frozen=True)
class ComponentSchema:
    component_id:str
    version:int
    fields:tuple[ComponentField,...]

    def __post_init__(self)->None:
        require_id(self.component_id,"component_id")
        if not _is_int(self.version) or self.version<1: raise CreatorContractError("invalid component version")
        if not self.fields or len(self.fields)>MAX_COMPONENTS: raise CreatorContractError("component field count out of bounds")
        names=[f.name for f in self.fields]
        if len(set(names))!=len(names): raise CreatorContractError("duplicate component field")

    @property
    def digest(self)->str: return digest_json({"component_id":self.component_id,"version":self.version,"fields":[f.__dict__ for f in self.fields]})

@dataclass(frozen=True)
class PrefabDefinition:
    prefab_id:str
    parent_prefab_id:str|None
    component_digests:tuple[str,...]

    def __post_init__(self)->None:
        require_id(self.prefab_id,"prefab_id")
        if self.parent_prefab_id is not None: require_id(self.parent_prefab_id,"parent_prefab_id")
        if self.parent_prefab_id==self.prefab_id: raise CreatorContractError("prefab cannot parent itself")
        comps=tuple(sorted(self.component_digests))
        if len(comps)>MAX_COMPONENTS or len(set(comps))!=len(comps): raise CreatorContractError("invalid component_digests")
        for d in comps: require_digest(d,"component_digest")
        object.__setattr__(self,"component_digests",comps)

def resolve_prefab_chain(prefabs:Sequence[PrefabDefinition],prefab_id:str)->tuple[PrefabDefinition,...]:
    by_id={p.prefab_id:p for p in prefabs}
    if len(by_id)!=len(prefabs): raise CreatorContractError("duplicate prefab id")
    current=require_id(prefab_id,"prefab_id"); chain=[]; seen=set()
    while current is not None:
        if current in seen: raise CreatorContractError("prefab inheritance cycle")
        seen.add(current)
        try: item=by_id[current]
        except KeyError as exc: raise CreatorContractError("unknown prefab parent") from exc
        chain.append(item); current=item.parent_prefab_id
    return tuple(reversed(chain))

@dataclass(frozen=True)
class AssetReference:
    asset_id:str
    artifact_digest:str
    asset_type:str
    provenance_digest:str
    rights_digest:str

    def __post_init__(self)->None:
        require_id(self.asset_id,"asset_id"); require_digest(self.artifact_digest,"artifact_digest"); require_digest(self.provenance_digest,"provenance_digest"); require_digest(self.rights_digest,"rights_digest")
        if self.asset_type not in {"texture","mesh","audio","video","script","material","animation","font","document","other"}: raise CreatorContractError("invalid asset_type")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class HistoryEntry:
    sequence:int
    transaction_digest:str
    forward_state_digest:str
    reverse_state_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.sequence) or self.sequence<0: raise CreatorContractError("invalid history sequence")
        for name in ("transaction_digest","forward_state_digest","reverse_state_digest"): require_digest(getattr(self,name),name)

class UndoRedoLog:
    def __init__(self,entries:Sequence[HistoryEntry]=(),cursor:int|None=None)->None:
        if len(entries)>MAX_HISTORY: raise CreatorContractError("history budget exceeded")
        for i,e in enumerate(entries):
            if e.sequence!=i: raise CreatorContractError("history sequence drift")
        if cursor is None: cursor=len(entries)
        if not _is_int(cursor) or not 0<=cursor<=len(entries): raise CreatorContractError("invalid history cursor")
        self.entries=tuple(entries); self.cursor=cursor

    def append(self,transaction_digest:str,forward_state_digest:str,reverse_state_digest:str)->"UndoRedoLog":
        kept=self.entries[:self.cursor]
        entry=HistoryEntry(len(kept),require_digest(transaction_digest,"transaction_digest"),require_digest(forward_state_digest,"forward_state_digest"),require_digest(reverse_state_digest,"reverse_state_digest"))
        return UndoRedoLog(kept+(entry,),len(kept)+1)

    def undo(self)->tuple["UndoRedoLog",str]:
        if self.cursor==0: raise CreatorContractError("nothing to undo")
        entry=self.entries[self.cursor-1]
        return UndoRedoLog(self.entries,self.cursor-1),entry.reverse_state_digest

    def redo(self)->tuple["UndoRedoLog",str]:
        if self.cursor>=len(self.entries): raise CreatorContractError("nothing to redo")
        entry=self.entries[self.cursor]
        return UndoRedoLog(self.entries,self.cursor+1),entry.forward_state_digest

@dataclass(frozen=True)
class WorldPartition:
    partition_id:str
    world_id:str
    min_x:int
    min_y:int
    max_x:int
    max_y:int
    content_digest:str

    def __post_init__(self)->None:
        require_id(self.partition_id,"partition_id"); require_id(self.world_id,"world_id"); require_digest(self.content_digest,"content_digest")
        for name in ("min_x","min_y","max_x","max_y"):
            if not _is_int(getattr(self,name)): raise CreatorContractError(f"invalid {name}")
        if self.min_x>=self.max_x or self.min_y>=self.max_y: raise CreatorContractError("invalid partition bounds")

def partitions_for_point(partitions:Sequence[WorldPartition],world_id:str,x:int,y:int)->tuple[WorldPartition,...]:
    require_id(world_id,"world_id")
    if not _is_int(x) or not _is_int(y): raise CreatorContractError("invalid point")
    if len(partitions)>MAX_PARTITIONS: raise CreatorContractError("partition budget exceeded")
    ids=[p.partition_id for p in partitions]
    if len(set(ids))!=len(ids): raise CreatorContractError("duplicate partition id")
    return tuple(sorted((p for p in partitions if p.world_id==world_id and p.min_x<=x<p.max_x and p.min_y<=y<p.max_y),key=lambda p:p.partition_id))

@dataclass(frozen=True)
class MigrationStep:
    migration_id:str
    from_version:int
    to_version:int
    transform_digest:str
    reversible:bool

    def __post_init__(self)->None:
        require_id(self.migration_id,"migration_id"); require_digest(self.transform_digest,"transform_digest")
        if not _is_int(self.from_version) or not _is_int(self.to_version) or self.from_version<1 or self.to_version!=self.from_version+1: raise CreatorContractError("migration must advance exactly one version")
        if not isinstance(self.reversible,bool): raise CreatorContractError("reversible must be boolean")

def plan_migration(steps:Sequence[MigrationStep],from_version:int,to_version:int)->tuple[MigrationStep,...]:
    if len(steps)>MAX_MIGRATIONS: raise CreatorContractError("migration budget exceeded")
    if not _is_int(from_version) or not _is_int(to_version) or from_version<1 or to_version<from_version: raise CreatorContractError("invalid migration range")
    by_from={s.from_version:s for s in steps}
    if len(by_from)!=len(steps): raise CreatorContractError("duplicate migration source version")
    out=[]; current=from_version
    while current<to_version:
        try: step=by_from[current]
        except KeyError as exc: raise CreatorContractError("migration path gap") from exc
        out.append(step); current=step.to_version
    return tuple(out)

@dataclass(frozen=True)
class EditorCheckpoint:
    checkpoint_id:str
    sequence:int
    durable_state_digest:str
    pending_transaction_digest:str|None
    prior_checkpoint_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.checkpoint_id,"checkpoint_id")
        if not _is_int(self.sequence) or self.sequence<0: raise CreatorContractError("invalid checkpoint sequence")
        require_digest(self.durable_state_digest,"durable_state_digest")
        if self.pending_transaction_digest is not None: require_digest(self.pending_transaction_digest,"pending_transaction_digest")
        if self.prior_checkpoint_digest is not None: require_digest(self.prior_checkpoint_digest,"prior_checkpoint_digest")
        if self.sequence==0 and self.prior_checkpoint_digest is not None: raise CreatorContractError("genesis checkpoint cannot have parent")
        if self.sequence>0 and self.prior_checkpoint_digest is None: raise CreatorContractError("checkpoint requires parent")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

def recover_editor(checkpoints:Sequence[EditorCheckpoint])->EditorCheckpoint:
    if not checkpoints: raise CreatorContractError("no editor checkpoint available")
    for i,cp in enumerate(checkpoints):
        if cp.sequence!=i: raise CreatorContractError("editor checkpoint sequence drift")
        expected=checkpoints[i-1].digest if i else None
        if cp.prior_checkpoint_digest!=expected: raise CreatorContractError("editor checkpoint chain drift")
    latest=checkpoints[-1]
    if latest.pending_transaction_digest is not None:
        return EditorCheckpoint(f"{latest.checkpoint_id}:recovered",latest.sequence+1,latest.durable_state_digest,None,latest.digest)
    return latest
