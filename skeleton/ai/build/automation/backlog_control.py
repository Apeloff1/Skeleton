"""Deterministic, provenance-preserving backlog control for VOL-093."""
from __future__ import annotations
from dataclasses import dataclass,replace
from enum import Enum
from datetime import datetime,timezone
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$"); _SHA=re.compile(r"^[0-9a-f]{64}$")
class BacklogError(ValueError): pass
class BacklogState(str,Enum): OPEN="open"; BLOCKED="blocked"; READY="ready"; RETIRED="retired"; CLOSED="closed"
class SourceKind(str,Enum): ISSUE="issue"; GAP="gap"; RISK="risk"; PLAN="plan"
class DispositionKind(str,Enum): KEEP="keep"; DUPLICATE="duplicate"; RETIRE="retire"; REVALIDATE="revalidate"
def _id(v,n):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise BacklogError(f"{n} must be stable identifier")
 return v
def _sha(v,n):
 if not isinstance(v,str) or not _SHA.fullmatch(v): raise BacklogError(f"{n} must be sha256")
 return v
def _digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class BacklogSource:
 source_id:str; kind:SourceKind; rationale:str
 def __post_init__(self):
  object.__setattr__(self,"source_id",_id(self.source_id,"source_id"))
  if not isinstance(self.kind,SourceKind) or not isinstance(self.rationale,str) or not self.rationale.strip(): raise BacklogError("invalid source")
 @property
 def digest(self): return _digest((self.source_id,self.kind.value,self.rationale.strip()))
@dataclass(frozen=True,slots=True)
class BacklogDependency:
 dependency_id:str; item_id:str; depends_on:str; required_state:BacklogState=BacklogState.CLOSED
 def __post_init__(self):
  for n in ("dependency_id","item_id","depends_on"): object.__setattr__(self,n,_id(getattr(self,n),n))
  if self.item_id==self.depends_on or not isinstance(self.required_state,BacklogState): raise BacklogError("invalid dependency")
@dataclass(frozen=True,slots=True)
class BacklogItem:
 item_id:str; title:str; owner:str; closure_rule:str; sources:tuple[BacklogSource,...]; state:BacklogState=BacklogState.OPEN
 def __post_init__(self):
  object.__setattr__(self,"item_id",_id(self.item_id,"item_id"))
  if not all(isinstance(x,str) and x.strip() for x in (self.title,self.owner,self.closure_rule)) or not isinstance(self.state,BacklogState): raise BacklogError("invalid backlog item")
  if not self.sources or not isinstance(self.sources,tuple) or any(not isinstance(x,BacklogSource) for x in self.sources): raise BacklogError("source provenance required")
  object.__setattr__(self,"sources",tuple(sorted(set(self.sources),key=lambda x:(x.kind.value,x.source_id))))
 @property
 def fingerprint(self): return _digest((" ".join(self.title.lower().split())," ".join(self.closure_rule.lower().split())))
 @property
 def digest(self): return _digest((self.item_id,self.title,self.owner,self.closure_rule,[x.digest for x in self.sources],self.state.value))
@dataclass(frozen=True,slots=True)
class BacklogDisposition:
 disposition_id:str; item_id:str; kind:DispositionKind; reason:str; target_item_id:str|None=None
@dataclass(frozen=True,slots=True)
class ClosureEvidence:
 evidence_id:str; item_id:str; item_digest:str; observed_at:datetime; artifact_digest:str
 def __post_init__(self):
  object.__setattr__(self,"evidence_id",_id(self.evidence_id,"evidence_id"));object.__setattr__(self,"item_id",_id(self.item_id,"item_id"));_sha(self.item_digest,"item_digest");_sha(self.artifact_digest,"artifact_digest")
  if self.observed_at.tzinfo is None or self.observed_at.microsecond: raise BacklogError("observed_at must be canonical")
  object.__setattr__(self,"observed_at",self.observed_at.astimezone(timezone.utc))
class BacklogRegistry:
 def __init__(self): self._items={};self._deps={};self._dispositions={};self._closures={}
 def add(self,item):
  if not isinstance(item,BacklogItem): raise BacklogError("item must be BacklogItem")
  if item.item_id in self._items and self._items[item.item_id]!=item: raise BacklogError("backlog identity is immutable")
  self._items[item.item_id]=item
 def _item(self,i):
  i=_id(i,"item_id")
  if i not in self._items: raise BacklogError("unknown backlog item")
  return self._items[i]
 def add_dependency(self,d):
  if d.item_id not in self._items or d.depends_on not in self._items: raise BacklogError("dependency references unknown item")
  self._deps[d.dependency_id]=d; self._acyclic()
 def _acyclic(self):
  graph={i:[] for i in self._items}
  for d in self._deps.values(): graph[d.item_id].append(d.depends_on)
  seen=set(); active=set()
  def visit(i):
   if i in active: raise BacklogError("dependency cycle")
   if i in seen:return
   active.add(i)
   for p in graph[i]:visit(p)
   active.remove(i);seen.add(i)
  for i in graph:visit(i)
 def duplicates(self,i):
  x=self._item(i);return tuple(sorted(y.item_id for y in self._items.values() if y.item_id!=x.item_id and y.fingerprint==x.fingerprint))
 def deduplicate(self,canonical_id,duplicate_id,disposition_id,reason):
  a=self._item(canonical_id);b=self._item(duplicate_id)
  if a.item_id==b.item_id or a.state in (BacklogState.CLOSED,BacklogState.RETIRED) or b.state in (BacklogState.CLOSED,BacklogState.RETIRED): raise BacklogError("invalid terminal/self deduplication")
  if a.fingerprint!=b.fingerprint: raise BacklogError("items are not deterministic duplicates")
  d=BacklogDisposition(disposition_id,b.item_id,DispositionKind.DUPLICATE,reason,a.item_id)
  if disposition_id in self._dispositions and self._dispositions[disposition_id]!=d: raise BacklogError("disposition identity is immutable")
  self._items[a.item_id]=replace(a,sources=tuple(set(a.sources+b.sources)));self._items[b.item_id]=replace(b,state=BacklogState.RETIRED);self._dispositions[disposition_id]=d;return d
 def reconcile(self,i):
  x=self._item(i)
  if x.state in (BacklogState.CLOSED,BacklogState.RETIRED): return x
  deps=[d for d in self._deps.values() if d.item_id==x.item_id]
  state=BacklogState.READY if all(self._items[d.depends_on].state is d.required_state for d in deps) else BacklogState.BLOCKED
  self._items[x.item_id]=replace(x,state=state);return self._items[x.item_id]
 def close(self,i,evidence):
  if not isinstance(evidence,ClosureEvidence): raise BacklogError("closure rule requires typed evidence")
  x=self.reconcile(i)
  if x.state is not BacklogState.READY: raise BacklogError("blocked item cannot close")
  if evidence.item_id!=x.item_id or evidence.item_digest!=x.digest: raise BacklogError("closure evidence is stale or bound to another item")
  self._closures[evidence.evidence_id]=evidence;self._items[x.item_id]=replace(x,state=BacklogState.CLOSED);return self._items[x.item_id]
 def revalidate_dependents(self,i):
  i=self._item(i);return tuple(self.reconcile(x) for x in sorted({d.item_id for d in self._deps.values() if d.depends_on==i.item_id}))