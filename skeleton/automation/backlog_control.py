"""Dependency-aware, provenance-preserving backlog control for VOL-093."""
from __future__ import annotations
from dataclasses import dataclass,replace
from enum import Enum
import hashlib,json,re
from datetime import datetime,timezone
from typing import Iterable
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class BacklogError(ValueError):pass
class BacklogState(str,Enum): OPEN="open"; BLOCKED="blocked"; READY="ready"; RETIRED="retired"; CLOSED="closed"
class SourceKind(str,Enum): ISSUE="issue"; GAP="gap"; RISK="risk"; PLAN="plan"
class DispositionKind(str,Enum): KEEP="keep"; DUPLICATE="duplicate"; RETIRE="retire"; REVALIDATE="revalidate"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise BacklogError(f"{f} must be stable identifier")
 return v
def _text(v,f):
 if not isinstance(v,str) or not v.strip() or "\x00" in v:raise BacklogError(f"{f} must be safe text")
 return v.strip()
def _digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class BacklogSource:
 source_id:str;kind:SourceKind;rationale:str
 def __post_init__(self):
  object.__setattr__(self,"source_id",_id(self.source_id,"source_id"));object.__setattr__(self,"rationale",_text(self.rationale,"rationale"))
  if not isinstance(self.kind,SourceKind):raise BacklogError("kind must be SourceKind")
 @property
 def digest(self):return _digest({"source_id":self.source_id,"kind":self.kind.value,"rationale":self.rationale})

@dataclass(frozen=True,slots=True)
class BacklogDependency:
 dependency_id:str;item_id:str;depends_on:str;required_state:BacklogState=BacklogState.CLOSED
 def __post_init__(self):
  for f in ("dependency_id","item_id","depends_on"):object.__setattr__(self,f,_id(getattr(self,f),f))
  if self.item_id==self.depends_on:raise BacklogError("item cannot depend on itself")
  if not isinstance(self.required_state,BacklogState):raise BacklogError("required_state must be BacklogState")

@dataclass(frozen=True,slots=True)
class BacklogItem:
 item_id:str;title:str;owner:str;closure_rule:str;sources:tuple[BacklogSource,...];state:BacklogState=BacklogState.OPEN
 def __post_init__(self):
  object.__setattr__(self,"item_id",_id(self.item_id,"item_id"));object.__setattr__(self,"title",_text(self.title,"title"));object.__setattr__(self,"owner",_text(self.owner,"owner"));object.__setattr__(self,"closure_rule",_text(self.closure_rule,"closure_rule"))
  if not isinstance(self.state,BacklogState):raise BacklogError("state must be BacklogState")
  if not isinstance(self.sources,tuple) or any(not isinstance(s,BacklogSource) for s in self.sources):raise BacklogError("sources must be typed tuple")
  if len(self.sources)>256:raise BacklogError("source provenance exceeds policy bound")
  sources=tuple(sorted(self.sources,key=lambda s:(s.kind.value,s.source_id)))
  if not sources:raise BacklogError("backlog item requires source provenance")
  if len({(s.kind,s.source_id) for s in sources})!=len(sources):raise BacklogError("duplicate source provenance")
  object.__setattr__(self,"sources",sources)
 @property
 def fingerprint(self):return _digest({"title":" ".join(self.title.lower().split()),"closure_rule":" ".join(self.closure_rule.lower().split())})
 @property
 def digest(self):return _digest({"item_id":self.item_id,"title":self.title,"owner":self.owner,"closure_rule":self.closure_rule,"sources":[s.digest for s in self.sources],"state":self.state.value})

@dataclass(frozen=True,slots=True)
class BacklogDisposition:
 disposition_id:str;item_id:str;kind:DispositionKind;reason:str;target_item_id:str|None=None
 def __post_init__(self):
  object.__setattr__(self,"disposition_id",_id(self.disposition_id,"disposition_id"));object.__setattr__(self,"item_id",_id(self.item_id,"item_id"));object.__setattr__(self,"reason",_text(self.reason,"reason"))
  if not isinstance(self.kind,DispositionKind):raise BacklogError("kind must be DispositionKind")
  if self.target_item_id is not None:object.__setattr__(self,"target_item_id",_id(self.target_item_id,"target_item_id"))
  if self.kind is DispositionKind.DUPLICATE and not self.target_item_id:raise BacklogError("duplicate disposition requires target")
  if self.kind is not DispositionKind.DUPLICATE and self.target_item_id:raise BacklogError("only duplicate disposition may target another item")

