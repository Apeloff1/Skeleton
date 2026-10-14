"""FLGB-14 lore, canon, timeline, style, continuity, and regeneration contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Sequence

MAX_ID=256;MAX_EVENTS=1_000_000;MAX_RULES=100_000
class ContinuityContractError(ValueError):pass
def _int(v:Any)->bool:return isinstance(v,int) and not isinstance(v,bool)
def rid(v:str,n:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID:raise ContinuityContractError(f"invalid {n}")
    return v
def rdig(v:str,n:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):raise ContinuityContractError(f"invalid {n}")
    return v
def dig(v:Any)->str:return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class LoreClaim:
    claim_id:str;subject:str;predicate:str;object_digest:str;evidence_digest:str
    def __post_init__(self):rid(self.claim_id,"claim_id");rid(self.subject,"subject");rid(self.predicate,"predicate");rdig(self.object_digest,"object_digest");rdig(self.evidence_digest,"evidence_digest")

@dataclass(frozen=True)
class LoreEdge:
    source_claim_id:str;target_claim_id:str;relation:str
    def __post_init__(self):
        rid(self.source_claim_id,"source_claim_id");rid(self.target_claim_id,"target_claim_id")
        if self.source_claim_id==self.target_claim_id:raise ContinuityContractError("self lore edge")
        if self.relation not in {"supports","causes","precedes","contradicts","refines"}:raise ContinuityContractError("invalid lore relation")

class LoreGraph:
    def __init__(self,claims:Sequence[LoreClaim],edges:Sequence[LoreEdge]):
        by_id={c.claim_id:c for c in claims}
        if len(by_id)!=len(claims):raise ContinuityContractError("duplicate lore claim")
        seen=set()
        for edge in edges:
            key=(edge.source_claim_id,edge.target_claim_id,edge.relation)
            if key in seen or edge.source_claim_id not in by_id or edge.target_claim_id not in by_id:raise ContinuityContractError("invalid lore edge")
            seen.add(key)
        self.claims=tuple(sorted(claims,key=lambda c:c.claim_id));self.edges=tuple(sorted(edges,key=lambda e:(e.source_claim_id,e.target_claim_id,e.relation)))
    @property
    def digest(self):return dig({"claims":[c.__dict__ for c in self.claims],"edges":[e.__dict__ for e in self.edges]})

@dataclass(frozen=True)
class TimelineEvent:
    event_id:str;start_tick:int;end_tick:int;causal_parents:tuple[str,...];canon_digest:str
    def __post_init__(self):
        rid(self.event_id,"event_id");rdig(self.canon_digest,"canon_digest")
        if not _int(self.start_tick) or not _int(self.end_tick) or not 0<=self.start_tick<=self.end_tick:raise ContinuityContractError("invalid timeline interval")
        parents=tuple(sorted(self.causal_parents))
        if self.event_id in parents or len(set(parents))!=len(parents):raise ContinuityContractError("invalid causal parents")
        for p in parents:rid(p,"causal parent")
        object.__setattr__(self,"causal_parents",parents)

def validate_timeline(events:Sequence[TimelineEvent])->tuple[TimelineEvent,...]:
    if len(events)>MAX_EVENTS:raise ContinuityContractError("timeline budget exceeded")
    by_id={e.event_id:e for e in events}
    if len(by_id)!=len(events):raise ContinuityContractError("duplicate timeline event")
    ordered=tuple(sorted(events,key=lambda e:(e.start_tick,e.end_tick,e.event_id)))
    for event in ordered:
        for pid in event.causal_parents:
            if pid not in by_id or by_id[pid].end_tick>event.start_tick:raise ContinuityContractError("invalid causal ordering")
    return ordered

@dataclass(frozen=True)
class CanonConstraint:
    constraint_id:str;subject:str;predicate:str;required_object_digest:str;immutable:bool=True
    def __post_init__(self):
        rid(self.constraint_id,"constraint_id");rid(self.subject,"subject");rid(self.predicate,"predicate");rdig(self.required_object_digest,"required_object_digest")
        if not isinstance(self.immutable,bool):raise ContinuityContractError("immutable must be boolean")

def verify_canon(constraints:Sequence[CanonConstraint],claims:Sequence[LoreClaim])->tuple[str,...]:
    observed={(c.subject,c.predicate):c.object_digest for c in claims}
    return tuple(sorted(c.constraint_id for c in constraints if (c.subject,c.predicate) in observed and observed[(c.subject,c.predicate)]!=c.required_object_digest))

@dataclass(frozen=True)
class StyleRule:
    rule_id:str;category:str;rule_digest:str;severity:str
    def __post_init__(self):
        rid(self.rule_id,"rule_id");rid(self.category,"category");rdig(self.rule_digest,"rule_digest")
        if self.severity not in {"advisory","required","forbidden"}:raise ContinuityContractError("invalid style severity")

class StyleBible:
    def __init__(self,rules:Sequence[StyleRule]):
        if len(rules)>MAX_RULES or len({r.rule_id for r in rules})!=len(rules):raise ContinuityContractError("invalid style rules")
        self.rules=tuple(sorted(rules,key=lambda r:r.rule_id))
    @property
    def digest(self):return dig([r.__dict__ for r in self.rules])

@dataclass(frozen=True)
class ContinuityObservation:
    observation_id:str;canon_violations:tuple[str,...];timeline_violations:tuple[str,...];style_violations:tuple[str,...];evidence_digest:str
    def __post_init__(self):
        rid(self.observation_id,"observation_id");rdig(self.evidence_digest,"evidence_digest")
        for n in ("canon_violations","timeline_violations","style_violations"):
            values=tuple(sorted(getattr(self,n)))
            if len(set(values))!=len(values):raise ContinuityContractError(f"duplicate {n}")
            for value in values:rid(value,n)
            object.__setattr__(self,n,values)
    @property
    def clean(self):return not (self.canon_violations or self.timeline_violations or self.style_violations)
    @property
    def digest(self):return dig({"id":self.observation_id,"canon":list(self.canon_violations),"timeline":list(self.timeline_violations),"style":list(self.style_violations),"evidence":self.evidence_digest})

@dataclass(frozen=True)
class GeneratedArtifact:
    artifact_id:str;content_digest:str;locked:bool=False
    def __post_init__(self):
        rid(self.artifact_id,"artifact_id");rdig(self.content_digest,"content_digest")
        if not isinstance(self.locked,bool):raise ContinuityContractError("locked must be boolean")

@dataclass(frozen=True)
class RegenerationDiff:
    added:tuple[str,...];removed:tuple[str,...];changed:tuple[str,...];preserved_locked:tuple[str,...]

def regeneration_diff(before:Sequence[GeneratedArtifact],after:Sequence[GeneratedArtifact])->RegenerationDiff:
    old={a.artifact_id:a for a in before};new={a.artifact_id:a for a in after}
    if len(old)!=len(before) or len(new)!=len(after):raise ContinuityContractError("duplicate generated artifact")
    removed=[];changed=[];preserved=[]
    for aid,artifact in old.items():
        if aid not in new:
            if artifact.locked:raise ContinuityContractError("removed locked artifact")
            removed.append(aid)
        elif new[aid].content_digest!=artifact.content_digest:
            if artifact.locked:raise ContinuityContractError("changed locked artifact")
            changed.append(aid)
        elif artifact.locked:preserved.append(aid)
    return RegenerationDiff(tuple(sorted(set(new)-set(old))),tuple(sorted(removed)),tuple(sorted(changed)),tuple(sorted(preserved)))
