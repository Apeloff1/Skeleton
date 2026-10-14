"""FLGB-07 governed dataset, training, candidate-weight, and promotion contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Sequence

MAX_ID_CHARS=256
MAX_SCOPES=1024
MAX_DATASETS=100000
MAX_CHECKPOINTS=1000000
MAX_FINGERPRINTS=2000000
MAX_SCORE_PPM=1000000
MAX_STEPS=10**12

class TrainingContractError(ValueError):
    """Fail-closed FLGB-07 contract error."""

def _is_int(v:Any)->bool: return isinstance(v,int) and not isinstance(v,bool)

def require_id(v:str,name:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID_CHARS or any(ord(c)<32 for c in v):
        raise TrainingContractError(f"invalid {name}")
    return v

def require_digest(v:str,name:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):
        raise TrainingContractError(f"invalid {name}")
    return v

def digest_json(v:Any)->str:
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode("utf-8")
    except (TypeError,ValueError) as exc: raise TrainingContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

def _canonical_ids(values:Sequence[str],name:str)->tuple[str,...]:
    result=tuple(sorted(values))
    if len(result)>MAX_SCOPES or len(set(result))!=len(result): raise TrainingContractError(f"invalid {name}")
    for item in result: require_id(item,name)
    return result

@dataclass(frozen=True)
class DatasetRights:
    dataset_id:str
    source_id:str
    rights_status:str
    license_id:str|None
    allowed_scopes:tuple[str,...]
    evidence_digest:str

    def __post_init__(self)->None:
        require_id(self.dataset_id,"dataset_id"); require_id(self.source_id,"source_id"); require_digest(self.evidence_digest,"evidence_digest")
        if self.rights_status not in {"allowed","restricted","quarantined","denied"}: raise TrainingContractError("invalid rights_status")
        if self.license_id is not None: require_id(self.license_id,"license_id")
        object.__setattr__(self,"allowed_scopes",_canonical_ids(self.allowed_scopes,"allowed_scope"))
        if self.rights_status=="allowed" and not self.allowed_scopes: raise TrainingContractError("allowed dataset requires explicit scope")

    def permits(self,scope:str)->bool:
        scope=require_id(scope,"scope")
        return self.rights_status=="allowed" and scope in self.allowed_scopes

    @property
    def digest(self)->str: return digest_json({"dataset_id":self.dataset_id,"source_id":self.source_id,"rights_status":self.rights_status,"license_id":self.license_id,"allowed_scopes":list(self.allowed_scopes),"evidence_digest":self.evidence_digest})

@dataclass(frozen=True)
class DatasetRevision:
    dataset_id:str
    revision:int
    content_digest:str
    rights_digest:str
    transform_digest:str
    parent_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.dataset_id,"dataset_id")
        if not _is_int(self.revision) or self.revision<0: raise TrainingContractError("invalid dataset revision")
        for name in ("content_digest","rights_digest","transform_digest"): require_digest(getattr(self,name),name)
        if self.parent_digest is not None: require_digest(self.parent_digest,"parent_digest")
        if self.revision==0 and self.parent_digest is not None: raise TrainingContractError("genesis dataset revision cannot have parent")
        if self.revision>0 and self.parent_digest is None: raise TrainingContractError("dataset revision requires parent")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

    def revise(self,content_digest:str,rights_digest:str,transform_digest:str)->"DatasetRevision":
        return DatasetRevision(self.dataset_id,self.revision+1,require_digest(content_digest,"content_digest"),require_digest(rights_digest,"rights_digest"),require_digest(transform_digest,"transform_digest"),self.digest)

@dataclass(frozen=True)
class DedupRecord:
    item_id:str
    fingerprint:str
    content_digest:str

    def __post_init__(self)->None:
        require_id(self.item_id,"item_id"); require_digest(self.fingerprint,"fingerprint"); require_digest(self.content_digest,"content_digest")

def deduplicate(records:Sequence[DedupRecord])->tuple[DedupRecord,...]:
    if len(records)>MAX_FINGERPRINTS: raise TrainingContractError("deduplication budget exceeded")
    seen_items=set(); chosen={}
    for record in sorted(records,key=lambda r:r.item_id):
        if record.item_id in seen_items: raise TrainingContractError("duplicate item identity")
        seen_items.add(record.item_id)
        chosen.setdefault(record.fingerprint,record)
    return tuple(sorted(chosen.values(),key=lambda r:r.item_id))

@dataclass(frozen=True)
class ContaminationFinding:
    dataset_item_digest:str
    benchmark_item_digest:str
    relation:str

    def __post_init__(self)->None:
        require_digest(self.dataset_item_digest,"dataset_item_digest"); require_digest(self.benchmark_item_digest,"benchmark_item_digest")
        if self.relation not in {"exact","derived","near-duplicate"}: raise TrainingContractError("invalid contamination relation")

def scan_contamination(dataset_digests:Sequence[str],benchmark_digests:Sequence[str])->tuple[ContaminationFinding,...]:
    dataset=tuple(require_digest(x,"dataset_digest") for x in dataset_digests)
    benchmark=set(require_digest(x,"benchmark_digest") for x in benchmark_digests)
    if len(set(dataset))!=len(dataset) or len(benchmark)!=len(tuple(benchmark_digests)): raise TrainingContractError("duplicate contamination identity")
    return tuple(ContaminationFinding(d,d,"exact") for d in sorted(set(dataset)&benchmark))

@dataclass(frozen=True)
class TrainingManifest:
    run_id:str
    base_model_digest:str
    dataset_revision_digests:tuple[str,...]
    code_digest:str
    config_digest:str
    seed_manifest_digest:str
    max_steps:int
    output_kind:str="candidate-only"

    def __post_init__(self)->None:
        require_id(self.run_id,"run_id")
        for name in ("base_model_digest","code_digest","config_digest","seed_manifest_digest"): require_digest(getattr(self,name),name)
        ds=tuple(self.dataset_revision_digests)
        if not ds or len(ds)>MAX_DATASETS or len(set(ds))!=len(ds): raise TrainingContractError("invalid dataset revision set")
        for d in ds: require_digest(d,"dataset_revision_digest")
        object.__setattr__(self,"dataset_revision_digests",tuple(sorted(ds)))
        if not _is_int(self.max_steps) or not 1<=self.max_steps<=MAX_STEPS: raise TrainingContractError("invalid max_steps")
        if self.output_kind!="candidate-only": raise TrainingContractError("training cannot directly publish production weights")

    @property
    def digest(self)->str: return digest_json({"run_id":self.run_id,"base_model_digest":self.base_model_digest,"dataset_revision_digests":list(self.dataset_revision_digests),"code_digest":self.code_digest,"config_digest":self.config_digest,"seed_manifest_digest":self.seed_manifest_digest,"max_steps":self.max_steps,"output_kind":self.output_kind})

@dataclass(frozen=True)
class TrainingCheckpoint:
    run_manifest_digest:str
    sequence:int
    weights_digest:str
    optimizer_digest:str
    rng_digest:str
    prior_checkpoint_digest:str|None=None

    def __post_init__(self)->None:
        for name in ("run_manifest_digest","weights_digest","optimizer_digest","rng_digest"): require_digest(getattr(self,name),name)
        if not _is_int(self.sequence) or not 0<=self.sequence<MAX_CHECKPOINTS: raise TrainingContractError("invalid checkpoint sequence")
        if self.prior_checkpoint_digest is not None: require_digest(self.prior_checkpoint_digest,"prior_checkpoint_digest")
        if self.sequence==0 and self.prior_checkpoint_digest is not None: raise TrainingContractError("genesis checkpoint cannot have parent")
        if self.sequence>0 and self.prior_checkpoint_digest is None: raise TrainingContractError("checkpoint requires parent")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

    def next(self,weights_digest:str,optimizer_digest:str,rng_digest:str)->"TrainingCheckpoint":
        return TrainingCheckpoint(self.run_manifest_digest,self.sequence+1,require_digest(weights_digest,"weights_digest"),require_digest(optimizer_digest,"optimizer_digest"),require_digest(rng_digest,"rng_digest"),self.digest)

@dataclass(frozen=True)
class DistillationRun:
    run_id:str
    teacher_digest:str
    student_base_digest:str
    dataset_revision_digest:str
    objective_digest:str
    output_kind:str="candidate-only"

    def __post_init__(self)->None:
        require_id(self.run_id,"run_id")
        for name in ("teacher_digest","student_base_digest","dataset_revision_digest","objective_digest"): require_digest(getattr(self,name),name)
        if self.output_kind!="candidate-only": raise TrainingContractError("distillation cannot self-promote")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class AdapterTrainingRun:
    run_id:str
    base_model_digest:str
    dataset_revision_digest:str
    target_modules:tuple[str,...]
    config_digest:str
    output_kind:str="candidate-only"

    def __post_init__(self)->None:
        require_id(self.run_id,"run_id"); require_digest(self.base_model_digest,"base_model_digest"); require_digest(self.dataset_revision_digest,"dataset_revision_digest"); require_digest(self.config_digest,"config_digest")
        modules=_canonical_ids(self.target_modules,"target_module")
        if not modules: raise TrainingContractError("adapter training requires target modules")
        object.__setattr__(self,"target_modules",modules)
        if self.output_kind!="candidate-only": raise TrainingContractError("adapter training cannot self-promote")

@dataclass(frozen=True)
class CandidateWeights:
    candidate_id:str
    weights_digest:str
    training_lineage_digest:str
    base_model_digest:str
    status:str="candidate"

    def __post_init__(self)->None:
        require_id(self.candidate_id,"candidate_id")
        for name in ("weights_digest","training_lineage_digest","base_model_digest"): require_digest(getattr(self,name),name)
        if self.status not in {"candidate","quarantined","rejected","promoted"}: raise TrainingContractError("invalid candidate status")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

    def production_authorized(self)->bool: return False

@dataclass(frozen=True)
class MirrorEvaluation:
    evaluation_id:str
    candidate_digest:str
    champion_digest:str
    candidate_score_ppm:int
    champion_score_ppm:int
    risk_gate_passed:bool
    independent_verifier:str
    evidence_digest:str

    def __post_init__(self)->None:
        require_id(self.evaluation_id,"evaluation_id"); require_id(self.independent_verifier,"independent_verifier")
        for name in ("candidate_digest","champion_digest","evidence_digest"): require_digest(getattr(self,name),name)
        for name in ("candidate_score_ppm","champion_score_ppm"):
            value=getattr(self,name)
            if not _is_int(value) or not 0<=value<=MAX_SCORE_PPM: raise TrainingContractError(f"invalid {name}")
        if not isinstance(self.risk_gate_passed,bool): raise TrainingContractError("risk_gate_passed must be boolean")

    @property
    def candidate_wins(self)->bool: return self.risk_gate_passed and self.candidate_score_ppm>self.champion_score_ppm

@dataclass(frozen=True)
class PromotionEvidence:
    candidate_digest:str
    exact_head_commit:str
    rights_digest:str
    contamination_scan_digest:str
    evaluation_digest:str
    rollback_digest:str
    independent_verifier:str
    rights_passed:bool
    contamination_clear:bool
    evaluation_passed:bool
    rollback_ready:bool

    def __post_init__(self)->None:
        for name in ("candidate_digest","exact_head_commit","rights_digest","contamination_scan_digest","evaluation_digest","rollback_digest"): require_digest(getattr(self,name),name)
        require_id(self.independent_verifier,"independent_verifier")
        for name in ("rights_passed","contamination_clear","evaluation_passed","rollback_ready"):
            if not isinstance(getattr(self,name),bool): raise TrainingContractError(f"{name} must be boolean")

    @property
    def qualified(self)->bool:
        return self.rights_passed and self.contamination_clear and self.evaluation_passed and self.rollback_ready

    @property
    def digest(self)->str: return digest_json(self.__dict__)
