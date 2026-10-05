"""Fail-closed repository maintenance contracts for VOL-092."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
from typing import Iterable

_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA=re.compile(r"^[0-9a-f]{64}$")
class MaintenanceError(ValueError): pass
class MaintenanceRisk(str,Enum): LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"
class ResourceKind(str,Enum): BRANCH="branch"; FILE="file"; DEPENDENCY="dependency"; ARTIFACT="artifact"
class OwnershipClass(str,Enum): ACTIVE="active"; MIGRATION="migration"; GENERATED="generated"; RELEASE="release"; EVIDENCE="evidence"; UNOWNED="unowned"
class MaintenanceAction(str,Enum): INSPECT="inspect"; UPDATE="update"; DELETE="delete"
class MaintenanceDecision(str,Enum): ALLOW="allow"; BLOCK="block"

def _id(v,f):
    if not isinstance(v,str) or not _ID.fullmatch(v): raise MaintenanceError(f"{f} must be stable identifier")
    return v
def _text(v,f):
    if not isinstance(v,str) or not v.strip() or "\x00" in v: raise MaintenanceError(f"{f} must be safe text")
    return v.strip()
def _sha(v,f):
    if not isinstance(v,str) or not _SHA.fullmatch(v): raise MaintenanceError(f"{f} must be lowercase sha256")
    return v
def _digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class RepositoryOwnership:
    resource_id:str; kind:ResourceKind; ownership:OwnershipClass; owner:str
    retention_reason:str; active_refs:tuple[str,...]=()
    def __post_init__(self):
        object.__setattr__(self,"resource_id",_id(self.resource_id,"resource_id"));object.__setattr__(self,"owner",_text(self.owner,"owner"));object.__setattr__(self,"retention_reason",_text(self.retention_reason,"retention_reason"))
        if not isinstance(self.kind,ResourceKind): raise MaintenanceError("kind must be ResourceKind")
        if not isinstance(self.ownership,OwnershipClass): raise MaintenanceError("ownership must be OwnershipClass")
        refs=tuple(sorted(set(self.active_refs)))
        for r in refs:_id(r,"active_ref")
        object.__setattr__(self,"active_refs",refs)
        if self.ownership is OwnershipClass.UNOWNED and refs: raise MaintenanceError("unowned resource cannot claim active references")
    @property
    def digest(self):return _digest({"resource_id":self.resource_id,"kind":self.kind.value,"ownership":self.ownership.value,"owner":self.owner,"retention_reason":self.retention_reason,"active_refs":self.active_refs})

@dataclass(frozen=True,slots=True)
class ResourceEvidence:
    evidence_id:str; resource_id:str; observed_digest:str
    reachable:bool; retention_satisfied:bool; active_migration:bool; release_bound:bool; evidence_bound:bool
    def __post_init__(self):
        object.__setattr__(self,"evidence_id",_id(self.evidence_id,"evidence_id"));object.__setattr__(self,"resource_id",_id(self.resource_id,"resource_id"));object.__setattr__(self,"observed_digest",_sha(self.observed_digest,"observed_digest"))
        for f in ("reachable","retention_satisfied","active_migration","release_bound","evidence_bound"):
            if not isinstance(getattr(self,f),bool): raise MaintenanceError(f"{f} must be bool")
    @property
    def digest(self):return _digest({"evidence_id":self.evidence_id,"resource_id":self.resource_id,"observed_digest":self.observed_digest,"reachable":self.reachable,"retention_satisfied":self.retention_satisfied,"active_migration":self.active_migration,"release_bound":self.release_bound,"evidence_bound":self.evidence_bound})

@dataclass(frozen=True,slots=True)
class MaintenanceTask:
    task_id:str; resource_id:str; action:MaintenanceAction; risk:MaintenanceRisk; expected_digest:str; mutation_limit:int
    def __post_init__(self):
        object.__setattr__(self,"task_id",_id(self.task_id,"task_id"));object.__setattr__(self,"resource_id",_id(self.resource_id,"resource_id"));object.__setattr__(self,"expected_digest",_sha(self.expected_digest,"expected_digest"))
        if not isinstance(self.action,MaintenanceAction): raise MaintenanceError("action must be MaintenanceAction")
        if not isinstance(self.risk,MaintenanceRisk): raise MaintenanceError("risk must be MaintenanceRisk")
        if not isinstance(self.mutation_limit,int) or isinstance(self.mutation_limit,bool) or not 1<=self.mutation_limit<=100: raise MaintenanceError("mutation_limit must be bounded 1..100")
        if self.action is MaintenanceAction.DELETE and self.risk in (MaintenanceRisk.LOW,MaintenanceRisk.MEDIUM): raise MaintenanceError("deletion cannot be classified below high risk")
    @property
    def digest(self):return _digest({"task_id":self.task_id,"resource_id":self.resource_id,"action":self.action.value,"risk":self.risk.value,"expected_digest":self.expected_digest,"mutation_limit":self.mutation_limit})

@dataclass(frozen=True,slots=True)
class MaintenanceReceipt:
    task_digest:str; ownership_digest:str; evidence_digest:str|None; decision:MaintenanceDecision; reasons:tuple[str,...]
    def __post_init__(self):
        _sha(self.task_digest,"task_digest");_sha(self.ownership_digest,"ownership_digest")
        if self.evidence_digest is not None:_sha(self.evidence_digest,"evidence_digest")
        object.__setattr__(self,"reasons",tuple(sorted(set(self.reasons))))
        if self.decision is MaintenanceDecision.ALLOW and self.reasons: raise MaintenanceError("allowed receipt cannot contain blockers")
    @property
    def digest(self):return _digest({"task_digest":self.task_digest,"ownership_digest":self.ownership_digest,"evidence_digest":self.evidence_digest,"decision":self.decision.value,"reasons":self.reasons})

def authorize(task:MaintenanceTask, ownership:RepositoryOwnership, evidence:ResourceEvidence|None=None)->MaintenanceReceipt:
    if task.resource_id!=ownership.resource_id: raise MaintenanceError("task/ownership resource mismatch")
    reasons=[]
    mutating=task.action in (MaintenanceAction.UPDATE,MaintenanceAction.DELETE)
    if mutating:
        if evidence is None: reasons.append("missing_resource_evidence")
        else:
            if evidence.resource_id!=task.resource_id: raise MaintenanceError("resource evidence mismatch")
            if evidence.observed_digest!=task.expected_digest: reasons.append("resource_changed_since_observation")
    if task.action is MaintenanceAction.DELETE:
        if evidence is not None:
            if evidence.reachable: reasons.append("resource_reachable")
            if not evidence.retention_satisfied: reasons.append("retention_not_satisfied")
            if evidence.active_migration: reasons.append("active_migration")
            if evidence.release_bound: reasons.append("release_bound")
            if evidence.evidence_bound: reasons.append("evidence_bound")
        if ownership.ownership in (OwnershipClass.ACTIVE,OwnershipClass.MIGRATION,OwnershipClass.RELEASE,OwnershipClass.EVIDENCE): reasons.append(f"protected_ownership:{ownership.ownership.value}")
        if ownership.active_refs: reasons.append("active_references")
    decision=MaintenanceDecision.BLOCK if reasons else MaintenanceDecision.ALLOW
    return MaintenanceReceipt(task.digest,ownership.digest,evidence.digest if evidence else None,decision,tuple(reasons))
