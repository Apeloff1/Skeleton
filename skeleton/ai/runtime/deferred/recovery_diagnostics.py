"""Recovery and diagnostic safety contracts for VOL-278..282."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .contracts import sha256_json

def _t(v:object,n:str)->str:
 if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} must be non-empty text")
 return v.strip()
def _d(v:object,n:str)->str:
 v=_t(v,n)
 if len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ValueError(f"{n} must be lowercase sha256")
 return v

@dataclass(frozen=True,slots=True)
class RecoveryArtifact:
 artifact_id:str; expected_digest:str; observed_digest:str; signature_verified:bool
 def __post_init__(self):
  _t(self.artifact_id,"artifact_id");_d(self.expected_digest,"expected_digest");_d(self.observed_digest,"observed_digest")
 @property
 def valid(self)->bool: return self.signature_verified and self.expected_digest==self.observed_digest
@dataclass(frozen=True,slots=True)
class BootstrapRecovery:
 recovery_id:str; artifacts:tuple[RecoveryArtifact,...]; dependency_count:int
 def __post_init__(self):
  _t(self.recovery_id,"recovery_id")
  if self.dependency_count<0: raise ValueError("dependency_count must be non-negative")
  if len({a.artifact_id for a in self.artifacts})!=len(self.artifacts):raise ValueError("duplicate recovery artifact")
  if not self.artifacts: raise ValueError("recovery requires artifacts")
@dataclass(frozen=True,slots=True)
class BootstrapReceipt: recovery_id:str; validated:bool; handoff_allowed:bool
def validate_recovery(r:BootstrapRecovery,normal_dependency_count:int)->BootstrapReceipt:
 if normal_dependency_count<0:raise ValueError("normal_dependency_count must be non-negative")
 valid=r.dependency_count<normal_dependency_count and all(a.valid for a in r.artifacts)
 return BootstrapReceipt(r.recovery_id,valid,valid)

@dataclass(frozen=True,slots=True)
class CrashContext:
 component:str; correlation_id:str; fields:tuple[tuple[str,str],...]
@dataclass(frozen=True,slots=True)
class CrashSignature:
 exception_type:str; stack_digest:str
@dataclass(frozen=True,slots=True)
class CrashReport:
 context:CrashContext; signature:CrashSignature; telemetry_available:bool; redacted:bool
 def __post_init__(self):
  _t(self.context.component,"component");_t(self.context.correlation_id,"correlation_id");_t(self.signature.exception_type,"exception_type");_d(self.signature.stack_digest,"stack_digest")
  if len({k for k,_ in self.context.fields})!=len(self.context.fields) or any(not k for k,_ in self.context.fields):raise ValueError("unique crash context fields required")
  if not self.redacted: raise ValueError("crash report must be redacted before export")
 @property
 def identity(self)->str: return sha256_json({"component":self.context.component,"correlation":self.context.correlation_id,"exception":self.signature.exception_type,"stack":self.signature.stack_digest})

@dataclass(frozen=True,slots=True)
class SupportRedaction:
 secret_keys:tuple[str,...]
@dataclass(frozen=True,slots=True)
class SupportManifest:
 allowed_paths:tuple[str,...]; item_digests:tuple[tuple[str,str],...]; expires_at:str
@dataclass(frozen=True,slots=True)
class SupportBundle:
 manifest:SupportManifest; items:tuple[tuple[str,str],...]; redaction:SupportRedaction
 def __post_init__(self):
  if not self.manifest.expires_at or len(set(self.manifest.allowed_paths))!=len(self.manifest.allowed_paths) or any(not p for p in self.manifest.allowed_paths):raise ValueError("invalid support manifest")
  if len({p for p,_ in self.manifest.item_digests})!=len(self.manifest.item_digests) or len({p for p,_ in self.items})!=len(self.items):raise ValueError("duplicate support path")
  if any(not s for s in self.redaction.secret_keys):raise ValueError("invalid redaction key")
  allowed=set(self.manifest.allowed_paths)
  if any(p not in allowed for p,_ in self.items): raise ValueError("support bundle contains non-allowlisted path")
  expected=dict(self.manifest.item_digests)
  if any(expected.get(p)!=sha256_json({"content":c}) for p,c in self.items): raise ValueError("support bundle digest mismatch")
  for _,content in self.items:
   if any(secret in content for secret in self.redaction.secret_keys): raise ValueError("support bundle contains declared secret")

class FindingState(str,Enum): HEALTHY="healthy"; DEGRADED="degraded"; BROKEN="broken"; UNKNOWN="unknown"
@dataclass(frozen=True,slots=True)
class DoctorCheck: check_id:str; component:str
@dataclass(frozen=True,slots=True)
class DoctorFinding:
 check:DoctorCheck; state:FindingState; evidence_digest:str; recommendation:str
 def __post_init__(self):
  _t(self.check.check_id,"check_id");_t(self.check.component,"component");_d(self.evidence_digest,"evidence_digest");_t(self.recommendation,"recommendation")
@dataclass(frozen=True,slots=True)
class DoctorReport:
 findings:tuple[DoctorFinding,...]; machine_readable:bool=True
 @property
 def healthy(self)->bool: return bool(self.findings) and all(f.state is FindingState.HEALTHY for f in self.findings)
@dataclass(frozen=True,slots=True)
class RepairRequest:
 finding:DoctorFinding; authorization_receipt:str
 def __post_init__(self):
  if not self.authorization_receipt.strip(): raise ValueError("repair requires separate authorization")

@dataclass(frozen=True,slots=True)
class HealthEvidence:
 component:str; internal_state:FindingState; external_state:FindingState|None; evidence_digest:str
 def __post_init__(self):
  _t(self.component,"component");_d(self.evidence_digest,"evidence_digest")
@dataclass(frozen=True,slots=True)
class FaultHypothesis:
 component:str; statement:str; evidence_digest:str; confidence:float
 def __post_init__(self):
  _t(self.component,"component");_t(self.statement,"statement");_d(self.evidence_digest,"evidence_digest")
  if not 0<=self.confidence<=1: raise ValueError("confidence must be in [0,1]")
@dataclass(frozen=True,slots=True)
class SelfDiagnostic:
 evidence:tuple[HealthEvidence,...]; hypotheses:tuple[FaultHypothesis,...]
 @property
 def advisory_health(self)->FindingState:
  if not self.evidence: return FindingState.UNKNOWN
  if any(e.external_state is None for e in self.evidence): return FindingState.UNKNOWN
  states={e.internal_state for e in self.evidence}|{e.external_state for e in self.evidence if e.external_state}
  if FindingState.BROKEN in states:return FindingState.BROKEN
  if FindingState.DEGRADED in states:return FindingState.DEGRADED
  return FindingState.HEALTHY
 @property
 def production_certified(self)->bool: return False
