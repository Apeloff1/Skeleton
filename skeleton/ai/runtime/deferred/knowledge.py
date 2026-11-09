"""Knowledge, retrieval, memory and strategy controls for deferred AI volumes."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Mapping, Sequence

from .contracts import sha256_json


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result=float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class PolicyRevision:
    policy_id: str
    version: int
    digest: str
    kind: str

    def __post_init__(self) -> None:
        for name in ("policy_id", "kind"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if isinstance(self.version,bool) or not isinstance(self.version,int) or self.version<1:
            raise ValueError("policy version must be positive integer")
        object.__setattr__(self,"digest",_sha(self.digest,"digest"))


class PolicyRegistry:
    def __init__(self) -> None:
        self._current:dict[tuple[str,str],PolicyRevision]={}

    def publish(self,revision:PolicyRevision)->None:
        key=(revision.kind,revision.policy_id)
        prior=self._current.get(key)
        if prior is not None and revision.version<=prior.version:
            if prior==revision:
                return
            raise ValueError("policy versions must increase")
        self._current[key]=revision

    def current(self,kind:str,policy_id:str)->PolicyRevision:
        return self._current[(kind,policy_id)]


@dataclass(frozen=True, slots=True)
class DataContract:
    contract_id:str
    version:int
    schema_digest:str
    semantic_digest:str
    units:Mapping[str,str]
    lineage_required:bool=True

    def __post_init__(self)->None:
        object.__setattr__(self,"contract_id",_text(self.contract_id,"contract_id"))
        if isinstance(self.version,bool) or not isinstance(self.version,int) or self.version<1:
            raise ValueError("data contract version must be positive integer")
        object.__setattr__(self,"schema_digest",_sha(self.schema_digest,"schema_digest"))
        object.__setattr__(self,"semantic_digest",_sha(self.semantic_digest,"semantic_digest"))
        normalized={_text(k,"unit field"):_text(v,"unit") for k,v in self.units.items()}
        object.__setattr__(self,"units",normalized)
        if not isinstance(self.lineage_required,bool):
            raise TypeError("lineage_required must be boolean")


@dataclass(frozen=True, slots=True)
class EmbeddingIdentity:
    model_id:str
    model_digest:str
    dimensions:int
    normalization:str
    source_digest:str

    def __post_init__(self)->None:
        object.__setattr__(self,"model_id",_text(self.model_id,"model_id"))
        object.__setattr__(self,"model_digest",_sha(self.model_digest,"model_digest"))
        object.__setattr__(self,"source_digest",_sha(self.source_digest,"source_digest"))
        if isinstance(self.dimensions,bool) or not isinstance(self.dimensions,int) or self.dimensions<1:
            raise ValueError("dimensions must be positive integer")
        if self.normalization not in {"none","l2","unit"}:
            raise ValueError("unsupported normalization")

    @property
    def digest(self)->str:
        return sha256_json({
            "model_id":self.model_id,
            "model_digest":self.model_digest,
            "dimensions":self.dimensions,
            "normalization":self.normalization,
            "source_digest":self.source_digest,
        })


@dataclass(frozen=True, slots=True)
class IndexVersion:
    index_id:str
    version:int
    embedding_digest:str
    watermark:int
    complete:bool

    def __post_init__(self)->None:
        object.__setattr__(self,"index_id",_text(self.index_id,"index_id"))
        if isinstance(self.version,bool) or not isinstance(self.version,int) or self.version<1:
            raise ValueError("index version must be positive integer")
        object.__setattr__(self,"embedding_digest",_sha(self.embedding_digest,"embedding_digest"))
        if isinstance(self.watermark,bool) or not isinstance(self.watermark,int) or self.watermark<0:
            raise ValueError("watermark must be non-negative integer")
        if not isinstance(self.complete,bool):
            raise TypeError("complete must be boolean")


class IndexAlias:
    def __init__(self)->None:
        self._targets:dict[str,IndexVersion]={}

    def promote(self,alias:str,target:IndexVersion)->None:
        alias=_text(alias,"alias")
        if not target.complete:
            raise ValueError("cannot promote incomplete index")
        prior=self._targets.get(alias)
        if prior is not None and target.version<prior.version:
            raise ValueError("index alias cannot move backward without explicit rollback")
        self._targets[alias]=target

    def resolve(self,alias:str)->IndexVersion:
        return self._targets[alias]


@dataclass(frozen=True, slots=True)
class FreshnessRecord:
    source_id:str
    observed_at:int
    valid_until:int
    source_version:str

    def __post_init__(self)->None:
        object.__setattr__(self,"source_id",_text(self.source_id,"source_id"))
        object.__setattr__(self,"source_version",_text(self.source_version,"source_version"))
        for name in ("observed_at","valid_until"):
            value=getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,int) or value<0:
                raise ValueError(f"{name} must be non-negative integer")
        if self.valid_until<self.observed_at:
            raise ValueError("valid_until cannot precede observed_at")

    def fresh_at(self,now:int)->bool:
        return self.observed_at<=now<=self.valid_until


@dataclass(frozen=True, slots=True)
class SourceTrust:
    source_id:str
    authority:float
    recency:float
    independence:float
    provenance:float

    def __post_init__(self)->None:
        object.__setattr__(self,"source_id",_text(self.source_id,"source_id"))
        for name in ("authority","recency","independence","provenance"):
            value=_finite(getattr(self,name),name)
            if not 0.0<=value<=1.0:
                raise ValueError(f"{name} must be in [0,1]")
            object.__setattr__(self,name,value)

    @property
    def score(self)->float:
        return min(self.authority,self.recency,self.independence,self.provenance)


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    source_id:str
    lineage_root:str
    claim_id:str

    def __post_init__(self)->None:
        for name in ("source_id","lineage_root","claim_id"):
            object.__setattr__(self,name,_text(getattr(self,name),name))


class DiversityEngine:
    @staticmethod
    def independent_count(evidence:Sequence[SourceEvidence],claim_id:str)->int:
        return len({
            item.lineage_root
            for item in evidence
            if item.claim_id==claim_id
        })


@dataclass(frozen=True, slots=True)
class ClaimScope:
    population:str
    geography:str
    valid_from:int
    valid_until:int|None=None

    def __post_init__(self)->None:
        object.__setattr__(self,"population",_text(self.population,"population"))
        object.__setattr__(self,"geography",_text(self.geography,"geography"))
        if isinstance(self.valid_from,bool) or not isinstance(self.valid_from,int) or self.valid_from<0:
            raise ValueError("valid_from must be non-negative integer")
        if self.valid_until is not None:
            if isinstance(self.valid_until,bool) or not isinstance(self.valid_until,int) or self.valid_until<self.valid_from:
                raise ValueError("invalid valid_until")

    def active(self,now:int)->bool:
        return now>=self.valid_from and (self.valid_until is None or now<=self.valid_until)


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id:str
    statement_digest:str
    equivalence_key:str
    scope:ClaimScope
    source_ids:tuple[str,...]
    confidence:float

    def __post_init__(self)->None:
        object.__setattr__(self,"claim_id",_text(self.claim_id,"claim_id"))
        object.__setattr__(self,"statement_digest",_sha(self.statement_digest,"statement_digest"))
        object.__setattr__(self,"equivalence_key",_text(self.equivalence_key,"equivalence_key"))
        sources=tuple(_text(item,"source_id") for item in self.source_ids)
        if not sources or len(sources)!=len(set(sources)):
            raise ValueError("claim source ids must be unique and non-empty")
        object.__setattr__(self,"source_ids",sources)
        confidence=_finite(self.confidence,"confidence")
        if not 0.0<=confidence<=1.0:
            raise ValueError("confidence must be in [0,1]")
        object.__setattr__(self,"confidence",confidence)


class ClaimReconciler:
    @staticmethod
    def deduplicate(claims:Sequence[Claim])->tuple[Claim,...]:
        groups:dict[tuple[str,ClaimScope,str],list[Claim]]={}
        for claim in claims:
            groups.setdefault(
                (claim.equivalence_key,claim.scope,claim.statement_digest),
                [],
            ).append(claim)
        chosen=[]
        for _,items in sorted(
            groups.items(),
            key=lambda item:(item[0][0],repr(item[0][1]),item[0][2]),
        ):
            chosen.append(
                max(
                    items,
                    key=lambda claim:(
                        claim.confidence,
                        len(claim.source_ids),
                        claim.claim_id,
                    ),
                )
            )
        return tuple(chosen)

    @staticmethod
    def conflicts(claims:Sequence[Claim])->tuple[tuple[str,...],...]:
        by_key:dict[tuple[str,ClaimScope],list[Claim]]={}
        for claim in claims:
            by_key.setdefault((claim.equivalence_key,claim.scope),[]).append(claim)
        conflicts=[]
        for _,items in sorted(
            by_key.items(),
            key=lambda item:(item[0][0],repr(item[0][1])),
        ):
            digests={item.statement_digest for item in items}
            if len(digests)>1:
                conflicts.append(tuple(sorted(item.claim_id for item in items)))
        return tuple(conflicts)


@dataclass(frozen=True, slots=True)
class KnowledgeSnapshot:
    snapshot_id:str
    claim_digests:tuple[str,...]
    policy_digests:tuple[str,...]
    index_digests:tuple[str,...]

    def __post_init__(self)->None:
        object.__setattr__(self,"snapshot_id",_text(self.snapshot_id,"snapshot_id"))
        for collection_name in ("claim_digests","policy_digests","index_digests"):
            collection=getattr(self,collection_name)
            for item in collection:
                _sha(item,collection_name)
            if len(collection)!=len(set(collection)):
                raise ValueError(f"{collection_name} must be unique")

    @property
    def digest(self)->str:
        return sha256_json({
            "snapshot_id":self.snapshot_id,
            "claim_digests":sorted(self.claim_digests),
            "policy_digests":sorted(self.policy_digests),
            "index_digests":sorted(self.index_digests),
        })


@dataclass(frozen=True, slots=True)
class MemoryRevision:
    memory_id:str
    revision:int
    content_digest:str
    supersedes_digest:str|None
    tombstone:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"memory_id",_text(self.memory_id,"memory_id"))
        if isinstance(self.revision,bool) or not isinstance(self.revision,int) or self.revision<1:
            raise ValueError("memory revision must be positive integer")
        object.__setattr__(self,"content_digest",_sha(self.content_digest,"content_digest"))
        if self.supersedes_digest is not None:
            object.__setattr__(self,"supersedes_digest",_sha(self.supersedes_digest,"supersedes_digest"))
        if not isinstance(self.tombstone,bool):
            raise TypeError("tombstone must be boolean")

    @property
    def digest(self)->str:
        return sha256_json({
            "memory_id":self.memory_id,
            "revision":self.revision,
            "content_digest":self.content_digest,
            "supersedes_digest":self.supersedes_digest,
            "tombstone":self.tombstone,
        })


class VersionedMemory:
    def __init__(self)->None:
        self._latest:dict[str,MemoryRevision]={}
        self._history:dict[str,list[MemoryRevision]]={}

    def append(self,revision:MemoryRevision)->None:
        prior=self._latest.get(revision.memory_id)
        if prior is None:
            if revision.revision!=1 or revision.supersedes_digest is not None:
                raise ValueError("first memory revision must start at one")
        else:
            if revision.revision!=prior.revision+1:
                raise ValueError("memory revisions must be contiguous")
            if revision.supersedes_digest!=prior.digest:
                raise ValueError("memory supersession digest mismatch")
            if prior.tombstone and not revision.tombstone:
                raise ValueError("tombstoned memory cannot be resurrected")
        self._latest[revision.memory_id]=revision
        self._history.setdefault(revision.memory_id,[]).append(revision)

    def latest(self,memory_id:str)->MemoryRevision:
        return self._latest[memory_id]

    def history(self,memory_id:str)->tuple[MemoryRevision,...]:
        return tuple(self._history.get(memory_id,()))


@dataclass(frozen=True, slots=True)
class Hypothesis:
    hypothesis_id:str
    statement_digest:str
    supporting_evidence:tuple[str,...]=()
    refuting_evidence:tuple[str,...]=()

    def __post_init__(self)->None:
        object.__setattr__(self,"hypothesis_id",_text(self.hypothesis_id,"hypothesis_id"))
        object.__setattr__(self,"statement_digest",_sha(self.statement_digest,"statement_digest"))
        if set(self.supporting_evidence)&set(self.refuting_evidence):
            raise ValueError("evidence cannot both support and refute a hypothesis")

    @property
    def status(self)->str:
        if self.refuting_evidence:
            return "contested"
        if self.supporting_evidence:
            return "supported"
        return "open"


@dataclass(frozen=True, slots=True)
class CausalEdge:
    cause:str
    effect:str
    evidence_digest:str

    def __post_init__(self)->None:
        object.__setattr__(self,"cause",_text(self.cause,"cause"))
        object.__setattr__(self,"effect",_text(self.effect,"effect"))
        if self.cause==self.effect:
            raise ValueError("causal self-edge forbidden")
        object.__setattr__(self,"evidence_digest",_sha(self.evidence_digest,"evidence_digest"))


class CausalGraph:
    def __init__(self)->None:
        self._edges:set[CausalEdge]=set()

    def add(self,edge:CausalEdge)->None:
        self._edges.add(edge)
        adjacency:dict[str,set[str]]={}
        for item in self._edges:
            adjacency.setdefault(item.cause,set()).add(item.effect)
        visiting:set[str]=set()
        visited:set[str]=set()
        def walk(node:str)->None:
            if node in visiting:
                raise ValueError("causal graph cycle detected")
            if node in visited:
                return
            visiting.add(node)
            for child in adjacency.get(node,()):
                walk(child)
            visiting.remove(node)
            visited.add(node)
        try:
            for node in tuple(adjacency):
                walk(node)
        except Exception:
            self._edges.remove(edge)
            raise


@dataclass(frozen=True, slots=True)
class StrategySpec:
    strategy_id:str
    version:int
    max_cost_units:int
    capability_tags:tuple[str,...]
    evidence_score:float

    def __post_init__(self)->None:
        object.__setattr__(self,"strategy_id",_text(self.strategy_id,"strategy_id"))
        if isinstance(self.version,bool) or not isinstance(self.version,int) or self.version<1:
            raise ValueError("strategy version must be positive integer")
        if isinstance(self.max_cost_units,bool) or not isinstance(self.max_cost_units,int) or self.max_cost_units<1:
            raise ValueError("max_cost_units must be positive integer")
        tags=tuple(_text(item,"capability tag") for item in self.capability_tags)
        if not tags or len(tags)!=len(set(tags)):
            raise ValueError("capability tags must be unique and non-empty")
        object.__setattr__(self,"capability_tags",tags)
        score=_finite(self.evidence_score,"evidence_score")
        if not 0.0<=score<=1.0:
            raise ValueError("evidence_score must be in [0,1]")
        object.__setattr__(self,"evidence_score",score)


class StrategyRegistry:
    def __init__(self)->None:
        self._items:dict[str,StrategySpec]={}

    def publish(self,spec:StrategySpec)->None:
        prior=self._items.get(spec.strategy_id)
        if prior is not None and spec.version<=prior.version:
            if prior==spec:
                return
            raise ValueError("strategy version must increase")
        self._items[spec.strategy_id]=spec

    def select(self,required_tags:Iterable[str],max_cost_units:int)->StrategySpec:
        required=set(required_tags)
        candidates=[
            item for item in self._items.values()
            if required.issubset(set(item.capability_tags))
            and item.max_cost_units<=max_cost_units
        ]
        if not candidates:
            raise RuntimeError("no qualified cognitive strategy")
        return max(candidates,key=lambda item:(item.evidence_score,-item.max_cost_units,item.strategy_id))


@dataclass(frozen=True, slots=True)
class ReasoningCost:
    operation_id:str
    stage_id:str
    cost_units:int
    token_units:int

    def __post_init__(self)->None:
        for name in ("operation_id","stage_id"):
            object.__setattr__(self,name,_text(getattr(self,name),name))
        for name in ("cost_units","token_units"):
            value=getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,int) or value<0:
                raise ValueError(f"{name} must be non-negative integer")
