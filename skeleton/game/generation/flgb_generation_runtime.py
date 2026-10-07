"""FLGB-14 deterministic procedural generation and continuity contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Sequence
MAX_ID=256; MAX_ITEMS=100000; MAX_SCORE=1000000
class GenerationContractError(ValueError): pass
def _int(v): return isinstance(v,int) and not isinstance(v,bool)
def req_id(v,n):
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID: raise GenerationContractError(f"invalid {n}")
    return v
def req_digest(v,n):
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise GenerationContractError(f"invalid {n}")
    return v
def dig(v):
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode()
    except (TypeError,ValueError) as exc: raise GenerationContractError("non-canonical value") from exc
    return sha256(raw).hexdigest()
@dataclass(frozen=True)
class SeedContract:
    namespace:str; seed:int; generator_version:str; parent_seed_digest:str|None=None
    def __post_init__(self):
        req_id(self.namespace,"namespace"); req_id(self.generator_version,"generator_version")
        if not _int(self.seed) or self.seed<0 or self.seed>=2**64: raise GenerationContractError("invalid seed")
        if self.parent_seed_digest is not None: req_digest(self.parent_seed_digest,"parent_seed_digest")
    @property
    def digest(self): return dig(self.__dict__)
    def derive(self,label:str):
        label=req_id(label,"label"); value=int(sha256((self.digest+":"+label).encode()).hexdigest()[:16],16)
        return SeedContract(f"{self.namespace}:{label}",value,self.generator_version,self.digest)
@dataclass(frozen=True)
class TerrainChunk:
    chunk_id:str; seed_digest:str; x:int; y:int; size:int; height_digest:str; biome_digest:str
    def __post_init__(self):
        req_id(self.chunk_id,"chunk_id"); req_digest(self.seed_digest,"seed_digest"); req_digest(self.height_digest,"height_digest"); req_digest(self.biome_digest,"biome_digest")
        if not all(_int(v) for v in (self.x,self.y,self.size)) or self.size<1: raise GenerationContractError("invalid terrain coordinates")
    @property
    def digest(self): return dig(self.__dict__)
@dataclass(frozen=True)
class LayoutProduction:
    symbol:str; expansion:tuple[str,...]; weight:int
    def __post_init__(self):
        req_id(self.symbol,"symbol")
        for x in self.expansion: req_id(x,"expansion")
        if not _int(self.weight) or self.weight<1: raise GenerationContractError("invalid production weight")
def expand_layout(start:str,productions:Sequence[LayoutProduction],seed:int,max_steps:int)->tuple[str,...]:
    req_id(start,"start")
    if not _int(seed) or seed<0 or not _int(max_steps) or max_steps<0: raise GenerationContractError("invalid layout controls")
    by={}
    for p in productions: by.setdefault(p.symbol,[]).append(p)
    out=[start]
    for step in range(max_steps):
        idx=next((i for i,s in enumerate(out) if s in by),None)
        if idx is None: break
        options=sorted(by[out[idx]],key=lambda p:(p.weight,p.expansion))
        total=sum(p.weight for p in options); pick=int(sha256(f"{seed}:{step}:{out[idx]}".encode()).hexdigest()[:16],16)%total
        acc=0; chosen=None
        for p in options:
            acc+=p.weight
            if pick<acc: chosen=p; break
        out[idx:idx+1]=chosen.expansion
        if len(out)>MAX_ITEMS: raise GenerationContractError("layout expansion budget exceeded")
    return tuple(out)
@dataclass(frozen=True)
class EncounterSpec:
    encounter_id:str; seed_digest:str; difficulty:int; actor_ids:tuple[str,...]; reward_digest:str
    def __post_init__(self):
        req_id(self.encounter_id,"encounter_id"); req_digest(self.seed_digest,"seed_digest"); req_digest(self.reward_digest,"reward_digest")
        if not _int(self.difficulty) or not 0<=self.difficulty<=MAX_SCORE: raise GenerationContractError("invalid difficulty")
        ids=tuple(sorted(self.actor_ids))
        if not ids or len(set(ids))!=len(ids): raise GenerationContractError("invalid actor ids")
        for x in ids: req_id(x,"actor_id")
        object.__setattr__(self,"actor_ids",ids)
@dataclass(frozen=True)
class GeneratedQuest:
    quest_id:str; seed_digest:str; objective_ids:tuple[str,...]; dependency_ids:tuple[str,...]; canon_digest:str
    def __post_init__(self):
        req_id(self.quest_id,"quest_id"); req_digest(self.seed_digest,"seed_digest"); req_digest(self.canon_digest,"canon_digest")
        for seq,name in ((self.objective_ids,"objective"),(self.dependency_ids,"dependency")):
            if len(set(seq))!=len(seq): raise GenerationContractError(f"duplicate {name}")
            for x in seq: req_id(x,name)
@dataclass(frozen=True)
class GeneratedCharacter:
    character_id:str; seed_digest:str; archetype:str; trait_ids:tuple[str,...]; canon_digest:str
    def __post_init__(self):
        req_id(self.character_id,"character_id"); req_digest(self.seed_digest,"seed_digest"); req_id(self.archetype,"archetype"); req_digest(self.canon_digest,"canon_digest")
        traits=tuple(sorted(self.trait_ids))
        if len(set(traits))!=len(traits): raise GenerationContractError("duplicate trait")
        for x in traits: req_id(x,"trait")
        object.__setattr__(self,"trait_ids",traits)
@dataclass(frozen=True)
class LoreFact:
    fact_id:str; subject:str; predicate:str; object_digest:str; source_digest:str
    def __post_init__(self): req_id(self.fact_id,"fact_id"); req_id(self.subject,"subject"); req_id(self.predicate,"predicate"); req_digest(self.object_digest,"object_digest"); req_digest(self.source_digest,"source_digest")
class LoreGraph:
    def __init__(self,facts:Sequence[LoreFact]):
        ids=[f.fact_id for f in facts]
        if len(set(ids))!=len(ids): raise GenerationContractError("duplicate lore fact")
        claims={}
        for f in facts:
            key=(f.subject,f.predicate)
            if key in claims and claims[key]!=f.object_digest: raise GenerationContractError("lore contradiction")
            claims[key]=f.object_digest
        self.facts=tuple(sorted(facts,key=lambda f:f.fact_id))
    @property
    def digest(self): return dig([f.__dict__ for f in self.facts])
@dataclass(frozen=True)
class TimelineEvent:
    event_id:str; start_tick:int; end_tick:int; subject_ids:tuple[str,...]; event_digest:str
    def __post_init__(self):
        req_id(self.event_id,"event_id"); req_digest(self.event_digest,"event_digest")
        if not _int(self.start_tick) or not _int(self.end_tick) or self.start_tick<0 or self.end_tick<self.start_tick: raise GenerationContractError("invalid timeline range")
        if len(set(self.subject_ids))!=len(self.subject_ids): raise GenerationContractError("duplicate timeline subject")
        for x in self.subject_ids: req_id(x,"subject")
def timeline_conflicts(events:Sequence[TimelineEvent])->tuple[tuple[str,str],...]:
    conflicts=[]
    for i,a in enumerate(events):
        for b in events[i+1:]:
            if set(a.subject_ids)&set(b.subject_ids) and max(a.start_tick,b.start_tick)<min(a.end_tick,b.end_tick): conflicts.append(tuple(sorted((a.event_id,b.event_id))))
    return tuple(sorted(set(conflicts)))
@dataclass(frozen=True)
class CanonConstraint:
    constraint_id:str; subject:str; predicate:str; required_object_digest:str
    def __post_init__(self): req_id(self.constraint_id,"constraint_id"); req_id(self.subject,"subject"); req_id(self.predicate,"predicate"); req_digest(self.required_object_digest,"required_object_digest")
def validate_canon_constraints(facts:Sequence[LoreFact],constraints:Sequence[CanonConstraint])->tuple[str,...]:
    claims={(f.subject,f.predicate):f.object_digest for f in facts}; failed=[]
    for c in constraints:
        if claims.get((c.subject,c.predicate))!=c.required_object_digest: failed.append(c.constraint_id)
    return tuple(sorted(failed))
@dataclass(frozen=True)
class StyleBible:
    style_id:str; version:int; rule_digests:tuple[str,...]; forbidden_digests:tuple[str,...]
    def __post_init__(self):
        req_id(self.style_id,"style_id")
        if not _int(self.version) or self.version<1: raise GenerationContractError("invalid style version")
        for seq,name in ((self.rule_digests,"rule_digest"),(self.forbidden_digests,"forbidden_digest")):
            if len(set(seq))!=len(seq): raise GenerationContractError(f"duplicate {name}")
            for x in seq: req_digest(x,name)
    @property
    def digest(self): return dig({"style_id":self.style_id,"version":self.version,"rule_digests":list(self.rule_digests),"forbidden_digests":list(self.forbidden_digests)})
@dataclass(frozen=True)
class ContinuityIssue:
    issue_id:str; category:str; left_digest:str; right_digest:str; severity:str
    def __post_init__(self):
        req_id(self.issue_id,"issue_id"); req_id(self.category,"category"); req_digest(self.left_digest,"left_digest"); req_digest(self.right_digest,"right_digest")
        if self.severity not in {"warning","error","critical"}: raise GenerationContractError("invalid continuity severity")
def verify_continuity(lore:LoreGraph,events:Sequence[TimelineEvent],constraints:Sequence[CanonConstraint])->tuple[ContinuityIssue,...]:
    issues=[]
    for cid in validate_canon_constraints(lore.facts,constraints): issues.append(ContinuityIssue(f"canon:{cid}","canon",lore.digest,sha256(cid.encode()).hexdigest(),"critical"))
    for a,b in timeline_conflicts(events): issues.append(ContinuityIssue(f"time:{a}:{b}","timeline",sha256(a.encode()).hexdigest(),sha256(b.encode()).hexdigest(),"error"))
    return tuple(issues)
@dataclass(frozen=True)
class RegenerationChange:
    object_id:str; before_digest:str; after_digest:str; reason:str
    def __post_init__(self): req_id(self.object_id,"object_id"); req_digest(self.before_digest,"before_digest"); req_digest(self.after_digest,"after_digest"); req_id(self.reason,"reason")
def regeneration_diff(before:Mapping[str,str],after:Mapping[str,str],reason:str)->tuple[RegenerationChange,...]:
    req_id(reason,"reason"); changes=[]
    for key in sorted(set(before)|set(after)):
        b=before.get(key,"0"*64); a=after.get(key,"0"*64); req_id(key,"object_id"); req_digest(b,"before_digest"); req_digest(a,"after_digest")
        if a!=b: changes.append(RegenerationChange(key,b,a,reason))
    return tuple(changes)
