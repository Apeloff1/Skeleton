"""Desktop install/update/rollback continuity contracts for VOL-103."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_SHA=re.compile(r"^[0-9a-f]{64}$");_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class DesktopReleaseError(ValueError):pass
class UpdateState(str,Enum): STAGED="staged"; MIGRATED="migrated"; COMMITTED="committed"; ROLLED_BACK="rolled_back"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise DesktopReleaseError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise DesktopReleaseError(f"{f} must be sha256")
 return v
@dataclass(frozen=True,slots=True)
class SignedDesktopRelease:
 release_id:str;artifact_digest:str;signature_digest:str;signer_id:str;schema_version:int
 def __post_init__(self):
  for f in ("release_id","signer_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.artifact_digest,"artifact_digest");_sha(self.signature_digest,"signature_digest")
  if not isinstance(self.schema_version,int) or isinstance(self.schema_version,bool) or self.schema_version<1:raise DesktopReleaseError("schema_version invalid")
@dataclass(frozen=True,slots=True)
class DesktopAcceptanceRun:
 run_id:str;release_id:str;environment_digest:str;vs001_evidence_digest:str;governed_artifact_digest:str
 def __post_init__(self):
  for f in ("run_id","release_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  for f in ("environment_digest","vs001_evidence_digest","governed_artifact_digest"):_sha(getattr(self,f),f)
@dataclass(frozen=True,slots=True)
class DesktopArtifactReceipt:
 release_id:str;authoritative_state_digest:str;artifact_digest:str;schema_version:int
 def __post_init__(self):
  object.__setattr__(self,"release_id",_id(self.release_id,"release_id"));_sha(self.authoritative_state_digest,"authoritative_state_digest");_sha(self.artifact_digest,"artifact_digest")
  if not isinstance(self.schema_version,int) or isinstance(self.schema_version,bool) or self.schema_version<1:raise DesktopReleaseError("schema_version invalid")
@dataclass(frozen=True,slots=True)
class DesktopRollbackEvidence:
 from_release_id:str;to_release_id:str;preupdate_state_digest:str;restored_state_digest:str;rollback_artifact_digest:str
 def __post_init__(self):
  for f in ("from_release_id","to_release_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  for f in ("preupdate_state_digest","restored_state_digest","rollback_artifact_digest"):_sha(getattr(self,f),f)
  if self.preupdate_state_digest!=self.restored_state_digest:raise DesktopReleaseError("rollback did not restore authoritative state")
class DesktopUpdateTransaction:
 def __init__(self,current:SignedDesktopRelease,receipt:DesktopArtifactReceipt):
  if current.release_id!=receipt.release_id or current.schema_version!=receipt.schema_version:raise DesktopReleaseError("release/receipt mismatch")
  self.current=current;self.receipt=receipt;self.target=None;self.state=None;self.preupdate_digest=None;self.preupdate_receipt=receipt
 def stage(self,target:SignedDesktopRelease):
  if self.state in (UpdateState.STAGED,UpdateState.MIGRATED):raise DesktopReleaseError("update already in progress")
  if target.release_id==self.current.release_id:raise DesktopReleaseError("target release must differ")
  self.target=target;self.preupdate_digest=self.receipt.authoritative_state_digest;self.preupdate_receipt=self.receipt;self.state=UpdateState.STAGED
 def migrate(self,migrated_state_digest:str):
  if self.state is not UpdateState.STAGED:raise DesktopReleaseError("update not staged")
  _sha(migrated_state_digest,"migrated_state_digest");self.receipt=DesktopArtifactReceipt(self.target.release_id,migrated_state_digest,self.target.artifact_digest,self.target.schema_version);self.state=UpdateState.MIGRATED
 def commit(self,acceptance:DesktopAcceptanceRun):
  if self.state is not UpdateState.MIGRATED:raise DesktopReleaseError("migration not complete")
  if not isinstance(acceptance,DesktopAcceptanceRun):raise DesktopReleaseError("acceptance must be DesktopAcceptanceRun")
  if acceptance.release_id!=self.target.release_id:raise DesktopReleaseError("acceptance targets wrong release")
  if acceptance.governed_artifact_digest!=self.target.artifact_digest:raise DesktopReleaseError("acceptance artifact does not match signed target")
  self.current=self.target;self.state=UpdateState.COMMITTED;self.target=None;self.preupdate_digest=None;return self.receipt
 def interrupt(self):
  if self.state not in (UpdateState.STAGED,UpdateState.MIGRATED):raise DesktopReleaseError("no interruptible update")
  return "rollback_required"
 def rollback(self,artifact_digest:str):
  if self.preupdate_digest is None or self.state not in (UpdateState.STAGED,UpdateState.MIGRATED):raise DesktopReleaseError("no rollback-eligible update")
  _sha(artifact_digest,"artifact_digest")
  target_id=self.target.release_id if self.target else self.current.release_id
  evidence=DesktopRollbackEvidence(target_id,self.current.release_id,self.preupdate_digest,self.preupdate_digest,artifact_digest)
  self.receipt=self.preupdate_receipt;self.state=UpdateState.ROLLED_BACK;return evidence
