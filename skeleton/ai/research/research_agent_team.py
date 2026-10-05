"""Governed research-agent team contracts for VOL-210."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json
from typing import Iterable

class ResearchTeamError(ValueError): pass

_ALLOWED_ROLES=frozenset({"lead","investigator","verifier","synthesizer","reproducer"})

def _token(name:str,value:object)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>256:
        raise ResearchTeamError(f"{name} must be non-empty normalized text")
    return value

def _tokens(name:str,values:Iterable[str])->tuple[str,...]:
    if isinstance(values,(str,bytes)): raise ResearchTeamError(f"{name} must be a collection")
    result=tuple(sorted({_token(name,v) for v in values}))
    if not result: raise ResearchTeamError(f"{name} must be non-empty")
    return result

def _digest(value:object)->str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ResearchRoleTemplate:
    role_id:str
    role_type:str
    capabilities:tuple[str,...]
    independent_review:bool=False
    def __post_init__(self):
        object.__setattr__(self,"role_id",_token("role_id",self.role_id))
        role=_token("role_type",self.role_type)
        if role not in _ALLOWED_ROLES: raise ResearchTeamError("unknown research role")
        object.__setattr__(self,"role_type",role)
        object.__setattr__(self,"capabilities",_tokens("capability",self.capabilities))
        if not isinstance(self.independent_review,bool): raise ResearchTeamError("independent_review must be boolean")
        if role=="verifier" and self.independent_review is not True:
            raise ResearchTeamError("verifier role must declare independent review")
    @property
    def digest(self)->str:
        return _digest({"role_id":self.role_id,"role_type":self.role_type,"capabilities":list(self.capabilities),"independent_review":self.independent_review})

@dataclass(frozen=True,slots=True)
class ResearchAssignment:
    assignment_id:str
    agent_id:str
    role:ResearchRoleTemplate
    task_scope:tuple[str,...]
    def __post_init__(self):
        object.__setattr__(self,"assignment_id",_token("assignment_id",self.assignment_id))
        object.__setattr__(self,"agent_id",_token("agent_id",self.agent_id))
        if not isinstance(self.role,ResearchRoleTemplate): raise ResearchTeamError("role must be ResearchRoleTemplate")
        object.__setattr__(self,"task_scope",_tokens("task_scope",self.task_scope))
    @property
    def digest(self)->str:
        return _digest({"assignment_id":self.assignment_id,"agent_id":self.agent_id,"role_digest":self.role.digest,"task_scope":list(self.task_scope)})

@dataclass(frozen=True,slots=True)
class ResearchTeamPlan:
    plan_id:str
    research_question:str
    assignments:tuple[ResearchAssignment,...]
    evidence_contract_id:str
    external_side_effects:bool=False
    production_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"plan_id",_token("plan_id",self.plan_id))
        object.__setattr__(self,"research_question",_token("research_question",self.research_question))
        object.__setattr__(self,"evidence_contract_id",_token("evidence_contract_id",self.evidence_contract_id))
        if not isinstance(self.assignments,tuple) or not self.assignments: raise ResearchTeamError("assignments required")
        ids=[a.assignment_id for a in self.assignments]; agents=[a.agent_id for a in self.assignments]
        if len(ids)!=len(set(ids)): raise ResearchTeamError("assignment ids must be unique")
        if len(agents)!=len(set(agents)): raise ResearchTeamError("research roles must be held by distinct agents")
        roles={a.role.role_type for a in self.assignments}
        if "investigator" not in roles or "verifier" not in roles: raise ResearchTeamError("team requires investigator and verifier")
        investigators={a.agent_id for a in self.assignments if a.role.role_type=="investigator"}
        verifiers={a.agent_id for a in self.assignments if a.role.role_type=="verifier"}
        if investigators & verifiers: raise ResearchTeamError("verifier must be independent from investigator")
        if self.external_side_effects is not False or self.production_authority is not False:
            raise ResearchTeamError("research team plan is non-authoritative evidence only")
        object.__setattr__(self,"assignments",tuple(sorted(self.assignments,key=lambda a:a.assignment_id)))
    @property
    def digest(self)->str:
        return _digest({"plan_id":self.plan_id,"research_question":self.research_question,"assignment_digests":[a.digest for a in self.assignments],"evidence_contract_id":self.evidence_contract_id,"external_side_effects":False,"production_authority":False})
