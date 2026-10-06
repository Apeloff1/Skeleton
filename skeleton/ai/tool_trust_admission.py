"""Fail-closed admission from discovered capability to trusted tool result."""
from dataclasses import dataclass
import hashlib,json
from skeleton.ai.tool_discovery import ToolDiscoveryResult
from skeleton.security.tool_result_trust import ToolResultTrust,validate_result

@dataclass(frozen=True)
class TrustedToolAdmission:
 tool_id:str; capability:str; manifest_digest:str; result_digest:str; admission_digest:str

def _sha(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def admit_tool_result(discovery:ToolDiscoveryResult,capability:str,trust:ToolResultTrust,result_digest:str,*,high_impact:bool,now:int,max_age:int):
 if not discovery.validated: raise PermissionError("unvalidated tool discovery")
 if discovery.granted_authority: raise PermissionError("discovery cannot grant authority")
 if capability not in {c.name for c in discovery.manifest.capabilities}: raise PermissionError("capability not attested")
 if len(result_digest)!=64 or any(c not in "0123456789abcdef" for c in result_digest): raise ValueError("result_digest must be sha256")
 validation=validate_result(trust,high_impact=high_impact,now=now,max_age=max_age)
 if not validation.valid: raise PermissionError(validation.reason)
 m=discovery.manifest
 manifest=_sha({"tool_id":m.tool_id,"capabilities":[(c.name,c.schema) for c in m.capabilities],"attestation":None if m.attestation is None else (m.attestation.signer,m.attestation.digest,m.attestation.trusted)})
 body={"tool_id":m.tool_id,"capability":capability,"manifest_digest":manifest,"result_digest":result_digest,"sources":[(e.source,e.observed_at,e.independent) for e in trust.provenance]}
 return TrustedToolAdmission(m.tool_id,capability,manifest,result_digest,_sha(body))
