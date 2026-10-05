"""Artifact rebuild, change planning and deterministic generation VOL-335..341."""
from dataclasses import dataclass
from .contracts import sha256_json
@dataclass(frozen=True,slots=True)
class RebuildStep: artifact_id:str; input_digests:tuple[str,...]; producer_version:str; verified_inputs:bool
@dataclass(frozen=True,slots=True)
class RebuildPlan: steps:tuple[RebuildStep,...]
@dataclass(frozen=True,slots=True)
class RebuildEvidence: artifact_id:str; expected_digest:str; rebuilt_digest:str; semantic_match:bool
def rebuild_admissible(p): return bool(p.steps) and all(bool(s.artifact_id) and bool(s.input_digests) and all(bool(d) for d in s.input_digests) and s.verified_inputs and bool(s.producer_version) for s in p.steps)
def rebuild_verified(e): return bool(e.artifact_id) and bool(e.expected_digest) and e.expected_digest==e.rebuilt_digest and e.semantic_match
@dataclass(frozen=True,slots=True)
class ImpactQuery: changed_objects:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ImpactEvidence: architecture:bool; traces:bool; ownership:bool; missing_edges:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ImpactSet: affected:tuple[str,...]; owners:tuple[str,...]; uncertainty:float; evidence:ImpactEvidence
def impact(q,edges,owners,evidence):
 if not q.changed_objects: raise ValueError("changed objects required")
 seen=set(q.changed_objects);front=list(seen)
 while front:
  x=front.pop()
  for y in edges.get(x,()):
   if y not in seen:seen.add(y);front.append(y)
 uncertainty=0 if all((evidence.architecture,evidence.traces,evidence.ownership)) and not evidence.missing_edges else 1
 return ImpactSet(tuple(sorted(seen)),tuple(sorted({owners[x] for x in seen if x in owners})),uncertainty,evidence)
@dataclass(frozen=True,slots=True)
class RiskFactor: name:str; weight:float; observed:float
@dataclass(frozen=True,slots=True)
class RiskCalibration: calibration_id:str; predicted:float; observed_incident:bool
@dataclass(frozen=True,slots=True)
class ChangeRisk: score:float; factors:tuple[RiskFactor,...]; calibration_id:str
def estimate_risk(factors,calibration_id):
 if not calibration_id or not factors: raise ValueError("risk evidence required")
 if any(x.weight<0 or x.observed<0 or x.observed>1 for x in factors): raise ValueError("invalid risk factor")
 return ChangeRisk(sum(x.weight*x.observed for x in factors),tuple(factors),calibration_id)
@dataclass(frozen=True,slots=True)
class ChangeGate: name:str; passed:bool; hard:bool=True
@dataclass(frozen=True,slots=True)
class ChangeStep: step_id:str; reversible:bool; rollback:str|None
@dataclass(frozen=True,slots=True)
class SafeChangePlan: steps:tuple[ChangeStep,...]; gates:tuple[ChangeGate,...]; budget_ok:bool
def change_admissible(p): return bool(p.steps) and bool(p.gates) and p.budget_ok and not any(g.hard and not g.passed for g in p.gates) and all(bool(s.step_id) and (s.reversible or bool(s.rollback)) for s in p.steps)
@dataclass(frozen=True,slots=True)
class SystemSource: contract_version:str; content:str; authority:frozenset[str]
@dataclass(frozen=True,slots=True)
class SystemCompilePlan: generator_version:str
@dataclass(frozen=True,slots=True)
class SystemArtifact:
 digest:str; source_digest:str; generator_version:str
 @property
 def authority(self): return frozenset()
def compile_system(s,p):
 sd=sha256_json({"contract_version":s.contract_version,"content":s.content})
 return SystemArtifact(sha256_json({"source":sd,"generator":p.generator_version}),sd,p.generator_version)
@dataclass(frozen=True,slots=True)
class ExtensionPoint: name:str; manual_path:str
@dataclass(frozen=True,slots=True)
class GenerationSpec: contract_version:str; generator_version:str; extension_points:tuple[ExtensionPoint,...]
@dataclass(frozen=True,slots=True)
class GeneratedCode: content:str; generated_marker:str; spec_digest:str; output_digest:str
def generate_code(spec,body):
 d=sha256_json({"contract":spec.contract_version,"generator":spec.generator_version,"extensions":[(x.name,x.manual_path) for x in spec.extension_points]})
 return GeneratedCode(body,"GENERATED - DO NOT EDIT",d,sha256_json({"spec":d,"content":body}))
@dataclass(frozen=True,slots=True)
class SDKMethod: name:str; request_type:str; response_type:str
@dataclass(frozen=True,slots=True)
class SDKVersion: api_contract_version:str; generator_version:str
@dataclass(frozen=True,slots=True)
class ClientSDK: version:SDKVersion; methods:tuple[SDKMethod,...]; contract_digest:str
def generate_client(version,methods,contract):
 if len({x.name for x in methods})!=len(methods): raise ValueError("duplicate sdk method")
 return ClientSDK(version,tuple(sorted(methods,key=lambda x:x.name)),sha256_json({"version":version.api_contract_version,"contract":contract}))
