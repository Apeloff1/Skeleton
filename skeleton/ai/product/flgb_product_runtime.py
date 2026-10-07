"""FLGB-18 integrated product orchestration, deployment, and closure contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_PLANES=64
MAX_OPERATIONS=100_000
MAX_RESOURCES=10**12
MAX_TASKS=100_000
MAX_ITERATIONS=10_000
MAX_PLATFORMS=128
MAX_GATES=100_000
MAX_EVIDENCE=100_000
EXPECTED_FLGB_PLANES=tuple(f"FLGB-{index:02d}" for index in range(1,19))

class ProductContractError(ValueError):
    """Fail-closed FLGB-18 contract error."""

def _is_int(value:Any)->bool:
    return isinstance(value,int) and not isinstance(value,bool)

def require_id(value:str,name:str)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>MAX_ID_CHARS or any(ord(ch)<32 for ch in value):
        raise ProductContractError(f"invalid {name}")
    return value

def require_digest(value:str,name:str)->str:
    if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ProductContractError(f"invalid {name}")
    return value

def digest_json(value:Any)->str:
    try:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError) as exc:
        raise ProductContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

def canonical_ids(values:Sequence[str],name:str,max_items:int=MAX_PLANES)->tuple[str,...]:
    result=tuple(sorted(values))
    if len(result)>max_items or len(set(result))!=len(result): raise ProductContractError(f"invalid {name}")
    for item in result: require_id(item,name)
    return result

@dataclass(frozen=True)
class PlaneBootEvidence:
    plane_id:str
    implementation_digest:str
    state:str

    def __post_init__(self)->None:
        require_id(self.plane_id,"plane_id"); require_digest(self.implementation_digest,"implementation_digest")
        if self.state not in {"implemented-pending-verification","verified"}: raise ProductContractError("invalid plane boot state")

@dataclass(frozen=True)
class ProductBootManifest:
    product_id:str
    exact_head_commit:str
    plane_evidence:tuple[PlaneBootEvidence,...]
    config_digest:str
    environment_digest:str

    def __post_init__(self)->None:
        require_id(self.product_id,"product_id"); require_digest(self.exact_head_commit,"exact_head_commit"); require_digest(self.config_digest,"config_digest"); require_digest(self.environment_digest,"environment_digest")
        if not self.plane_evidence or len(self.plane_evidence)>MAX_PLANES: raise ProductContractError("plane boot evidence count out of bounds")
        ids=[p.plane_id for p in self.plane_evidence]
        if len(set(ids))!=len(ids): raise ProductContractError("duplicate plane boot evidence")
        if set(ids)!=set(EXPECTED_FLGB_PLANES): raise ProductContractError("product boot requires FLGB-01 through FLGB-18 evidence")
        object.__setattr__(self,"plane_evidence",tuple(sorted(self.plane_evidence,key=lambda p:p.plane_id)))

    @property
    def digest(self)->str:
        return digest_json({"product_id":self.product_id,"exact_head_commit":self.exact_head_commit,"plane_evidence":[p.__dict__ for p in self.plane_evidence],"config_digest":self.config_digest,"environment_digest":self.environment_digest})

@dataclass(frozen=True)
class ProjectBootstrapRequest:
    project_id:str
    template_digest:str
    seed_digest:str
    rights_digest:str
    settings_digest:str
    requested_worlds:tuple[str,...]

    def __post_init__(self)->None:
        require_id(self.project_id,"project_id")
        for name in ("template_digest","seed_digest","rights_digest","settings_digest"): require_digest(getattr(self,name),name)
        worlds=canonical_ids(self.requested_worlds,"requested world",1024)
        if not worlds: raise ProductContractError("project bootstrap requires at least one world")
        object.__setattr__(self,"requested_worlds",worlds)

    @property
    def digest(self)->str:return digest_json({"project_id":self.project_id,"template_digest":self.template_digest,"seed_digest":self.seed_digest,"rights_digest":self.rights_digest,"settings_digest":self.settings_digest,"requested_worlds":list(self.requested_worlds)})

@dataclass(frozen=True)
class ProjectBootstrapReceipt:
    request_digest:str
    project_manifest_digest:str
    initial_state_digest:str
    provenance_digest:str

    def __post_init__(self)->None:
        for name in ("request_digest","project_manifest_digest","initial_state_digest","provenance_digest"): require_digest(getattr(self,name),name)

    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class BuildOperation:
    sequence:int
    operation_id:str
    input_digest:str
    output_digest:str
    authority_digest:str

    def __post_init__(self)->None:
        if not _is_int(self.sequence) or self.sequence<0: raise ProductContractError("invalid build operation sequence")
        require_id(self.operation_id,"operation_id")
        for name in ("input_digest","output_digest","authority_digest"): require_digest(getattr(self,name),name)

@dataclass(frozen=True)
class ChatBuildTransaction:
    transaction_id:str
    conversation_digest:str
    request_digest:str
    project_digest_before:str
    project_digest_after:str
    operations:tuple[BuildOperation,...]
    idempotency_key:str

    def __post_init__(self)->None:
        require_id(self.transaction_id,"transaction_id"); require_id(self.idempotency_key,"idempotency_key")
        for name in ("conversation_digest","request_digest","project_digest_before","project_digest_after"): require_digest(getattr(self,name),name)
        if not self.operations or len(self.operations)>MAX_OPERATIONS: raise ProductContractError("build operation count out of bounds")
        for index,op in enumerate(self.operations):
            if not isinstance(op,BuildOperation) or op.sequence!=index: raise ProductContractError("chat-build operation sequence drift")
        if self.project_digest_before==self.project_digest_after: raise ProductContractError("chat-build transaction must change project state")

    @property
    def digest(self)->str:return digest_json({"transaction_id":self.transaction_id,"conversation_digest":self.conversation_digest,"request_digest":self.request_digest,"project_digest_before":self.project_digest_before,"project_digest_after":self.project_digest_after,"operations":[op.__dict__ for op in self.operations],"idempotency_key":self.idempotency_key})

@dataclass(frozen=True)
class BuildEvidence:
    transaction_digest:str
    exact_head_commit:str
    build_digest:str
    test_digest:str
    artifact_digest:str
    status:str

    def __post_init__(self)->None:
        for name in ("transaction_digest","exact_head_commit","build_digest","test_digest","artifact_digest"): require_digest(getattr(self,name),name)
        if self.status not in {"passed","failed"}: raise ProductContractError("invalid build evidence status")

    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class ResourceRequest:
    task_id:str
    cpu_units:int
    memory_bytes:int
    priority:int
    foreground:bool
    preemptible:bool

    def __post_init__(self)->None:
        require_id(self.task_id,"task_id")
        for name in ("cpu_units","memory_bytes"):
            value=getattr(self,name)
            if not _is_int(value) or not 0<value<=MAX_RESOURCES: raise ProductContractError(f"invalid {name}")
        if not _is_int(self.priority): raise ProductContractError("invalid priority")
        if not isinstance(self.foreground,bool) or not isinstance(self.preemptible,bool): raise ProductContractError("resource flags must be boolean")

def schedule_resources(requests:Sequence[ResourceRequest],cpu_budget:int,memory_budget:int)->tuple[ResourceRequest,...]:
    if len(requests)>MAX_TASKS: raise ProductContractError("resource request budget exceeded")
    if not _is_int(cpu_budget) or not _is_int(memory_budget) or cpu_budget<0 or memory_budget<0: raise ProductContractError("invalid resource budgets")
    ids=[r.task_id for r in requests]
    if len(set(ids))!=len(ids): raise ProductContractError("duplicate resource task")
    ordered=sorted(requests,key=lambda r:(not r.foreground,-r.priority,r.cpu_units,r.memory_bytes,r.task_id))
    selected=[]; cpu=0; memory=0
    for request in ordered:
        if cpu+request.cpu_units<=cpu_budget and memory+request.memory_bytes<=memory_budget:
            selected.append(request); cpu+=request.cpu_units; memory+=request.memory_bytes
    return tuple(selected)

@dataclass(frozen=True)
class ForegroundPolicy:
    policy_id:str
    foreground_reserve_cpu:int
    foreground_reserve_memory:int
    allow_preempt_background:bool=True

    def __post_init__(self)->None:
        require_id(self.policy_id,"policy_id")
        for name in ("foreground_reserve_cpu","foreground_reserve_memory"):
            value=getattr(self,name)
            if not _is_int(value) or not 0<=value<=MAX_RESOURCES: raise ProductContractError(f"invalid {name}")
        if not isinstance(self.allow_preempt_background,bool): raise ProductContractError("allow_preempt_background must be boolean")

    def should_preempt(self,foreground_waiting:bool,background:ResourceRequest)->bool:
        if not isinstance(foreground_waiting,bool): raise ProductContractError("foreground_waiting must be boolean")
        if background.foreground: return False
        return foreground_waiting and self.allow_preempt_background and background.preemptible

@dataclass(frozen=True)
class IdleMirrorPlan:
    plan_id:str
    baseline_digest:str
    max_iterations:int
    cpu_cap:int
    memory_cap:int
    output_kind:str="candidate-only"

    def __post_init__(self)->None:
        require_id(self.plan_id,"plan_id"); require_digest(self.baseline_digest,"baseline_digest")
        if not _is_int(self.max_iterations) or not 1<=self.max_iterations<=MAX_ITERATIONS: raise ProductContractError("invalid mirror iterations")
        for name in ("cpu_cap","memory_cap"):
            value=getattr(self,name)
            if not _is_int(value) or not 0<value<=MAX_RESOURCES: raise ProductContractError(f"invalid {name}")
        if self.output_kind!="candidate-only": raise ProductContractError("idle mirror room cannot self-promote")

    def may_run(self,foreground_active:bool,idle:bool)->bool:
        if not isinstance(foreground_active,bool) or not isinstance(idle,bool): raise ProductContractError("idle state flags must be boolean")
        return idle and not foreground_active

@dataclass(frozen=True)
class PlaneDependency:
    plane_id:str
    dependencies:tuple[str,...]
    evidence_digest:str

    def __post_init__(self)->None:
        require_id(self.plane_id,"plane_id"); require_digest(self.evidence_digest,"evidence_digest")
        deps=canonical_ids(self.dependencies,"plane dependency",MAX_PLANES)
        if self.plane_id in deps: raise ProductContractError("plane cannot depend on itself")
        object.__setattr__(self,"dependencies",deps)

def dependency_order(planes:Sequence[PlaneDependency])->tuple[str,...]:
    if not planes or len(planes)>MAX_PLANES: raise ProductContractError("plane dependency count out of bounds")
    by_id={p.plane_id:p for p in planes}
    if len(by_id)!=len(planes): raise ProductContractError("duplicate plane dependency node")
    for p in planes:
        if set(p.dependencies)-set(by_id): raise ProductContractError("unknown cross-plane dependency")
    remaining=set(by_id); done=set(); result=[]
    while remaining:
        ready=sorted(pid for pid in remaining if set(by_id[pid].dependencies).issubset(done))
        if not ready: raise ProductContractError("cross-plane dependency cycle")
        result.extend(ready); done.update(ready); remaining.difference_update(ready)
    return tuple(result)

@dataclass(frozen=True)
class InstallerHandoff:
    package_digest:str
    installer_manifest_digest:str
    provenance_digest:str
    signing_digest:str
    target_platforms:tuple[str,...]
    verification_digest:str

    def __post_init__(self)->None:
        for name in ("package_digest","installer_manifest_digest","provenance_digest","signing_digest","verification_digest"): require_digest(getattr(self,name),name)
        targets=canonical_ids(self.target_platforms,"target platform",MAX_PLATFORMS)
        if not targets: raise ProductContractError("installer handoff requires target platform")
        object.__setattr__(self,"target_platforms",targets)

    @property
    def digest(self)->str:return digest_json({"package_digest":self.package_digest,"installer_manifest_digest":self.installer_manifest_digest,"provenance_digest":self.provenance_digest,"signing_digest":self.signing_digest,"target_platforms":list(self.target_platforms),"verification_digest":self.verification_digest})

@dataclass(frozen=True)
class UpdateRollbackPlan:
    current_release_digest:str
    target_release_digest:str
    update_package_digest:str
    rollback_artifact_digest:str
    migration_digest:str
    rollback_test_digest:str

    def __post_init__(self)->None:
        for name in ("current_release_digest","target_release_digest","update_package_digest","rollback_artifact_digest","migration_digest","rollback_test_digest"): require_digest(getattr(self,name),name)
        if self.current_release_digest==self.target_release_digest: raise ProductContractError("update must change release")

    @property
    def ready(self)->bool:return True
    @property
    def digest(self)->str:return digest_json(self.__dict__)

@dataclass(frozen=True)
class AcceptanceGate:
    gate_id:str
    passed:bool
    critical:bool
    evidence_digest:str

    def __post_init__(self)->None:
        require_id(self.gate_id,"gate_id"); require_digest(self.evidence_digest,"evidence_digest")
        if not isinstance(self.passed,bool) or not isinstance(self.critical,bool): raise ProductContractError("acceptance flags must be boolean")

@dataclass(frozen=True)
class WholeSystemAcceptance:
    candidate_digest:str
    exact_head_commit:str
    gates:tuple[AcceptanceGate,...]
    independent_verifier:str

    def __post_init__(self)->None:
        require_digest(self.candidate_digest,"candidate_digest"); require_digest(self.exact_head_commit,"exact_head_commit"); require_id(self.independent_verifier,"independent_verifier")
        if not self.gates or len(self.gates)>MAX_GATES: raise ProductContractError("acceptance gate count out of bounds")
        ids=[g.gate_id for g in self.gates]
        if len(set(ids))!=len(ids): raise ProductContractError("duplicate acceptance gate")

    @property
    def accepted(self)->bool:return all(g.passed for g in self.gates)
    @property
    def digest(self)->str:return digest_json({"candidate_digest":self.candidate_digest,"exact_head_commit":self.exact_head_commit,"gates":[g.__dict__ for g in self.gates],"independent_verifier":self.independent_verifier})

@dataclass(frozen=True)
class PlaneClosureEvidence:
    plane_id:str
    exact_head_commit:str
    implementation_digest:str
    implementation_signed:bool
    independent_verification_signed:bool
    verifier_id:str|None

    def __post_init__(self)->None:
        require_id(self.plane_id,"plane_id"); require_digest(self.exact_head_commit,"exact_head_commit"); require_digest(self.implementation_digest,"implementation_digest")
        if not isinstance(self.implementation_signed,bool) or not isinstance(self.independent_verification_signed,bool): raise ProductContractError("closure signoff flags must be boolean")
        if self.verifier_id is not None: require_id(self.verifier_id,"verifier_id")
        if self.independent_verification_signed and self.verifier_id is None: raise ProductContractError("independent verification requires verifier identity")

    @property
    def closed(self)->bool:return self.implementation_signed and self.independent_verification_signed and self.verifier_id is not None

@dataclass(frozen=True)
class ClosureFanInReceipt:
    exact_head_commit:str
    plane_ids:tuple[str,...]
    acceptance_digest:str
    evidence_digest:str

    def __post_init__(self)->None:
        require_digest(self.exact_head_commit,"exact_head_commit"); require_digest(self.acceptance_digest,"acceptance_digest"); require_digest(self.evidence_digest,"evidence_digest")
        planes=canonical_ids(self.plane_ids,"plane_id",MAX_PLANES)
        if not planes: raise ProductContractError("closure fan-in requires planes")
        object.__setattr__(self,"plane_ids",planes)

def fan_in_closure(evidence:Sequence[PlaneClosureEvidence],acceptance:WholeSystemAcceptance)->ClosureFanInReceipt:
    if not evidence or len(evidence)>MAX_EVIDENCE: raise ProductContractError("closure evidence count out of bounds")
    ids=[e.plane_id for e in evidence]
    if len(set(ids))!=len(ids): raise ProductContractError("duplicate plane closure evidence")
    if set(ids)!=set(EXPECTED_FLGB_PLANES): raise ProductContractError("closure fan-in requires FLGB-01 through FLGB-18 evidence")
    if not acceptance.accepted: raise ProductContractError("whole-system acceptance has not passed")
    if any(e.exact_head_commit!=acceptance.exact_head_commit for e in evidence): raise ProductContractError("closure exact-head mismatch")
    open_planes=[e.plane_id for e in evidence if not e.closed]
    if open_planes: raise ProductContractError("closure contains unsigned planes: "+",".join(sorted(open_planes)))
    evidence_digest=digest_json([{"plane_id":e.plane_id,"exact_head_commit":e.exact_head_commit,"implementation_digest":e.implementation_digest,"implementation_signed":e.implementation_signed,"independent_verification_signed":e.independent_verification_signed,"verifier_id":e.verifier_id} for e in sorted(evidence,key=lambda e:e.plane_id)])
    return ClosureFanInReceipt(acceptance.exact_head_commit,tuple(ids),acceptance.digest,evidence_digest)
