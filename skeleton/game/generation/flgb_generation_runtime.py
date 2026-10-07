"""FLGB-14 deterministic procedural generation, canon, continuity, and regeneration contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_RULES=100_000
MAX_NODES=1_000_000
MAX_EVENTS=1_000_000
MAX_TAGS=4096
MAX_BUDGET=10**12
MAX_COORD=10**9
MAX_SCORE_PPM=1_000_000

class GenerationContractError(ValueError):
    """Fail-closed FLGB-14 contract error."""

def _is_int(value:Any)->bool:return isinstance(value,int) and not isinstance(value,bool)

def require_id(value:str,name:str)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>MAX_ID_CHARS or any(ord(ch)<32 for ch in value):raise GenerationContractError(f"invalid {name}")
    return value

def require_digest(value:str,name:str)->str:
    if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):raise GenerationContractError(f"invalid {name}")
    return value

def digest_json(value:Any)->str:
    try:raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError) as exc:raise GenerationContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

def _canonical_ids(values:Sequence[str],name:str,max_items:int=MAX_TAGS)->tuple[str,...]:
    result=tuple(sorted(values))
    if len(result)>max_items or len(set(result))!=len(result):raise GenerationContractError(f"invalid {name}")
    for item in result:require_id(item,name)
    return result

@dataclass(frozen=True)
class SeedContract:
    project_id:str
    generator_id:str
    generator_version:str
    seed:int
    config_digest:str
    parent_seed_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.project_id,"project_id");require_id(self.generator_id,"generator_id");require_id(self.generator_version,"generator_version");require_digest(self.config_digest,"config_digest")
        if not _is_int(self.seed) or not 0<=self.seed<=2**63-1:raise GenerationContractError("invalid seed")
        if self.parent_seed_digest is not None:require_digest(self.parent_seed_digest,"parent_seed_digest")

    @property
    def digest(self)->str:return digest_json(self.__dict__)

    def derive(self,label:str)->"SeedContract":
        label=require_id(label,"seed label")
        raw=sha256(f"{self.digest}:{label}".encode("utf-8")).digest()
        child_seed=int.from_bytes(raw[:8],"big")&((1<<63)-1)
        return SeedContract(self.project_id,f"{self.generator_id}/{label}",self.generator_version,child_seed,self.config_digest,self.digest)

@dataclass(frozen=True)
class TerrainTile:
    tile_id:str
    x:int
    y:int
    resolution:int
    height_digest:str
    biome_digest:str
    seed_digest:str

    def __post_init__(self)->None:
        require_id(self.tile_id,"tile_id");require_digest(self.height_digest,"height_digest");require_digest(self.biome_digest,"biome_digest");require_digest(self.seed_digest,"seed_digest")
        for name in ("x","y"):
            value=getattr(self,name)
            if not _is_int(value) or abs(value)>MAX_COORD:raise GenerationContractError(f"invalid {name}")
        if not _is_int(self.resolution) or not 2<=self.resolution<=16384:raise GenerationContractError("invalid terrain resolution")

def generate_terrain_tile(seed:SeedContract,x:int,y:int,resolution:int,biome_digest:str)->TerrainTile:
    if not isinstance(seed,SeedContract):raise GenerationContractError("SeedContract required")
    require_digest(biome_digest,"biome_digest")
    tile_id=f"{x}:{y}"
    height_digest=digest_json({"seed":seed.digest,"x":x,"y":y,"resolution":resolution,"domain":"height"})
    return TerrainTile(tile_id,x,y,resolution,height_digest,biome_digest,seed.digest)

@dataclass(frozen=True)
class LayoutRule:
    rule_id:str
    symbol:str
    expansion:tuple[str,...]
    weight:int

    def __post_init__(self)->None:
        require_id(self.rule_id,"rule_id");require_id(self.symbol,"symbol")
        expansion=tuple(self.expansion)
        if not expansion or len(expansion)>MAX_RULES:raise GenerationContractError("invalid layout expansion")
        for item in expansion:require_id(item,"layout symbol")
        object.__setattr__(self,"expansion",expansion)
        if not _is_int(self.weight) or not 1<=self.weight<=1_000_000:raise GenerationContractError("invalid layout weight")

class LayoutGrammar:
    def __init__(self,rules:Sequence[LayoutRule])->None:
        if not rules or len(rules)>MAX_RULES:raise GenerationContractError("layout rule count out of bounds")
        ids=[r.rule_id for r in rules]
        if len(set(ids))!=len(ids):raise GenerationContractError("duplicate layout rule")
        grouped={}
        for rule in rules:grouped.setdefault(rule.symbol,[]).append(rule)
        self._rules=MappingProxyType({k:tuple(sorted(v,key=lambda r:r.rule_id)) for k,v in sorted(grouped.items())})

    def expand(self,symbol:str,seed:SeedContract,depth:int)->tuple[str,...]:
        symbol=require_id(symbol,"symbol")
        if not _is_int(depth) or not 0<=depth<=64:raise GenerationContractError("invalid layout depth")
        frontier=(symbol,)
        for level in range(depth):
            out=[]
            for index,item in enumerate(frontier):
                candidates=self._rules.get(item)
                if not candidates:out.append(item);continue
                total=sum(rule.weight for rule in candidates)
                pick=int(sha256(f"{seed.digest}:{level}:{index}:{item}".encode("utf-8")).hexdigest(),16)%total
                cursor=0;chosen=candidates[-1]
                for rule in candidates:
                    cursor+=rule.weight
                    if pick<cursor:chosen=rule;break
                out.extend(chosen.expansion)
                if len(out)>MAX_NODES:raise GenerationContractError("layout expansion budget exceeded")
            frontier=tuple(out)
        return frontier

@dataclass(frozen=True)
class EncounterTemplate:
    encounter_id:str
    threat_cost:int
    enemy_tags:tuple[str,...]
    environment_tags:tuple[str,...]

    def __post_init__(self)->None:
        require_id(self.encounter_id,"encounter_id")
        if not _is_int(self.threat_cost) or not 1<=self.threat_cost<=MAX_BUDGET:raise GenerationContractError("invalid threat_cost")
        object.__setattr__(self,"enemy_tags",_canonical_ids(self.enemy_tags,"enemy_tag"))
        object.__setattr__(self,"environment_tags",_canonical_ids(self.environment_tags,"environment_tag"))

def generate_encounters(templates:Sequence[EncounterTemplate],budget:int,seed:SeedContract)->tuple[str,...]:
    if not _is_int(budget) or not 0<=budget<=MAX_BUDGET:raise GenerationContractError("invalid encounter budget")
    ids=[t.encounter_id for t in templates]
    if len(set(ids))!=len(ids):raise GenerationContractError("duplicate encounter template")
    ordered=sorted(templates,key=lambda t:(sha256(f"{seed.digest}:{t.encounter_id}".encode("utf-8")).hexdigest(),t.encounter_id))
    selected=[];used=0
    for template in ordered:
        if used+template.threat_cost<=budget:selected.append(template.encounter_id);used+=template.threat_cost
    return tuple(selected)

@dataclass(frozen=True)
class QuestNode:
    node_id:str
    kind:str
    prerequisites:tuple[str,...]=()
    reward_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.node_id,"node_id");require_id(self.kind,"kind")
        prereqs=tuple(sorted(self.prerequisites))
        if self.node_id in prereqs or len(set(prereqs))!=len(prereqs):raise GenerationContractError("invalid quest prerequisites")
        for item in prereqs:require_id(item,"quest prerequisite")
        object.__setattr__(self,"prerequisites",prereqs)
        if self.reward_digest is not None:require_digest(self.reward_digest,"reward_digest")

class GeneratedQuest:
    def __init__(self,quest_id:str,nodes:Sequence[QuestNode],seed_digest:str)->None:
        self.quest_id=require_id(quest_id,"quest_id");require_digest(seed_digest,"seed_digest");self.seed_digest=seed_digest
        if not nodes or len(nodes)>MAX_NODES:raise GenerationContractError("quest node count out of bounds")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes):raise GenerationContractError("duplicate quest node")
        for node in nodes:
            if set(node.prerequisites)-set(by_id):raise GenerationContractError("unknown quest prerequisite")
        self._nodes=MappingProxyType(by_id);self._validate()

    def _validate(self)->None:
        remaining=set(self._nodes);done=set()
        while remaining:
            ready=sorted(node_id for node_id in remaining if set(self._nodes[node_id].prerequisites).issubset(done))
            if not ready:raise GenerationContractError("quest graph cycle")
            done.update(ready);remaining.difference_update(ready)

    @property
    def digest(self)->str:return digest_json({"quest_id":self.quest_id,"seed_digest":self.seed_digest,"nodes":[{"node_id":n.node_id,"kind":n.kind,"prerequisites":list(n.prerequisites),"reward_digest":n.reward_digest} for n in sorted(self._nodes.values(),key=lambda n:n.node_id)]})

@dataclass(frozen=True)
class CharacterTemplate:
    archetype_id:str
    trait_pool:tuple[str,...]
    required_traits:tuple[str,...]=()

    def __post_init__(self)->None:
        require_id(self.archetype_id,"archetype_id")
        pool=_canonical_ids(self.trait_pool,"trait",MAX_TAGS);required=_canonical_ids(self.required_traits,"required_trait",MAX_TAGS)
        if not set(required).issubset(pool):raise GenerationContractError("required trait not in trait pool")
        object.__setattr__(self,"trait_pool",pool);object.__setattr__(self,"required_traits",required)

def generate_character(template:CharacterTemplate,seed:SeedContract,optional_trait_count:int)->tuple[str,...]:
    if not _is_int(optional_trait_count) or optional_trait_count<0:raise GenerationContractError("invalid optional_trait_count")
    optional=[t for t in template.trait_pool if t not in template.required_traits]
    ordered=sorted(optional,key=lambda t:(sha256(f"{seed.digest}:{t}".encode("utf-8")).hexdigest(),t))
    return tuple(sorted(set(template.required_traits)|set(ordered[:optional_trait_count])))

@dataclass(frozen=True)
class LoreNode:
    lore_id:str
    statement_digest:str
    evidence_digest:str
    tags:tuple[str,...]=()

    def __post_init__(self)->None:
        require_id(self.lore_id,"lore_id");require_digest(self.statement_digest,"statement_digest");require_digest(self.evidence_digest,"evidence_digest")
        object.__setattr__(self,"tags",_canonical_ids(self.tags,"lore_tag"))

@dataclass(frozen=True)
class LoreEdge:
    source_id:str
    target_id:str
    relation:str

    def __post_init__(self)->None:
        require_id(self.source_id,"source_id");require_id(self.target_id,"target_id");require_id(self.relation,"relation")
        if self.source_id==self.target_id:raise GenerationContractError("self lore edge forbidden")

class LoreGraph:
    def __init__(self,nodes:Sequence[LoreNode],edges:Sequence[LoreEdge])->None:
        if len(nodes)>MAX_NODES or len(edges)>MAX_NODES:raise GenerationContractError("lore graph budget exceeded")
        by_id={n.lore_id:n for n in nodes}
        if len(by_id)!=len(nodes):raise GenerationContractError("duplicate lore node")
        edge_keys=set()
        for edge in edges:
            if edge.source_id not in by_id or edge.target_id not in by_id:raise GenerationContractError("orphan lore edge")
            key=(edge.source_id,edge.target_id,edge.relation)
            if key in edge_keys:raise GenerationContractError("duplicate lore edge")
            edge_keys.add(key)
        self.nodes=tuple(sorted(nodes,key=lambda n:n.lore_id));self.edges=tuple(sorted(edges,key=lambda e:(e.source_id,e.target_id,e.relation)))

    @property
    def digest(self)->str:return digest_json({"nodes":[{"lore_id":n.lore_id,"statement_digest":n.statement_digest,"evidence_digest":n.evidence_digest,"tags":list(n.tags)} for n in self.nodes],"edges":[e.__dict__ for e in self.edges]})

@dataclass(frozen=True)
class TimelineEvent:
    event_id:str
    start_tick:int
    end_tick:int
    subject_id:str
    event_digest:str

    def __post_init__(self)->None:
        require_id(self.event_id,"event_id");require_id(self.subject_id,"subject_id");require_digest(self.event_digest,"event_digest")
        if not _is_int(self.start_tick) or not _is_int(self.end_tick) or not 0<=self.start_tick<=self.end_tick:raise GenerationContractError("invalid timeline interval")

def validate_timeline(events:Sequence[TimelineEvent])->tuple[TimelineEvent,...]:
    ids=[e.event_id for e in events]
    if len(set(ids))!=len(ids) or len(events)>MAX_EVENTS:raise GenerationContractError("invalid timeline event set")
    by_subject={}
    for event in sorted(events,key=lambda e:(e.subject_id,e.start_tick,e.end_tick,e.event_id)):
        prior=by_subject.get(event.subject_id)
        if prior is not None and event.start_tick<prior.end_tick:raise GenerationContractError("subject timeline overlap")
        by_subject[event.subject_id]=event
    return tuple(sorted(events,key=lambda e:(e.start_tick,e.end_tick,e.event_id)))

@dataclass(frozen=True)
class CanonConstraint:
    constraint_id:str
    subject_id:str
    predicate:str
    object_digest:str
    mode:str="must-equal"

    def __post_init__(self)->None:
        require_id(self.constraint_id,"constraint_id");require_id(self.subject_id,"subject_id");require_id(self.predicate,"predicate");require_digest(self.object_digest,"object_digest")
        if self.mode not in {"must-equal","must-not-equal"}:raise GenerationContractError("invalid canon constraint mode")

def verify_canon(constraints:Sequence[CanonConstraint],facts:Mapping[tuple[str,str],str])->tuple[str,...]:
    seen=set();violations=[]
    for constraint in constraints:
        key=(constraint.subject_id,constraint.predicate)
        identity=(constraint.constraint_id,key)
        if identity in seen:raise GenerationContractError("duplicate canon constraint")
        seen.add(identity)
        actual=facts.get(key)
        if actual is not None:require_digest(actual,"fact digest")
        violated=(constraint.mode=="must-equal" and actual!=constraint.object_digest) or (constraint.mode=="must-not-equal" and actual==constraint.object_digest)
        if violated:violations.append(constraint.constraint_id)
    return tuple(sorted(violations))

@dataclass(frozen=True)
class StyleBible:
    bible_id:str
    version:int
    required_tags:tuple[str,...]
    forbidden_tags:tuple[str,...]
    reference_digest:str

    def __post_init__(self)->None:
        require_id(self.bible_id,"bible_id");require_digest(self.reference_digest,"reference_digest")
        if not _is_int(self.version) or self.version<1:raise GenerationContractError("invalid style bible version")
        required=_canonical_ids(self.required_tags,"required_tag");forbidden=_canonical_ids(self.forbidden_tags,"forbidden_tag")
        if set(required)&set(forbidden):raise GenerationContractError("style tag cannot be both required and forbidden")
        object.__setattr__(self,"required_tags",required);object.__setattr__(self,"forbidden_tags",forbidden)

    def validate_tags(self,tags:Sequence[str])->tuple[str,...]:
        present=set(_canonical_ids(tags,"style_tag"))
        violations=[f"missing:{tag}" for tag in self.required_tags if tag not in present]
        violations.extend(f"forbidden:{tag}" for tag in self.forbidden_tags if tag in present)
        return tuple(sorted(violations))

    @property
    def digest(self)->str:return digest_json({"bible_id":self.bible_id,"version":self.version,"required_tags":list(self.required_tags),"forbidden_tags":list(self.forbidden_tags),"reference_digest":self.reference_digest})

@dataclass(frozen=True)
class ContinuityFinding:
    finding_id:str
    category:str
    severity:str
    evidence_digest:str

    def __post_init__(self)->None:
        require_id(self.finding_id,"finding_id");require_id(self.category,"category");require_digest(self.evidence_digest,"evidence_digest")
        if self.severity not in {"info","warning","error","critical"}:raise GenerationContractError("invalid continuity severity")

@dataclass(frozen=True)
class ContinuityReport:
    artifact_digest:str
    findings:tuple[ContinuityFinding,...]

    def __post_init__(self)->None:
        require_digest(self.artifact_digest,"artifact_digest")
        ids=[f.finding_id for f in self.findings]
        if len(set(ids))!=len(ids):raise GenerationContractError("duplicate continuity finding")

    @property
    def passed(self)->bool:return not any(f.severity in {"error","critical"} for f in self.findings)

    @property
    def digest(self)->str:return digest_json({"artifact_digest":self.artifact_digest,"findings":[f.__dict__ for f in sorted(self.findings,key=lambda f:f.finding_id)]})

@dataclass(frozen=True)
class RegenerationDiff:
    scope_id:str
    before_digest:str
    after_digest:str
    added_ids:tuple[str,...]
    removed_ids:tuple[str,...]
    changed_ids:tuple[str,...]
    seed_digest:str

    def __post_init__(self)->None:
        require_id(self.scope_id,"scope_id");require_digest(self.before_digest,"before_digest");require_digest(self.after_digest,"after_digest");require_digest(self.seed_digest,"seed_digest")
        for name in ("added_ids","removed_ids","changed_ids"):
            values=_canonical_ids(getattr(self,name),name,MAX_NODES);object.__setattr__(self,name,values)
        if set(self.added_ids)&set(self.removed_ids) or set(self.added_ids)&set(self.changed_ids) or set(self.removed_ids)&set(self.changed_ids):raise GenerationContractError("regeneration diff categories overlap")

    @property
    def changed(self)->bool:return self.before_digest!=self.after_digest

    @property
    def digest(self)->str:return digest_json({"scope_id":self.scope_id,"before_digest":self.before_digest,"after_digest":self.after_digest,"added_ids":list(self.added_ids),"removed_ids":list(self.removed_ids),"changed_ids":list(self.changed_ids),"seed_digest":self.seed_digest})
