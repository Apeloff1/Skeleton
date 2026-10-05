"""Evidence-derived build work packages for VOL-095."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
from datetime import datetime,timezone
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA=re.compile(r"^[0-9a-f]{64}$")
class WorkPackageError(ValueError):pass
class EvidenceRole(str,Enum): IMPLEMENTATION="implementation"; VERIFICATION="verification"; COMPLETION="completion"
class PackageState(str,Enum): BLOCKED="blocked"; READY="ready"; IMPLEMENTED="implemented"; VERIFIED="verified"; COMPLETE="complete"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise WorkPackageError(f"{f} must be stable identifier")
 return v
def _txt(v,f):
 if not isinstance(v,str) or not v.strip() or "\x00" in v:raise WorkPackageError(f"{f} required")
 return v.strip()
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class WorkPackageDependency:
 dependency_id:str;package_id:str;depends_on:str
 def __post_init__(self):
  for f in ("dependency_id","package_id","depends_on"):object.__setattr__(self,f,_id(getattr(self,f),f))
  if self.package_id==self.depends_on:raise WorkPackageError("self dependency")
@dataclass(frozen=True,slots=True)
class WorkPackageEvidence:
 evidence_id:str;package_id:str;package_digest:str;role:EvidenceRole;actor_id:str;artifact_digest:str;observed_at:datetime
 def __post_init__(self):
  for f in ("evidence_id","package_id","actor_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  if not isinstance(self.role,EvidenceRole):raise WorkPackageError("role must be EvidenceRole")
  for f in ("package_digest","artifact_digest"):
   if not isinstance(getattr(self,f),str) or not _SHA.fullmatch(getattr(self,f)):raise WorkPackageError(f"{f} must be sha256")
  if not isinstance(self.observed_at,datetime) or self.observed_at.tzinfo is None:raise WorkPackageError("observed_at must be timezone-aware")
  normalized=self.observed_at.astimezone(timezone.utc)
  if normalized.microsecond:raise WorkPackageError("observed_at must use whole-second precision")
  object.__setattr__(self,"observed_at",normalized)
@dataclass(frozen=True,slots=True)
class WorkPackage:
 package_id:str;volume_id:str;objective:str;non_goals:tuple[str,...];interfaces:tuple[str,...];state_owners:tuple[str,...];risks:tuple[str,...];tests:tuple[str,...];rollback:str;requirement_ids:tuple[str,...];aiq_task_ids:tuple[str,...]
 def __post_init__(self):
  for f in ("package_id","volume_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  object.__setattr__(self,"objective",_txt(self.objective,"objective"));object.__setattr__(self,"rollback",_txt(self.rollback,"rollback"))
  for f in ("non_goals","interfaces","state_owners","risks","tests","requirement_ids","aiq_task_ids"):
   raw=getattr(self,f)
   if not isinstance(raw,tuple):raise WorkPackageError(f"{f} must be tuple")
   if len(raw)>256:raise WorkPackageError(f"{f} exceeds policy bound")
   normalize=_id if f in ("requirement_ids","aiq_task_ids") else _txt
   vals=tuple(normalize(v,f) for v in raw)
   if not vals:raise WorkPackageError(f"{f} cannot be empty")
   if len(vals)!=len(set(vals)):raise WorkPackageError(f"{f} contains duplicate values")
   object.__setattr__(self,f,tuple(sorted(vals)))
 @property
 def digest(self):return _dig({"package_id":self.package_id,"volume_id":self.volume_id,"objective":self.objective,"non_goals":self.non_goals,"interfaces":self.interfaces,"state_owners":self.state_owners,"risks":self.risks,"tests":self.tests,"rollback":self.rollback,"requirement_ids":self.requirement_ids,"aiq_task_ids":self.aiq_task_ids})
class WorkPackageRegistry:
 def __init__(self):self.packages={};self.dependencies={};self.evidence={}
 def add(self,p):
  if not isinstance(p,WorkPackage):raise WorkPackageError("package must be WorkPackage")
  prior=self.packages.get(p.package_id)
  if prior is not None and prior!=p:raise WorkPackageError("package identity immutable")
  self.packages[p.package_id]=p
 def depend(self,d):
  if not isinstance(d,WorkPackageDependency):raise WorkPackageError("dependency must be WorkPackageDependency")
  if d.package_id not in self.packages or d.depends_on not in self.packages:raise WorkPackageError("unknown package dependency")
  prior=self.dependencies.get(d.dependency_id)
  if prior is not None and prior!=d:raise WorkPackageError("dependency identity immutable")
  if any(x.dependency_id!=d.dependency_id and x.package_id==d.package_id and x.depends_on==d.depends_on for x in self.dependencies.values()):raise WorkPackageError("duplicate dependency edge")
  self.dependencies[d.dependency_id]=d
  try:self._acyclic()
  except Exception:
   if prior is None:self.dependencies.pop(d.dependency_id,None)
   else:self.dependencies[d.dependency_id]=prior
   raise
 def _acyclic(self):
  g={k:set() for k in self.packages}
  for d in self.dependencies.values():g[d.package_id].add(d.depends_on)
  seen=set();stack=set()
  def visit(n):
   if n in stack:raise WorkPackageError("dependency cycle")
   if n in seen:return
   stack.add(n)
   for x in g[n]:visit(x)
   stack.remove(n);seen.add(n)
  for n in g:visit(n)
 def attest(self,e):
  if not isinstance(e,WorkPackageEvidence):raise WorkPackageError("evidence must be WorkPackageEvidence")
  if e.evidence_id not in self.evidence and len(self.evidence)>=4096:raise WorkPackageError("evidence registry exceeds policy bound")
  if e.package_id not in self.packages:raise WorkPackageError("evidence references unknown package")
  if e.package_digest!=self.packages[e.package_id].digest:raise WorkPackageError("evidence is stale or bound to another package version")
  same=[x for x in self.evidence.values() if x.package_id==e.package_id and x.package_digest==e.package_digest and x.role is e.role]
  if any(x.actor_id==e.actor_id and x.artifact_digest!=e.artifact_digest for x in same):raise WorkPackageError("actor cannot contradict evidence for same package role")
  prior=self.evidence.get(e.evidence_id)
  if prior is not None and prior!=e:raise WorkPackageError("evidence identity immutable")
  self.evidence[e.evidence_id]=e
 def state(self,pid):
  if pid not in self.packages:raise WorkPackageError("unknown package")
  deps=[d.depends_on for d in self.dependencies.values() if d.package_id==pid]
  if any(self.state(d) is not PackageState.COMPLETE for d in deps):return PackageState.BLOCKED
  ev=[e for e in self.evidence.values() if e.package_id==pid];roles={e.role for e in ev}
  if EvidenceRole.IMPLEMENTATION not in roles:return PackageState.READY
  if EvidenceRole.VERIFICATION not in roles:return PackageState.IMPLEMENTED
  implementation=[e for e in ev if e.role is EvidenceRole.IMPLEMENTATION]
  verification=[e for e in ev if e.role is EvidenceRole.VERIFICATION]
  impl={e.actor_id for e in implementation};verify={e.actor_id for e in verification}
  if impl & verify:raise WorkPackageError("verification must be independent from implementation")
  latest_implementation=max(e.observed_at for e in implementation)
  latest_verification=max(e.observed_at for e in verification)
  if latest_verification < latest_implementation:return PackageState.IMPLEMENTED
  if EvidenceRole.COMPLETION not in roles:return PackageState.VERIFIED
  completion=[e for e in ev if e.role is EvidenceRole.COMPLETION]
  complete={e.actor_id for e in completion}
  if complete & impl:raise WorkPackageError("completion signer cannot be implementation actor")
  if complete & verify:raise WorkPackageError("completion signer cannot be verification actor")
  latest_completion=max(e.observed_at for e in completion)
  if latest_completion < latest_verification:return PackageState.VERIFIED
  return PackageState.COMPLETE

 def evidence_rollup(self,pid):
  state=self.state(pid)
  p=self.packages[pid]
  ev=tuple(sorted((e for e in self.evidence.values() if e.package_id==pid),key=lambda x:(x.role.value,x.evidence_id)))
  return {"package_id":pid,"package_digest":p.digest,"state":state.value,"evidence_ids":tuple(e.evidence_id for e in ev),"artifact_digests":tuple(e.artifact_digest for e in ev),"observed_at_utc":tuple(e.observed_at.isoformat() for e in ev)}
