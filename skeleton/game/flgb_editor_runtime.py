"""FLGB-09 durable game project, editor transaction, world, and recovery contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_WORLDS=4096
MAX_NODES=1_000_000
MAX_COMPONENTS=4096
MAX_ASSETS=1_000_000
MAX_OPERATIONS=100_000
MAX_PARTITIONS=1_000_000
MAX_MIGRATIONS=100_000

class GameProjectError(ValueError):
    """Fail-closed FLGB-09 contract error."""

def _is_int(v:Any)->bool: return isinstance(v,int) and not isinstance(v,bool)

def require_id(v:str,name:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID_CHARS or any(ord(c)<32 for c in v):
        raise GameProjectError(f"invalid {name}")
    return v

def require_digest(v:str,name:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):
        raise GameProjectError(f"invalid {name}")
    return v

def digest_json(v:Any)->str:
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode("utf-8")
    except (TypeError,ValueError) as exc: raise GameProjectError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class ProjectManifest:
    project_id:str
    revision:int
    schema_version:int
    world_ids:tuple[str,...]
    config_digest:str
    dependency_lock_digest:str
    rights_manifest_digest:str
    parent_manifest_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.project_id,"project_id")
        if not _is_int(self.revision) or self.revision<0: raise GameProjectError("invalid project revision")
        if not _is_int(self.schema_version) or self.schema_version<1: raise GameProjectError("invalid schema_version")
        worlds=tuple(sorted(self.world_ids))
        if len(worlds)>MAX_WORLDS or len(set(worlds))!=len(worlds): raise GameProjectError("invalid world_ids")
        for world in worlds: require_id(world,"world_id")
        object.__setattr__(self,"world_ids",worlds)
        for name in ("config_digest","dependency_lock_digest","rights_manifest_digest"): require_digest(getattr(self,name),name)
        if self.parent_manifest_digest is not None: require_digest(self.parent_manifest_digest,"parent_manifest_digest")
        if self.revision==0 and self.parent_manifest_digest is not None: raise GameProjectError("genesis project cannot have parent")
        if self.revision>0 and self.parent_manifest_digest is None: raise GameProjectError("project revision requires parent")

    @property
    def digest(self)->str: return digest_json({"project_id":self.project_id,"revision":self.revision,"schema_version":self.schema_version,"world_ids":list(self.world_ids),"config_digest":self.config_digest,"dependency_lock_digest":self.dependency_lock_digest,"rights_manifest_digest":self.rights_manifest_digest,"parent_manifest_digest":self.parent_manifest_digest})

    def revise(self,*,world_ids:Sequence[str]|None=None,config_digest:str|None=None)->"ProjectManifest":
        return ProjectManifest(self.project_id,self.revision+1,self.schema_version,tuple(self.world_ids if world_ids is None else world_ids),self.config_digest if config_digest is None else require_digest(config_digest,"config_digest"),self.dependency_lock_digest,self.rights_manifest_digest,self.digest)

@dataclass(frozen=True)
class EditorOperation:
    operation_id:str
    kind:str
    target_id:str
    payload_digest:str
    inverse_digest:str

    def __post_init__(self)->None:
        require_id(self.operation_id,"operation_id"); require_id(self.target_id,"target_id")
        if self.kind not in {"create","update","delete","move","attach","detach"}: raise GameProjectError("invalid editor operation kind")
        require_digest(self.payload_digest,"payload_digest"); require_digest(self.inverse_digest,"inverse_digest")

@dataclass(frozen=True)
class EditorTransaction:
    transaction_id:str
    project_id:str
    base_revision:int
    idempotency_key:str
    operations:tuple[EditorOperation,...]
    authority_scope:str="editor-transaction-only"

    def __post_init__(self)->None:
        require_id(self.transaction_id,"transaction_id"); require_id(self.project_id,"project_id"); require_id(self.idempotency_key,"idempotency_key")
        if not _is_int(self.base_revision) or self.base_revision<0: raise GameProjectError("invalid base_revision")
        if not self.operations or len(self.operations)>MAX_OPERATIONS: raise GameProjectError("editor transaction operation count out of bounds")
        ids=[op.operation_id for op in self.operations]
        if len(set(ids))!=len(ids): raise GameProjectError("duplicate editor operation")
        if self.authority_scope!="editor-transaction-only": raise GameProjectError("editor transaction cannot widen authority")

    @property
    def digest(self)->str: return digest_json({"transaction_id":self.transaction_id,"project_id":self.project_id,"base_revision":self.base_revision,"idempotency_key":self.idempotency_key,"operations":[op.__dict__ for op in self.operations],"authority_scope":self.authority_scope})

@dataclass(frozen=True)
class TransactionReceipt:
    transaction_digest:str
    prior_manifest_digest:str
    next_manifest_digest:str
    committed_revision:int

    def __post_init__(self)->None:
        require_digest(self.transaction_digest,"transaction_digest"); require_digest(self.prior_manifest_digest,"prior_manifest_digest"); require_digest(self.next_manifest_digest,"next_manifest_digest")
        if not _is_int(self.committed_revision) or self.committed_revision<1: raise GameProjectError("invalid committed_revision")

def commit_transaction(transaction:EditorTransaction,manifest:ProjectManifest,next_manifest:ProjectManifest)->TransactionReceipt:
    if transaction.project_id!=manifest.project_id or manifest.project_id!=next_manifest.project_id: raise GameProjectError("cross-project transaction")
    if transaction.base_revision!=manifest.revision: raise GameProjectError("stale editor transaction")
    if next_manifest.revision!=manifest.revision+1 or next_manifest.parent_manifest_digest!=manifest.digest: raise GameProjectError("next manifest is not direct child")
    return TransactionReceipt(transaction.digest,manifest.digest,next_manifest.digest,next_manifest.revision)

@dataclass(frozen=True)
class WorldIdentity:
    project_id:str
    world_id:str
    namespace:str
    generation:int=0

    def __post_init__(self)->None:
        require_id(self.project_id,"project_id"); require_id(self.world_id,"world_id"); require_id(self.namespace,"namespace")
        if not _is_int(self.generation) or self.generation<0: raise GameProjectError("invalid world generation")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class SceneNode:
    node_id:str
    parent_id:str|None
    entity_id:str|None
    order:int

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id")
        if self.parent_id is not None: require_id(self.parent_id,"parent_id")
        if self.entity_id is not None: require_id(self.entity_id,"entity_id")
        if self.parent_id==self.node_id: raise GameProjectError("scene node cannot parent itself")
        if not _is_int(self.order) or self.order<0: raise GameProjectError("invalid scene order")

class SceneGraph:
    def __init__(self,nodes:Sequence[SceneNode])->None:
        if not nodes or len(nodes)>MAX_NODES: raise GameProjectError("scene node count out of bounds")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise GameProjectError("duplicate scene node")
        roots=[n for n in nodes if n.parent_id is None]
        if len(roots)!=1: raise GameProjectError("scene graph requires exactly one root")
        for node in nodes:
            if node.parent_id is not None and node.parent_id not in by_id: raise GameProjectError("orphan scene node")
        state={}
        def visit(node_id:str)->None:
            mark=state.get(node_id,0)
            if mark==1: raise GameProjectError("scene graph cycle")
            if mark==2: return
            state[node_id]=1
            parent=by_id[node_id].parent_id
            if parent is not None: visit(parent)
            state[node_id]=2
        for node_id in by_id: visit(node_id)
        entity_ids=[n.entity_id for n in nodes if n.entity_id is not None]
        if len(set(entity_ids))!=len(entity_ids): raise GameProjectError("entity attached to multiple scene nodes")
        self.nodes=tuple(sorted(nodes,key=lambda n:(n.order,n.node_id)))
        self.root_id=roots[0].node_id

    @property
    def digest(self)->str: return digest_json([n.__dict__ for n in self.nodes])

@dataclass(frozen=True)
class EntityIdentity:
    project_id:str
    world_id:str
    scene_id:str
    entity_id:str
    generation:int=0

    def __post_init__(self)->None:
        for name in ("project_id","world_id","scene_id","entity_id"): require_id(getattr(self,name),name)
        if not _is_int(self.generation) or self.generation<0: raise GameProjectError("invalid entity generation")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class ComponentField:
    name:str
    value_type:str
    required:bool

    def __post_init__(self)->None:
        require_id(self.name,"field name")
        if self.value_type not in {"bool","int","float","string","vec2","vec3","quat","entity-ref","asset-ref","json"}: raise GameProjectError("invalid component field type")
        if not isinstance(self.required,bool): raise GameProjectError("required must be boolean")

@dataclass(frozen=True)
class ComponentSchema:
    component_id:str
    version:int
    fields:tuple[ComponentField,...]

    def __post_init__(self)->None:
        require_id(self.component_id,"component_id")
        if not _is_int(self.version) or self.version<1: raise GameProjectError("invalid component version")
        if not self.fields or len(self.fields)>MAX_COMPONENTS: raise GameProjectError("component field count out of bounds")
        names=[f.name for f in self.fields]
        if len(set(names))!=len(names): raise GameProjectError("duplicate component field")

    @property
    def digest(self)->str: return digest_json({"component_id":self.component_id,"version":self.version,"fields":[f.__dict__ for f in self.fields]})

@dataclass(frozen=True)
class PrefabSpec:
    prefab_id:str
    parent_prefab_id:str|None
    component_digests:tuple[str,...]

    def __post_init__(self)->None:
        require_id(self.prefab_id,"prefab_id")
        if self.parent_prefab_id is not None: require_id(self.parent_prefab_id,"parent_prefab_id")
        if self.parent_prefab_id==self.prefab_id: raise GameProjectError("prefab cannot inherit itself")
        values=tuple(sorted(self.component_digests))
        if len(set(values))!=len(values): raise GameProjectError("duplicate prefab component")
        for d in values: require_digest(d,"component_digest")
        object.__setattr__(self,"component_digests",values)

def validate_prefabs(prefabs:Sequence[PrefabSpec])->tuple[PrefabSpec,...]:
    by_id={p.prefab_id:p for p in prefabs}
    if len(by_id)!=len(prefabs): raise GameProjectError("duplicate prefab identity")
    state={}
    def visit(pid:str)->None:
        mark=state.get(pid,0)
        if mark==1: raise GameProjectError("prefab inheritance cycle")
        if mark==2:return
        state[pid]=1
        parent=by_id[pid].parent_prefab_id
        if parent is not None:
            if parent not in by_id: raise GameProjectError("unknown prefab parent")
            visit(parent)
        state[pid]=2
    for pid in by_id: visit(pid)
    return tuple(sorted(prefabs,key=lambda p:p.prefab_id))

@dataclass(frozen=True)
class AssetReference:
    asset_id:str
    kind:str
    content_digest:str
    provenance_digest:str
    rights_digest:str

    def __post_init__(self)->None:
        require_id(self.asset_id,"asset_id"); require_id(self.kind,"asset kind")
        for name in ("content_digest","provenance_digest","rights_digest"): require_digest(getattr(self,name),name)

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class HistoryEntry:
    sequence:int
    transaction_digest:str
    inverse_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.sequence) or self.sequence<0: raise GameProjectError("invalid history sequence")
        require_digest(self.transaction_digest,"transaction_digest"); require_digest(self.inverse_digest,"inverse_digest")

class UndoRedoLog:
    def __init__(self,entries:Sequence[HistoryEntry]=(),cursor:int|None=None)->None:
        for index,e in enumerate(entries):
            if e.sequence!=index: raise GameProjectError("history sequence drift")
        self.entries=tuple(entries)
        self.cursor=len(entries) if cursor is None else cursor
        if not _is_int(self.cursor) or not 0<=self.cursor<=len(self.entries): raise GameProjectError("invalid history cursor")

    def append(self,transaction_digest:str,inverse_digest:str)->"UndoRedoLog":
        active=self.entries[:self.cursor]
        entry=HistoryEntry(len(active),transaction_digest,inverse_digest)
        return UndoRedoLog(active+(entry,),len(active)+1)

    def undo(self)->tuple["UndoRedoLog",str]:
        if self.cursor==0: raise GameProjectError("nothing to undo")
        entry=self.entries[self.cursor-1]
        return UndoRedoLog(self.entries,self.cursor-1),entry.inverse_digest

    def redo(self)->tuple["UndoRedoLog",str]:
        if self.cursor>=len(self.entries): raise GameProjectError("nothing to redo")
        entry=self.entries[self.cursor]
        return UndoRedoLog(self.entries,self.cursor+1),entry.transaction_digest

@dataclass(frozen=True)
class WorldCell:
    cell_id:str
    x:int
    y:int
    z:int
    entity_ids:tuple[str,...]

    def __post_init__(self)->None:
        require_id(self.cell_id,"cell_id")
        for name in ("x","y","z"):
            if not _is_int(getattr(self,name)): raise GameProjectError(f"invalid {name}")
        ids=tuple(sorted(self.entity_ids))
        if len(set(ids))!=len(ids): raise GameProjectError("duplicate partition entity")
        for eid in ids: require_id(eid,"entity_id")
        object.__setattr__(self,"entity_ids",ids)

def validate_partitions(cells:Sequence[WorldCell])->tuple[WorldCell,...]:
    if len(cells)>MAX_PARTITIONS: raise GameProjectError("world partition budget exceeded")
    cell_ids=[c.cell_id for c in cells]; coords=[(c.x,c.y,c.z) for c in cells]
    if len(set(cell_ids))!=len(cell_ids) or len(set(coords))!=len(coords): raise GameProjectError("duplicate world partition identity")
    entities=[eid for c in cells for eid in c.entity_ids]
    if len(set(entities))!=len(entities): raise GameProjectError("entity assigned to multiple partitions")
    return tuple(sorted(cells,key=lambda c:(c.x,c.y,c.z,c.cell_id)))

@dataclass(frozen=True)
class MigrationStep:
    migration_id:str
    from_version:int
    to_version:int
    transform_digest:str
    rollback_digest:str

    def __post_init__(self)->None:
        require_id(self.migration_id,"migration_id")
        if not _is_int(self.from_version) or not _is_int(self.to_version) or self.to_version!=self.from_version+1: raise GameProjectError("migration must advance one version")
        require_digest(self.transform_digest,"transform_digest"); require_digest(self.rollback_digest,"rollback_digest")

def migration_path(current:int,target:int,steps:Sequence[MigrationStep])->tuple[MigrationStep,...]:
    if not _is_int(current) or not _is_int(target) or current<1 or target<current: raise GameProjectError("invalid migration range")
    if len(steps)>MAX_MIGRATIONS: raise GameProjectError("migration step budget exceeded")
    by_from={s.from_version:s for s in steps}
    if len(by_from)!=len(steps): raise GameProjectError("ambiguous migration step")
    path=[]; version=current
    while version<target:
        step=by_from.get(version)
        if step is None: raise GameProjectError("migration path gap")
        path.append(step); version=step.to_version
    return tuple(path)

@dataclass(frozen=True)
class EditorRecoveryReceipt:
    project_id:str
    manifest_digest:str
    snapshot_digest:str
    journal_digest:str
    replay_cursor:int
    recovered_manifest_digest:str

    def __post_init__(self)->None:
        require_id(self.project_id,"project_id")
        for name in ("manifest_digest","snapshot_digest","journal_digest","recovered_manifest_digest"): require_digest(getattr(self,name),name)
        if not _is_int(self.replay_cursor) or self.replay_cursor<0: raise GameProjectError("invalid replay_cursor")
        if self.recovered_manifest_digest!=self.manifest_digest: raise GameProjectError("editor recovery manifest mismatch")

    @property
    def digest(self)->str: return digest_json(self.__dict__)
