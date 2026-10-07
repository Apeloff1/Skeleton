"""FLGB-09 deterministic game-project, editor, scene, prefab, and recovery contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_ENTITIES=1_000_000
MAX_COMPONENTS=4096
MAX_FIELDS=4096
MAX_ASSETS=1_000_000
MAX_PARTITIONS=1_000_000
MAX_HISTORY=100_000
MAX_MIGRATION_STEPS=10_000
MAX_TX_OPS=100_000

class GameContractError(ValueError):
    """Fail-closed FLGB-09 contract error."""

def _is_int(value: Any) -> bool:
    return isinstance(value,int) and not isinstance(value,bool)

def require_id(value:str,name:str)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>MAX_ID_CHARS or any(ord(ch)<32 for ch in value):
        raise GameContractError(f"invalid {name}")
    return value

def require_digest(value:str,name:str)->str:
    if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
        raise GameContractError(f"invalid {name}")
    return value

def canonical_bytes(value:Any)->bytes:
    try:
        return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError) as exc:
        raise GameContractError("value is not canonical-json encodable") from exc

def digest_json(value:Any)->str:
    return sha256(canonical_bytes(value)).hexdigest()

@dataclass(frozen=True)
class ProjectManifest:
    project_id:str
    format_version:int
    engine_contract_digest:str
    world_ids:tuple[str,...]
    asset_catalog_digest:str
    settings_digest:str
    provenance_digest:str

    def __post_init__(self)->None:
        require_id(self.project_id,"project_id")
        if not _is_int(self.format_version) or self.format_version<1: raise GameContractError("invalid format_version")
        for name in ("engine_contract_digest","asset_catalog_digest","settings_digest","provenance_digest"): require_digest(getattr(self,name),name)
        worlds=tuple(sorted(self.world_ids))
        if not worlds or len(worlds)>MAX_PARTITIONS or len(set(worlds))!=len(worlds): raise GameContractError("invalid world_ids")
        for world_id in worlds: require_id(world_id,"world_id")
        object.__setattr__(self,"world_ids",worlds)

    @property
    def digest(self)->str:
        return digest_json({"project_id":self.project_id,"format_version":self.format_version,"engine_contract_digest":self.engine_contract_digest,"world_ids":list(self.world_ids),"asset_catalog_digest":self.asset_catalog_digest,"settings_digest":self.settings_digest,"provenance_digest":self.provenance_digest})

@dataclass(frozen=True)
class EditorOperation:
    sequence:int
    kind:str
    target_id:str
    before_digest:str|None
    after_digest:str|None
    payload_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.sequence) or self.sequence<0: raise GameContractError("invalid operation sequence")
        if self.kind not in {"create","update","delete","move","link","unlink"}: raise GameContractError("invalid editor operation kind")
        require_id(self.target_id,"target_id"); require_digest(self.payload_digest,"payload_digest")
        if self.before_digest is not None: require_digest(self.before_digest,"before_digest")
        if self.after_digest is not None: require_digest(self.after_digest,"after_digest")
        if self.kind=="create" and self.before_digest is not None: raise GameContractError("create cannot have before_digest")
        if self.kind=="delete" and self.after_digest is not None: raise GameContractError("delete cannot have after_digest")
        if self.kind in {"update","move","link","unlink"} and (self.before_digest is None or self.after_digest is None): raise GameContractError("mutating operation requires before and after digests")

@dataclass(frozen=True)
class EditorTransaction:
    transaction_id:str
    project_digest_before:str
    project_digest_after:str
    operations:tuple[EditorOperation,...]
    authority_digest:str
    idempotency_key:str

    def __post_init__(self)->None:
        require_id(self.transaction_id,"transaction_id"); require_id(self.idempotency_key,"idempotency_key")
        require_digest(self.project_digest_before,"project_digest_before"); require_digest(self.project_digest_after,"project_digest_after"); require_digest(self.authority_digest,"authority_digest")
        if not self.operations or len(self.operations)>MAX_TX_OPS: raise GameContractError("transaction operation count out of bounds")
        for index,op in enumerate(self.operations):
            if not isinstance(op,EditorOperation) or op.sequence!=index: raise GameContractError("editor transaction sequence drift")
        if self.project_digest_before==self.project_digest_after and any(op.kind!="link" for op in self.operations): raise GameContractError("state-changing transaction must change project digest")

    @property
    def digest(self)->str:
        return digest_json({"transaction_id":self.transaction_id,"project_digest_before":self.project_digest_before,"project_digest_after":self.project_digest_after,"operations":[op.__dict__ for op in self.operations],"authority_digest":self.authority_digest,"idempotency_key":self.idempotency_key})

@dataclass(frozen=True)
class WorldIdentity:
    project_id:str
    world_id:str
    world_revision:int
    seed_digest:str
    schema_digest:str
    parent_world_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.project_id,"project_id"); require_id(self.world_id,"world_id")
        if not _is_int(self.world_revision) or self.world_revision<0: raise GameContractError("invalid world_revision")
        require_digest(self.seed_digest,"seed_digest"); require_digest(self.schema_digest,"schema_digest")
        if self.parent_world_digest is not None: require_digest(self.parent_world_digest,"parent_world_digest")
        if self.world_revision==0 and self.parent_world_digest is not None: raise GameContractError("genesis world cannot have parent")
        if self.world_revision>0 and self.parent_world_digest is None: raise GameContractError("world revision requires parent")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

    def revise(self,schema_digest:str)->"WorldIdentity":
        return WorldIdentity(self.project_id,self.world_id,self.world_revision+1,self.seed_digest,require_digest(schema_digest,"schema_digest"),self.digest)

@dataclass(frozen=True)
class SceneNode:
    entity_id:str
    parent_id:str|None
    component_set_digest:str
    local_transform_digest:str
    order_key:int

    def __post_init__(self)->None:
        require_id(self.entity_id,"entity_id")
        if self.parent_id is not None: require_id(self.parent_id,"parent_id")
        if self.parent_id==self.entity_id: raise GameContractError("scene node cannot parent itself")
        require_digest(self.component_set_digest,"component_set_digest"); require_digest(self.local_transform_digest,"local_transform_digest")
        if not _is_int(self.order_key): raise GameContractError("invalid order_key")

class SceneGraph:
    def __init__(self,nodes:Sequence[SceneNode]=())->None:
        if len(nodes)>MAX_ENTITIES: raise GameContractError("scene entity budget exceeded")
        by_id={}
        for node in nodes:
            if not isinstance(node,SceneNode): raise GameContractError("SceneNode required")
            if node.entity_id in by_id: raise GameContractError("duplicate scene entity")
            by_id[node.entity_id]=node
        for node in nodes:
            if node.parent_id is not None and node.parent_id not in by_id: raise GameContractError("orphan scene parent")
        self._nodes=MappingProxyType(by_id)
        self._topological=self._validate_acyclic()

    def _validate_acyclic(self)->tuple[str,...]:
        state={}
        order=[]
        def visit(entity_id:str)->None:
            mark=state.get(entity_id,0)
            if mark==1: raise GameContractError("scene graph cycle")
            if mark==2: return
            state[entity_id]=1
            parent=self._nodes[entity_id].parent_id
            if parent is not None: visit(parent)
            state[entity_id]=2; order.append(entity_id)
        for entity_id in sorted(self._nodes): visit(entity_id)
        return tuple(order)

    @property
    def topological_entities(self)->tuple[str,...]: return self._topological

    @property
    def digest(self)->str:
        return digest_json([{"entity_id":n.entity_id,"parent_id":n.parent_id,"component_set_digest":n.component_set_digest,"local_transform_digest":n.local_transform_digest,"order_key":n.order_key} for n in sorted(self._nodes.values(),key=lambda n:(n.order_key,n.entity_id))])

@dataclass(frozen=True)
class EntityIdentity:
    project_id:str
    world_id:str
    entity_id:str
    generation:int=0

    def __post_init__(self)->None:
        require_id(self.project_id,"project_id"); require_id(self.world_id,"world_id"); require_id(self.entity_id,"entity_id")
        if not _is_int(self.generation) or self.generation<0: raise GameContractError("invalid entity generation")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

    def next_generation(self)->"EntityIdentity": return EntityIdentity(self.project_id,self.world_id,self.entity_id,self.generation+1)

@dataclass(frozen=True)
class ComponentField:
    name:str
    type_id:str
    required:bool
    default_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.name,"field name"); require_id(self.type_id,"type_id")
        if not isinstance(self.required,bool): raise GameContractError("required must be boolean")
        if self.default_digest is not None: require_digest(self.default_digest,"default_digest")
        if self.required and self.default_digest is not None: raise GameContractError("required field cannot also carry default")

@dataclass(frozen=True)
class ComponentSchema:
    component_id:str
    version:int
    fields:tuple[ComponentField,...]

    def __post_init__(self)->None:
        require_id(self.component_id,"component_id")
        if not _is_int(self.version) or self.version<1: raise GameContractError("invalid component version")
        if len(self.fields)>MAX_FIELDS: raise GameContractError("component field budget exceeded")
        names=[f.name for f in self.fields]
        if len(set(names))!=len(names): raise GameContractError("duplicate component field")
        object.__setattr__(self,"fields",tuple(sorted(self.fields,key=lambda f:f.name)))

    @property
    def digest(self)->str:
        return digest_json({"component_id":self.component_id,"version":self.version,"fields":[f.__dict__ for f in self.fields]})

@dataclass(frozen=True)
class PrefabDefinition:
    prefab_id:str
    revision:int
    parent_prefab_digest:str|None
    component_overrides:Mapping[str,str]=field(default_factory=dict)

    def __post_init__(self)->None:
        require_id(self.prefab_id,"prefab_id")
        if not _is_int(self.revision) or self.revision<0: raise GameContractError("invalid prefab revision")
        if self.parent_prefab_digest is not None: require_digest(self.parent_prefab_digest,"parent_prefab_digest")
        overrides=dict(self.component_overrides)
        if len(overrides)>MAX_COMPONENTS: raise GameContractError("prefab component budget exceeded")
        for component_id,value_digest in overrides.items(): require_id(component_id,"component_id"); require_digest(value_digest,"component value digest")
        object.__setattr__(self,"component_overrides",MappingProxyType(dict(sorted(overrides.items()))))

    @property
    def digest(self)->str: return digest_json({"prefab_id":self.prefab_id,"revision":self.revision,"parent_prefab_digest":self.parent_prefab_digest,"component_overrides":dict(self.component_overrides)})

def resolve_prefab_chain(prefabs:Sequence[PrefabDefinition])->Mapping[str,str]:
    if not prefabs: raise GameContractError("prefab chain required")
    resolved={}
    previous=None
    seen=set()
    for prefab in prefabs:
        if prefab.prefab_id in seen: raise GameContractError("prefab inheritance cycle or duplicate")
        seen.add(prefab.prefab_id)
        if previous is None:
            if prefab.parent_prefab_digest is not None: raise GameContractError("prefab chain root cannot reference parent")
        elif prefab.parent_prefab_digest!=previous.digest:
            raise GameContractError("prefab parent digest drift")
        resolved.update(prefab.component_overrides)
        previous=prefab
    return MappingProxyType(dict(sorted(resolved.items())))

@dataclass(frozen=True)
class AssetReference:
    asset_id:str
    artifact_digest:str
    kind:str
    rights_digest:str
    import_settings_digest:str

    def __post_init__(self)->None:
        require_id(self.asset_id,"asset_id"); require_digest(self.artifact_digest,"artifact_digest"); require_digest(self.rights_digest,"rights_digest"); require_digest(self.import_settings_digest,"import_settings_digest")
        if self.kind not in {"texture","mesh","audio","video","script","material","animation","font","data"}: raise GameContractError("invalid asset kind")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

class AssetCatalog:
    def __init__(self,assets:Sequence[AssetReference]=())->None:
        if len(assets)>MAX_ASSETS: raise GameContractError("asset catalog budget exceeded")
        entries={}
        for asset in assets:
            if asset.asset_id in entries: raise GameContractError("duplicate asset id")
            entries[asset.asset_id]=asset
        self._entries=MappingProxyType(entries)

    def resolve(self,asset_id:str)->AssetReference:
        try:return self._entries[require_id(asset_id,"asset_id")]
        except KeyError as exc: raise GameContractError("unknown asset reference") from exc

    @property
    def digest(self)->str: return digest_json([asset.__dict__ for asset in sorted(self._entries.values(),key=lambda a:a.asset_id)])

@dataclass(frozen=True)
class HistoryEntry:
    transaction_digest:str
    before_digest:str
    after_digest:str

    def __post_init__(self)->None:
        require_digest(self.transaction_digest,"transaction_digest"); require_digest(self.before_digest,"before_digest"); require_digest(self.after_digest,"after_digest")
        if self.before_digest==self.after_digest: raise GameContractError("history entry must change state")

@dataclass(frozen=True)
class UndoRedoState:
    current_digest:str
    undo_stack:tuple[HistoryEntry,...]=()
    redo_stack:tuple[HistoryEntry,...]=()

    def __post_init__(self)->None:
        require_digest(self.current_digest,"current_digest")
        if len(self.undo_stack)>MAX_HISTORY or len(self.redo_stack)>MAX_HISTORY: raise GameContractError("history budget exceeded")
        if self.undo_stack and self.undo_stack[-1].after_digest!=self.current_digest: raise GameContractError("undo stack does not terminate at current state")
        if self.redo_stack and self.redo_stack[-1].before_digest!=self.current_digest: raise GameContractError("redo stack does not begin from current state")

    def commit(self,entry:HistoryEntry)->"UndoRedoState":
        if entry.before_digest!=self.current_digest: raise GameContractError("history commit base mismatch")
        return UndoRedoState(entry.after_digest,self.undo_stack+(entry,),())

    def undo(self)->"UndoRedoState":
        if not self.undo_stack: raise GameContractError("nothing to undo")
        entry=self.undo_stack[-1]
        return UndoRedoState(entry.before_digest,self.undo_stack[:-1],self.redo_stack+(entry,))

    def redo(self)->"UndoRedoState":
        if not self.redo_stack: raise GameContractError("nothing to redo")
        entry=self.redo_stack[-1]
        return UndoRedoState(entry.after_digest,self.undo_stack+(entry,),self.redo_stack[:-1])

@dataclass(frozen=True)
class WorldPartition:
    partition_id:str
    world_id:str
    bounds_digest:str
    entity_ids:tuple[str,...]
    owner_shard:str

    def __post_init__(self)->None:
        require_id(self.partition_id,"partition_id"); require_id(self.world_id,"world_id"); require_digest(self.bounds_digest,"bounds_digest"); require_id(self.owner_shard,"owner_shard")
        ids=tuple(sorted(self.entity_ids))
        if len(ids)>MAX_ENTITIES or len(set(ids))!=len(ids): raise GameContractError("invalid partition entity set")
        for entity_id in ids: require_id(entity_id,"entity_id")
        object.__setattr__(self,"entity_ids",ids)

def validate_partitions(partitions:Sequence[WorldPartition])->tuple[WorldPartition,...]:
    if len(partitions)>MAX_PARTITIONS: raise GameContractError("partition budget exceeded")
    ids=[p.partition_id for p in partitions]
    if len(set(ids))!=len(ids): raise GameContractError("duplicate partition id")
    ownership={}
    for partition in partitions:
        for entity_id in partition.entity_ids:
            if entity_id in ownership: raise GameContractError("entity belongs to multiple partitions")
            ownership[entity_id]=partition.partition_id
    return tuple(sorted(partitions,key=lambda p:p.partition_id))

@dataclass(frozen=True)
class MigrationStep:
    step_id:str
    from_version:int
    to_version:int
    transform_digest:str
    reversible:bool

    def __post_init__(self)->None:
        require_id(self.step_id,"step_id"); require_digest(self.transform_digest,"transform_digest")
        if not _is_int(self.from_version) or not _is_int(self.to_version) or self.from_version<1 or self.to_version!=self.from_version+1: raise GameContractError("migration must advance exactly one version")
        if not isinstance(self.reversible,bool): raise GameContractError("reversible must be boolean")

def validate_migration_path(steps:Sequence[MigrationStep],start_version:int,target_version:int)->tuple[MigrationStep,...]:
    if not _is_int(start_version) or not _is_int(target_version) or start_version<1 or target_version<start_version: raise GameContractError("invalid migration bounds")
    if len(steps)>MAX_MIGRATION_STEPS: raise GameContractError("migration step budget exceeded")
    current=start_version
    for step in steps:
        if step.from_version!=current: raise GameContractError("migration path gap")
        current=step.to_version
    if current!=target_version: raise GameContractError("migration path does not reach target")
    return tuple(steps)

@dataclass(frozen=True)
class EditorCheckpoint:
    session_id:str
    sequence:int
    project_digest:str
    history_digest:str
    pending_transaction_digest:str|None
    prior_checkpoint_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.session_id,"session_id")
        if not _is_int(self.sequence) or self.sequence<0: raise GameContractError("invalid checkpoint sequence")
        require_digest(self.project_digest,"project_digest"); require_digest(self.history_digest,"history_digest")
        if self.pending_transaction_digest is not None: require_digest(self.pending_transaction_digest,"pending_transaction_digest")
        if self.prior_checkpoint_digest is not None: require_digest(self.prior_checkpoint_digest,"prior_checkpoint_digest")
        if self.sequence==0 and self.prior_checkpoint_digest is not None: raise GameContractError("genesis editor checkpoint cannot have parent")
        if self.sequence>0 and self.prior_checkpoint_digest is None: raise GameContractError("editor checkpoint requires parent")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class RecoveryDecision:
    checkpoint_digest:str
    action:str
    restored_project_digest:str
    pending_transaction_digest:str|None

    def __post_init__(self)->None:
        require_digest(self.checkpoint_digest,"checkpoint_digest"); require_digest(self.restored_project_digest,"restored_project_digest")
        if self.action not in {"resume","rollback-pending","discard-pending"}: raise GameContractError("invalid recovery action")
        if self.pending_transaction_digest is not None: require_digest(self.pending_transaction_digest,"pending_transaction_digest")
        if self.action=="resume" and self.pending_transaction_digest is not None: raise GameContractError("resume requires no unresolved pending transaction")
        if self.action in {"rollback-pending","discard-pending"} and self.pending_transaction_digest is None: raise GameContractError("pending recovery action requires pending transaction")

def recover_editor(checkpoint:EditorCheckpoint,*,prefer_rollback:bool=True)->RecoveryDecision:
    if checkpoint.pending_transaction_digest is None:
        return RecoveryDecision(checkpoint.digest,"resume",checkpoint.project_digest,None)
    return RecoveryDecision(checkpoint.digest,"rollback-pending" if prefer_rollback else "discard-pending",checkpoint.project_digest,checkpoint.pending_transaction_digest)
