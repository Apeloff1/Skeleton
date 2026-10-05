"""Executable unified threat-model coverage contracts for VOL-026."""
from dataclasses import dataclass
from hashlib import sha256
import json
from .contracts import SecurityContractError
_REQUIRED=frozenset({"tool-authority","secrets","filesystem","network-egress","supply-chain"})
@dataclass(frozen=True,slots=True)
class Threat:
 threat_id:str;asset:str;boundary:str;mitigation:str;validation:str
 def __post_init__(self):
  for n in ("threat_id","asset","boundary","mitigation","validation"):
   v=getattr(self,n)
   if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512:raise SecurityContractError(f"invalid {n}")
@dataclass(frozen=True,slots=True)
class ThreatModel:
 threats:tuple[Threat,...];model_version:str="vol026-v1"
 def __post_init__(self):
  if not isinstance(self.threats,tuple) or not self.threats:raise SecurityContractError("threats required")
  ids=[t.threat_id for t in self.threats]
  if len(ids)!=len(set(ids)):raise SecurityContractError("duplicate threat id")
  assets={t.asset for t in self.threats}
  missing=_REQUIRED-assets
  if missing:raise SecurityContractError("missing required threat coverage: "+",".join(sorted(missing)))
  object.__setattr__(self,"threats",tuple(sorted(self.threats,key=lambda t:t.threat_id)))
 @property
 def digest(self):
  return sha256(json.dumps({"version":self.model_version,"threats":[{"id":t.threat_id,"asset":t.asset,"boundary":t.boundary,"mitigation":t.mitigation,"validation":t.validation} for t in self.threats]},sort_keys=True,separators=(",",":")).encode()).hexdigest()
def canonical_vol026_threat_model()->ThreatModel:
 return ThreatModel((
  Threat("T-AUTH-001","tool-authority","planner-to-tool","exact capability/resource/operation grant","skeleton/testing/test_vol026_capability_security.py"),
  Threat("T-SECRET-001","secrets","secret-store-to-runtime","reference-only SecretRef","skeleton/testing/test_vol026_capability_security.py"),
  Threat("T-FS-001","filesystem","input-to-rooted-filesystem","rooted path and archive sandbox enforcement","skeleton/testing/test_security_rooted_fs.py"),
  Threat("T-NET-001","network-egress","runtime-to-network","resolved destination plus connected-peer validation","skeleton/testing/test_security_outbound_http.py"),
  Threat("T-SUPPLY-001","supply-chain","dependency-to-runtime","repository SAST and dependency integrity controls","scripts/check_repository_python_sast.py"),
 ))
