"""Experimental post-training lineage separated from production model authority."""
from dataclasses import dataclass
import hashlib,json
class PostTrainingError(ValueError): pass
@dataclass(frozen=True, slots=True)
class PostTrainingRun:
    run_id:str; base_model_digest:str; dataset_digest:str; objective:str; algorithm:str; config_digest:str
@dataclass(frozen=True, slots=True)
class PostTrainingCandidate:
    candidate_id:str; run_id:str; model_digest:str; evaluation_receipt_digest:str; promotion_authorized:bool=False
class PostTrainingLab:
    def __init__(self): self._runs={}; self._candidates={}
    def register(self,run:PostTrainingRun)->None:
        if not run.run_id or any(len(x)!=64 for x in (run.base_model_digest,run.dataset_digest,run.config_digest)) or not run.objective or not run.algorithm: raise PostTrainingError("invalid post-training lineage")
        old=self._runs.get(run.run_id)
        if old is not None and old!=run: raise PostTrainingError("run identity cannot be rebound")
        self._runs[run.run_id]=run
    def candidate(self,*,run_id:str,model_digest:str,evaluation_receipt_digest:str)->PostTrainingCandidate:
        if run_id not in self._runs or len(model_digest)!=64 or len(evaluation_receipt_digest)!=64: raise PostTrainingError("invalid candidate lineage")
        cid=hashlib.sha256(json.dumps([run_id,model_digest,evaluation_receipt_digest],separators=(",",":")).encode()).hexdigest()
        c=PostTrainingCandidate(cid,run_id,model_digest,evaluation_receipt_digest,False); self._candidates[cid]=c; return c
