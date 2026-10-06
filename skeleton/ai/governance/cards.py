"""Evidence-bound governance cards for VOL-221..VOL-224.

Cards are immutable machine artifacts derived from exact source/evidence
identities. They describe capabilities and limitations; they never grant
promotion or execution authority.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from typing import Iterable

class GovernanceCardError(ValueError): pass

def _token(name:str,value:object,max_len:int=1024)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>max_len:
        raise GovernanceCardError(f"{name} must be non-empty normalized text")
    return value

def _sha(name:str,value:object)->str:
    if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
        raise GovernanceCardError(f"{name} must be lowercase sha256")
    return value

def _git_sha(value:object)->str:
    if not isinstance(value,str) or len(value)!=40 or any(ch not in "0123456789abcdef" for ch in value):
        raise GovernanceCardError("source_revision must be a 40-character lowercase Git SHA")
    return value

def _tokens(name:str,values:Iterable[str],*,allow_empty:bool=False)->tuple[str,...]:
    if isinstance(values,(str,bytes)): raise GovernanceCardError(f"{name} must be a collection")
    out=tuple(sorted({_token(name,v,256) for v in values}))
    if not out and not allow_empty: raise GovernanceCardError(f"{name} must be non-empty")
    return out

def _digest(value:object)->str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ModelCard:
    card_id:str
    model_id:str
    source_revision:str
    model_bom_digest:str
    evaluation_digest:str
    intended_uses:tuple[str,...]
    prohibited_uses:tuple[str,...]
    limitations:tuple[str,...]
    promotion_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"card_id",_token("card_id",self.card_id,256))
        object.__setattr__(self,"model_id",_token("model_id",self.model_id,256))
        object.__setattr__(self,"source_revision",_git_sha(self.source_revision))
        object.__setattr__(self,"model_bom_digest",_sha("model_bom_digest",self.model_bom_digest))
        object.__setattr__(self,"evaluation_digest",_sha("evaluation_digest",self.evaluation_digest))
        object.__setattr__(self,"intended_uses",_tokens("intended_use",self.intended_uses))
        object.__setattr__(self,"prohibited_uses",_tokens("prohibited_use",self.prohibited_uses))
        object.__setattr__(self,"limitations",_tokens("limitation",self.limitations))
        if set(self.intended_uses)&set(self.prohibited_uses): raise GovernanceCardError("intended and prohibited uses must be disjoint")
        if self.promotion_authority is not False: raise GovernanceCardError("model card cannot grant promotion authority")
    @property
    def digest(self)->str:
        return _digest({"kind":"model","card_id":self.card_id,"model_id":self.model_id,"source_revision":self.source_revision,"model_bom_digest":self.model_bom_digest,"evaluation_digest":self.evaluation_digest,"intended_uses":list(self.intended_uses),"prohibited_uses":list(self.prohibited_uses),"limitations":list(self.limitations),"promotion_authority":False})

@dataclass(frozen=True,slots=True)
class DatasetCard:
    card_id:str
    dataset_id:str
    source_revision:str
    registry_digest:str
    lineage_digest:str
    license_id:str
    allowed_uses:tuple[str,...]
    sensitive_categories:tuple[str,...]=()
    deletion_policy_id:str="default"
    promotion_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"card_id",_token("card_id",self.card_id,256)); object.__setattr__(self,"dataset_id",_token("dataset_id",self.dataset_id,256))
        object.__setattr__(self,"source_revision",_git_sha(self.source_revision)); object.__setattr__(self,"registry_digest",_sha("registry_digest",self.registry_digest)); object.__setattr__(self,"lineage_digest",_sha("lineage_digest",self.lineage_digest))
        object.__setattr__(self,"license_id",_token("license_id",self.license_id,256)); object.__setattr__(self,"allowed_uses",_tokens("allowed_use",self.allowed_uses))
        object.__setattr__(self,"sensitive_categories",_tokens("sensitive_category",self.sensitive_categories,allow_empty=True)); object.__setattr__(self,"deletion_policy_id",_token("deletion_policy_id",self.deletion_policy_id,256))
        if self.promotion_authority is not False: raise GovernanceCardError("dataset card cannot grant promotion authority")
    @property
    def digest(self)->str:
        return _digest({"kind":"dataset","card_id":self.card_id,"dataset_id":self.dataset_id,"source_revision":self.source_revision,"registry_digest":self.registry_digest,"lineage_digest":self.lineage_digest,"license_id":self.license_id,"allowed_uses":list(self.allowed_uses),"sensitive_categories":list(self.sensitive_categories),"deletion_policy_id":self.deletion_policy_id,"promotion_authority":False})

@dataclass(frozen=True,slots=True)
class ToolCard:
    card_id:str
    tool_id:str
    source_revision:str
    tool_definition_digest:str
    security_review_digest:str
    capability_scopes:tuple[str,...]
    side_effect_class:str
    approval_required:bool
    promotion_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"card_id",_token("card_id",self.card_id,256)); object.__setattr__(self,"tool_id",_token("tool_id",self.tool_id,256)); object.__setattr__(self,"source_revision",_git_sha(self.source_revision))
        object.__setattr__(self,"tool_definition_digest",_sha("tool_definition_digest",self.tool_definition_digest)); object.__setattr__(self,"security_review_digest",_sha("security_review_digest",self.security_review_digest))
        object.__setattr__(self,"capability_scopes",_tokens("capability_scope",self.capability_scopes))
        side=_token("side_effect_class",self.side_effect_class,64)
        if side not in {"none","read","write","privileged"}: raise GovernanceCardError("unknown side_effect_class")
        object.__setattr__(self,"side_effect_class",side)
        if not isinstance(self.approval_required,bool): raise GovernanceCardError("approval_required must be boolean")
        if side=="privileged" and not self.approval_required: raise GovernanceCardError("privileged tool requires approval")
        if self.promotion_authority is not False: raise GovernanceCardError("tool card cannot grant promotion authority")
    @property
    def digest(self)->str:
        return _digest({"kind":"tool","card_id":self.card_id,"tool_id":self.tool_id,"source_revision":self.source_revision,"tool_definition_digest":self.tool_definition_digest,"security_review_digest":self.security_review_digest,"capability_scopes":list(self.capability_scopes),"side_effect_class":self.side_effect_class,"approval_required":self.approval_required,"promotion_authority":False})

@dataclass(frozen=True,slots=True)
class AgentCard:
    card_id:str
    agent_id:str
    source_revision:str
    registry_digest:str
    performance_evidence_digest:str
    authority_boundary_digest:str
    human_control_receipt_digest:str
    capability_scopes:tuple[str,...]
    autonomous_side_effects:bool=False
    promotion_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"card_id",_token("card_id",self.card_id,256)); object.__setattr__(self,"agent_id",_token("agent_id",self.agent_id,256)); object.__setattr__(self,"source_revision",_git_sha(self.source_revision))
        for name in ("registry_digest","performance_evidence_digest","authority_boundary_digest","human_control_receipt_digest"): object.__setattr__(self,name,_sha(name,getattr(self,name)))
        object.__setattr__(self,"capability_scopes",_tokens("capability_scope",self.capability_scopes))
        if self.autonomous_side_effects is not False: raise GovernanceCardError("agent card cannot authorize autonomous side effects")
        if self.promotion_authority is not False: raise GovernanceCardError("agent card cannot grant promotion authority")
    @property
    def digest(self)->str:
        return _digest({"kind":"agent","card_id":self.card_id,"agent_id":self.agent_id,"source_revision":self.source_revision,"registry_digest":self.registry_digest,"performance_evidence_digest":self.performance_evidence_digest,"authority_boundary_digest":self.authority_boundary_digest,"human_control_receipt_digest":self.human_control_receipt_digest,"capability_scopes":list(self.capability_scopes),"autonomous_side_effects":False,"promotion_authority":False})