@dataclass(frozen=True,slots=True)
class ClosureEvidence:
 evidence_id:str;item_id:str;item_digest:str;observed_at:datetime;artifact_digest:str
 def __post_init__(self):
  object.__setattr__(self,"evidence_id",_id(self.evidence_id,"evidence_id"));object.__setattr__(self,"item_id",_id(self.item_id,"item_id"))
  for f in ("item_digest","artifact_digest"):
   v=getattr(self,f)
   if not isinstance(v,str) or not re.fullmatch(r"[0-9a-f]{64}",v):raise BacklogError(f"{f} must be lowercase sha256")
  if not isinstance(self.observed_at,datetime) or self.observed_at.tzinfo is None:raise BacklogError("observed_at must be timezone-aware")
  normalized=self.observed_at.astimezone(timezone.utc)
  if normalized.microsecond:raise BacklogError("observed_at must use whole-second precision")
  object.__setattr__(self,"observed_at",normalized)

class BacklogRegistry:
 def __init__(self):self._items={};self._deps={};self._dispositions={};self._closures={}
 def add(self,item:BacklogItem):
  prior=self._items.get(item.item_id)
  if prior is not None and prior!=item:raise BacklogError("backlog identity is immutable")
  self._items[item.item_id]=item
 def add_dependency(self,dep:BacklogDependency):
  if dep.item_id not in self._items or dep.depends_on not in self._items:raise BacklogError("dependency references unknown item")
  prior=self._deps.get(dep.dependency_id)
  if prior is not None and prior!=dep:raise BacklogError("dependency identity is immutable")
  self._deps[dep.dependency_id]=dep
  self._assert_acyclic()
 def _assert_acyclic(self):
  graph={i:set() for i in self._items}
  for d in self._deps.values():graph[d.item_id].add(d.depends_on)
  visiting=set();done=set()
  def visit(n):
   if n in visiting:raise BacklogError("dependency cycle")
   if n in done:return
   visiting.add(n)
   for x in graph[n]:visit(x)
   visiting.remove(n);done.add(n)
  for n in graph:visit(n)
 def duplicates(self,item_id:str)->tuple[str,...]:
  item=self._items[item_id]
  return tuple(sorted(x.item_id for x in self._items.values() if x.item_id!=item_id and x.fingerprint==item.fingerprint))
 def deduplicate(self,canonical_id:str,duplicate_id:str,disposition_id:str,reason:str):
  canonical=self._items[canonical_id];duplicate=self._items[duplicate_id]
  if canonical.fingerprint!=duplicate.fingerprint:raise BacklogError("items are not deterministic duplicates")
  merged={(s.kind,s.source_id):s for s in canonical.sources}
  merged.update({(s.kind,s.source_id):s for s in duplicate.sources})
  self._items[canonical_id]=replace(canonical,sources=tuple(merged.values()))
  self._items[duplicate_id]=replace(duplicate,state=BacklogState.RETIRED)
  disp=BacklogDisposition(disposition_id,duplicate_id,DispositionKind.DUPLICATE,reason,canonical_id);self._dispositions[disposition_id]=disp
  return disp
 def reconcile(self,item_id:str)->BacklogItem:
  item=self._items[item_id]
  if item.state in (BacklogState.CLOSED,BacklogState.RETIRED):return item
  deps=[d for d in self._deps.values() if d.item_id==item_id]
  desired=BacklogState.READY if all(self._items[d.depends_on].state is d.required_state for d in deps) else BacklogState.BLOCKED
  updated=replace(item,state=desired);self._items[item_id]=updated;return updated
 def close(self,item_id:str,evidence:bool)->BacklogItem:
  item=self.reconcile(item_id)
  if item.state is not BacklogState.READY:raise BacklogError("blocked item cannot close")
  if not evidence:raise BacklogError("closure rule requires evidence")
  item=replace(item,state=BacklogState.CLOSED);self._items[item_id]=item;return item
 def revalidate_dependents(self,upstream_id:str)->tuple[BacklogItem,...]:
  affected=sorted({d.item_id for d in self._deps.values() if d.depends_on==upstream_id})
  return tuple(self.reconcile(i) for i in affected)
