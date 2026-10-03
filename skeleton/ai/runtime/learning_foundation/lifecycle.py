"""Model bill-of-materials, lifecycle and migration authority for P3-T2."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Sequence
from skeleton.learning.model_program import ModelArtifact, TrainingReceipt

class ModelLifecycleError(RuntimeError):
    pass

def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ModelLifecycleError("value is not deterministic JSON") from exc

def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()

def _text(name: str, value: object, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelLifecycleError(f"{name} must be non-empty text")
    result=value.strip()
    if len(result)>maximum:
        raise ModelLifecycleError(f"{name} exceeds {maximum} characters")
    return result

def _sha(name: str, value: object) -> str:
    result=_text(name,value,maximum=64).lower()
    if len(result)!=64 or any(ch not in "0123456789abcdef" for ch in result):
        raise ModelLifecycleError(f"{name} must be lowercase sha256")
    return result

def _refs(name: str, values: Sequence[str], *, minimum: int = 0) -> tuple[str,...]:
    out=[]
    for raw in values:
        item=_text(name,raw)
        if item in out:
            raise ModelLifecycleError(f"{name} contains duplicate {item}")
        out.append(item)
    if len(out)<minimum:
        raise ModelLifecycleError(f"{name} requires at least {minimum} entries")
    return tuple(out)

@dataclass(frozen=True, slots=True)
class ModelBillOfMaterials:
    model_id: str
    model_digest: str
    artifact_digest: str
    artifact_kind: str
    training_run_id: str
    training_receipt_digest: str
    dataset_digests: tuple[str,...]
    trainer_id: str
    code_revision: str
    license_refs: tuple[str,...]
    rights_refs: tuple[str,...]
    dependency_refs: tuple[str,...]=()

    def __post_init__(self) -> None:
        object.__setattr__(self,"model_id",_text("model_id",self.model_id))
        object.__setattr__(self,"model_digest",_sha("model_digest",self.model_digest))
        object.__setattr__(self,"artifact_digest",_sha("artifact_digest",self.artifact_digest))
        object.__setattr__(self,"artifact_kind",_text("artifact_kind",self.artifact_kind))
        object.__setattr__(self,"training_run_id",_text("training_run_id",self.training_run_id))
        object.__setattr__(self,"training_receipt_digest",_sha("training_receipt_digest",self.training_receipt_digest))
        object.__setattr__(self,"dataset_digests",tuple(_sha("dataset_digest",x) for x in self.dataset_digests))
        if not self.dataset_digests:
            raise ModelLifecycleError("MBOM requires at least one dataset digest")
        object.__setattr__(self,"trainer_id",_text("trainer_id",self.trainer_id))
        object.__setattr__(self,"code_revision",_text("code_revision",self.code_revision,maximum=256))
        object.__setattr__(self,"license_refs",_refs("license_ref",self.license_refs,minimum=1))
        object.__setattr__(self,"rights_refs",_refs("rights_ref",self.rights_refs,minimum=1))
        object.__setattr__(self,"dependency_refs",_refs("dependency_ref",self.dependency_refs))

    @classmethod
    def from_training(cls, artifact: ModelArtifact, receipt: TrainingReceipt, *, license_refs: Sequence[str], rights_refs: Sequence[str], dependency_refs: Sequence[str]=()) -> "ModelBillOfMaterials":
        if not isinstance(artifact,ModelArtifact) or not isinstance(receipt,TrainingReceipt):
            raise TypeError("artifact/receipt types are invalid")
        if artifact.model_id!=receipt.model_id or artifact.model_digest!=receipt.model_digest:
            raise ModelLifecycleError("artifact/receipt model identity drift")
        if artifact.artifact_digest!=receipt.artifact_digest or artifact.training_run_id!=receipt.run_id:
            raise ModelLifecycleError("artifact/receipt training identity drift")
        return cls(
            model_id=artifact.model_id,model_digest=artifact.model_digest,artifact_digest=artifact.artifact_digest,
            artifact_kind=artifact.kind,training_run_id=artifact.training_run_id,training_receipt_digest=receipt.digest,
            dataset_digests=receipt.dataset_digests,trainer_id=receipt.trainer_id,code_revision=receipt.code_revision,
            license_refs=tuple(license_refs),rights_refs=tuple(rights_refs),dependency_refs=tuple(dependency_refs),
        )

    @property
    def digest(self) -> str:
        return _digest({
            "model_id":self.model_id,"model_digest":self.model_digest,"artifact_digest":self.artifact_digest,
            "artifact_kind":self.artifact_kind,"training_run_id":self.training_run_id,
            "training_receipt_digest":self.training_receipt_digest,"dataset_digests":list(self.dataset_digests),
            "trainer_id":self.trainer_id,"code_revision":self.code_revision,"license_refs":list(self.license_refs),
            "rights_refs":list(self.rights_refs),"dependency_refs":list(self.dependency_refs),
        })

class ModelLifecycleState(str,Enum):
    CANDIDATE="candidate"
    VALIDATED="validated"
    ACTIVE="active"
    DEPRECATED="deprecated"
    RETIRED="retired"

_ALLOWED={
 ModelLifecycleState.CANDIDATE:{ModelLifecycleState.VALIDATED},
 ModelLifecycleState.VALIDATED:{ModelLifecycleState.ACTIVE},
 ModelLifecycleState.ACTIVE:{ModelLifecycleState.DEPRECATED},
 ModelLifecycleState.DEPRECATED:{ModelLifecycleState.RETIRED},
 ModelLifecycleState.RETIRED:set(),
}

@dataclass(frozen=True, slots=True)
class LifecycleTransitionReceipt:
    model_digest:str
    mbom_digest:str
    from_state:str
    to_state:str
    verifier_id:str
    evidence_refs:tuple[str,...]
    receipt_digest:str

@dataclass(frozen=True, slots=True)
class ModelMigrationDecision:
    source_model_digest:str
    target_model_digest:str
    parity_score:float
    required_score:float
    verifier_id:str
    evaluation_refs:tuple[str,...]
    rollback_model_digest:str
    approved:bool
    decision_digest:str

class ModelLifecycleRegistry:
    def __init__(self) -> None:
        self._mboms={}
        self._states={}
        self._history=[]

    def register_candidate(self, mbom: ModelBillOfMaterials) -> ModelBillOfMaterials:
        if not isinstance(mbom,ModelBillOfMaterials):
            raise TypeError("mbom must be ModelBillOfMaterials")
        prior=self._mboms.get(mbom.model_digest)
        if prior is not None and prior!=mbom:
            raise ModelLifecycleError("model digest cannot be rebound to different MBOM")
        self._mboms[mbom.model_digest]=mbom
        self._states.setdefault(mbom.model_digest,ModelLifecycleState.CANDIDATE)
        return mbom

    def state(self, model_digest: str) -> ModelLifecycleState:
        digest=_sha("model_digest",model_digest)
        try:return self._states[digest]
        except KeyError as exc:raise ModelLifecycleError("unknown model") from exc

    def mbom(self, model_digest: str) -> ModelBillOfMaterials:
        digest=_sha("model_digest",model_digest)
        try:return self._mboms[digest]
        except KeyError as exc:raise ModelLifecycleError("unknown model") from exc

    def transition(self, model_digest: str, to_state: ModelLifecycleState, *, verifier_id: str, evidence_refs: Sequence[str]) -> LifecycleTransitionReceipt:
        digest=_sha("model_digest",model_digest);current=self.state(digest)
        if not isinstance(to_state,ModelLifecycleState):
            raise TypeError("to_state must be ModelLifecycleState")
        if to_state not in _ALLOWED[current]:
            raise ModelLifecycleError(f"illegal lifecycle transition {current.value}->{to_state.value}")
        mbom=self.mbom(digest);verifier=_text("verifier_id",verifier_id)
        refs=_refs("evidence_ref",evidence_refs,minimum=2 if to_state in {ModelLifecycleState.VALIDATED,ModelLifecycleState.ACTIVE} else 1)
        if to_state in {ModelLifecycleState.VALIDATED,ModelLifecycleState.ACTIVE} and verifier==mbom.trainer_id:
            raise ModelLifecycleError("trainer cannot independently validate or activate its own model")
        payload={"model_digest":digest,"mbom_digest":mbom.digest,"from_state":current.value,"to_state":to_state.value,"verifier_id":verifier,"evidence_refs":list(refs)}
        receipt=LifecycleTransitionReceipt(digest,mbom.digest,current.value,to_state.value,verifier,refs,_digest(payload))
        self._states[digest]=to_state;self._history.append(receipt);return receipt

    def migration_decision(self, *, source_model_digest: str, target_model_digest: str, parity_score: float, required_score: float, verifier_id: str, evaluation_refs: Sequence[str]) -> ModelMigrationDecision:
        source=_sha("source_model_digest",source_model_digest);target=_sha("target_model_digest",target_model_digest)
        if source==target:raise ModelLifecycleError("migration source and target must differ")
        if self.state(source) is not ModelLifecycleState.ACTIVE:raise ModelLifecycleError("migration source must be active")
        if self.state(target) is not ModelLifecycleState.VALIDATED:raise ModelLifecycleError("migration target must be validated")
        if isinstance(parity_score,bool) or not isinstance(parity_score,(int,float)) or isinstance(required_score,bool) or not isinstance(required_score,(int,float)):
            raise ModelLifecycleError("parity scores must be numeric")
        score=float(parity_score);required=float(required_score)
        if not 0.0<=score<=1.0 or not 0.0<=required<=1.0:raise ModelLifecycleError("parity scores must be in [0, 1]")
        verifier=_text("verifier_id",verifier_id);source_mbom=self.mbom(source);target_mbom=self.mbom(target)
        if verifier in {source_mbom.trainer_id,target_mbom.trainer_id}:raise ModelLifecycleError("migration verifier must be independent of both trainers")
        refs=_refs("evaluation_ref",evaluation_refs,minimum=2);approved=score>=required
        payload={"source_model_digest":source,"target_model_digest":target,"source_mbom_digest":source_mbom.digest,"target_mbom_digest":target_mbom.digest,"parity_score":score,"required_score":required,"verifier_id":verifier,"evaluation_refs":list(refs),"rollback_model_digest":source,"approved":approved}
        return ModelMigrationDecision(source,target,score,required,verifier,refs,source,approved,_digest(payload))

    @property
    def history(self) -> tuple[LifecycleTransitionReceipt,...]:
        return tuple(self._history)

__all__=["LifecycleTransitionReceipt","ModelBillOfMaterials","ModelLifecycleError","ModelLifecycleRegistry","ModelLifecycleState","ModelMigrationDecision"]
