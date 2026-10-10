"""FLGB-14 deterministic procedural generation contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Sequence

MAX_ID=256; MAX_RULES=100000; MAX_NODES=1000000; MAX_SCORE=1000000; MAX_COORD=10**12
class GenerationContractError(ValueError): pass
def _int(v:Any)->bool:return isinstance(v,int) and not isinstance(v,bool)
def rid(v:str,n:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID: raise GenerationContractError(f"invalid {n}")
    return v
def rdig(v:str,n:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise GenerationContractError(f"invalid {n}")
    return v
def dig(v:Any)->str:
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    except (TypeError,ValueError) as exc: raise GenerationContractError("non-canonical value") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class SeedContract:
    project_id:str; root_seed_digest:str; generator_version:str
    def __post_init__(self): rid(self.project_id,"project_id");rdig(self.root_seed_digest,"root_seed_digest");rid(self.generator_version,"generator_version")
    def derive(self,domain:str,identity:str)->str:return dig({"root":self.root_seed_digest,"version":self.generator_version,"domain":rid(domain,"domain"),"identity":rid(identity,"identity")})
    @property
    def digest(self)->str:return dig(self.__dict__)

@dataclass(frozen=True)
class TerrainChunkRequest:
    world_id:str; chunk_x:int; chunk_y:int; resolution:int; seed_digest:str; biome_digest:str
    def __post_init__(self):
        rid(self.world_id,"world_id");rdig(self.seed_digest,"seed_digest");rdig(self.biome_digest,"biome_digest")
        if any(not _int(v) or abs(v)>MAX_COORD for v in (self.chunk_x,self.chunk_y)):raise GenerationContractError("invalid chunk coordinate")
        if not _int(self.resolution) or not 2<=self.resolution<=8192:raise GenerationContractError("invalid resolution")
    @property
    def request_digest(self)->str:return dig(self.__dict__)

@dataclass(frozen=True)
class TerrainChunkReceipt:
    request_digest:str; height_digest:str; material_digest:str; collision_digest:str
    def __post_init__(self):
        for n in ("request_digest","height_digest","material_digest","collision_digest"):rdig(getattr(self,n),n)

@dataclass(frozen=True)
class GrammarRule:
    rule_id:str; symbol:str; expansion_digest:str; weight:int
    def __post_init__(self):
        rid(self.rule_id,"rule_id");rid(self.symbol,"symbol");rdig(self.expansion_digest,"expansion_digest")
        if not _int(self.weight) or self.weight<=0:raise GenerationContractError("invalid grammar weight")

class LayoutGrammar:
    def __init__(self,rules:Sequence[GrammarRule]):
        if not rules or len(rules)>MAX_RULES:raise GenerationContractError("invalid grammar size")
        grouped={};ids=set()
        for rule in rules:
            if rule.rule_id in ids:raise GenerationContractError("duplicate grammar rule")
            ids.add(rule.rule_id);grouped.setdefault(rule.symbol,[]).append(rule)
        self._rules=MappingProxyType({k:tuple(sorted(v,key=lambda r:r.rule_id)) for k,v in grouped.items()})
    def choose(self,symbol:str,seed_digest:str)->GrammarRule:
        rules=self._rules.get(rid(symbol,"symbol"));rdig(seed_digest,"seed_digest")
        if not rules:raise GenerationContractError("unknown grammar symbol")
        total=sum(r.weight for r in rules);cursor=int(dig({"seed":seed_digest,"symbol":symbol}),16)%total
        for rule in rules:
            if cursor<rule.weight:return rule
            cursor-=rule.weight
        raise GenerationContractError("grammar selection overflow")

@dataclass(frozen=True)
class EncounterCandidate:
    encounter_id:str; cost:int; difficulty_ppm:int; canon_digest:str
    def __post_init__(self):
        rid(self.encounter_id,"encounter_id");rdig(self.canon_digest,"canon_digest")
        if not _int(self.cost) or self.cost<0:raise GenerationContractError("invalid cost")
        if not _int(self.difficulty_ppm) or not 0<=self.difficulty_ppm<=MAX_SCORE:raise GenerationContractError("invalid difficulty")

def select_encounters(candidates:Sequence[EncounterCandidate],budget:int,target_difficulty_ppm:int)->tuple[str,...]:
    if not _int(budget) or budget<0:raise GenerationContractError("invalid budget")
    if not _int(target_difficulty_ppm) or not 0<=target_difficulty_ppm<=MAX_SCORE:raise GenerationContractError("invalid target difficulty")
    ids=[c.encounter_id for c in candidates]
    if len(set(ids))!=len(ids):raise GenerationContractError("duplicate encounter")
    used=0;selected=[]
    for c in sorted(candidates,key=lambda c:(abs(c.difficulty_ppm-target_difficulty_ppm),c.cost,c.encounter_id)):
        if used+c.cost<=budget:selected.append(c.encounter_id);used+=c.cost
    return tuple(selected)

@dataclass(frozen=True)
class QuestBeat:
    beat_id:str; dependencies:tuple[str,...]; canon_digest:str; objective_digest:str
    def __post_init__(self):
        rid(self.beat_id,"beat_id");rdig(self.canon_digest,"canon_digest");rdig(self.objective_digest,"objective_digest")
        deps=tuple(sorted(self.dependencies))
        if self.beat_id in deps or len(set(deps))!=len(deps):raise GenerationContractError("invalid quest dependencies")
        for dep in deps:rid(dep,"dependency")
        object.__setattr__(self,"dependencies",deps)

class QuestBlueprint:
    def __init__(self,beats:Sequence[QuestBeat]):
        by_id={b.beat_id:b for b in beats}
        if not beats or len(beats)>MAX_NODES or len(by_id)!=len(beats):raise GenerationContractError("invalid quest beats")
        for beat in beats:
            if set(beat.dependencies)-set(by_id):raise GenerationContractError("unknown quest dependency")
        self._beats=MappingProxyType(by_id);self._waves=self._build()
    def _build(self):
        remaining=set(self._beats);done=set();waves=[]
        while remaining:
            ready=sorted(x for x in remaining if set(self._beats[x].dependencies).issubset(done))
            if not ready:raise GenerationContractError("quest cycle")
            waves.append(tuple(ready));done.update(ready);remaining.difference_update(ready)
        return tuple(waves)
    @property
    def waves(self):return self._waves

@dataclass(frozen=True)
class CharacterProfile:
    character_id:str; archetype:str; seed_digest:str; canon_digest:str; trait_ids:tuple[str,...]
    def __post_init__(self):
        rid(self.character_id,"character_id");rid(self.archetype,"archetype");rdig(self.seed_digest,"seed_digest");rdig(self.canon_digest,"canon_digest")
        traits=tuple(sorted(self.trait_ids))
        if len(set(traits))!=len(traits):raise GenerationContractError("duplicate trait")
        for trait in traits:rid(trait,"trait")
        object.__setattr__(self,"trait_ids",traits)
    @property
    def digest(self):return dig({"character_id":self.character_id,"archetype":self.archetype,"seed_digest":self.seed_digest,"canon_digest":self.canon_digest,"trait_ids":list(self.trait_ids)})
