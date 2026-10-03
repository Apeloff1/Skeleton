"""Deterministic training admission and durable run-state contracts."""
from dataclasses import dataclass, replace
from enum import Enum
class TrainingControlError(ValueError): pass
class RunStatus(str,Enum): PLANNED="planned"; ADMITTED="admitted"; RUNNING="running"; PAUSED="paused"; COMPLETED="completed"; FAILED="failed"
@dataclass(frozen=True, slots=True)
class TrainingConfig:
    run_id:str; dataset_manifest_digest:str; base_model_digest:str; code_digest:str; config_digest:str; max_steps:int; budget_units:int
    def __post_init__(self):
        if not self.run_id or any(len(x)!=64 for x in (self.dataset_manifest_digest,self.base_model_digest,self.code_digest,self.config_digest)): raise TrainingControlError("invalid training identity")
        if isinstance(self.max_steps,bool) or self.max_steps<1 or isinstance(self.budget_units,bool) or self.budget_units<1: raise TrainingControlError("invalid training bounds")
@dataclass(frozen=True, slots=True)
class TrainingAdmission:
    run_id:str; cpu:int; memory_mb:int; accelerator_count:int; budget_units:int; admitted:bool; reason:str
@dataclass(frozen=True, slots=True)
class TrainingRun:
    config:TrainingConfig; status:RunStatus=RunStatus.PLANNED; step:int=0; checkpoint_digest:str|None=None
class TrainingControlPlane:
    def __init__(self): self._runs={}
    def register(self,config:TrainingConfig)->TrainingRun:
        old=self._runs.get(config.run_id)
        if old is not None and old.config!=config: raise TrainingControlError("run identity cannot be rebound")
        run=old or TrainingRun(config); self._runs[config.run_id]=run; return run
    def admit(self,run_id:str,*,cpu:int,memory_mb:int,accelerator_count:int,budget_units:int)->TrainingAdmission:
        run=self._runs.get(run_id)
        if run is None: raise TrainingControlError("run must be registered")
        admitted=cpu>=1 and memory_mb>=256 and accelerator_count>=0 and budget_units>=run.config.budget_units
        admission=TrainingAdmission(run_id,cpu,memory_mb,accelerator_count,budget_units,admitted,"admitted" if admitted else "resource_or_budget_rejected")
        if admitted: self._runs[run_id]=replace(run,status=RunStatus.ADMITTED)
        return admission
    def start(self,run_id:str)->TrainingRun:
        run=self._runs[run_id]
        if run.status is not RunStatus.ADMITTED: raise TrainingControlError("run is not admitted")
        run=replace(run,status=RunStatus.RUNNING); self._runs[run_id]=run; return run
    def checkpoint(self,run_id:str,*,step:int,digest:str)->TrainingRun:
        run=self._runs[run_id]
        if run.status not in {RunStatus.RUNNING,RunStatus.PAUSED} or step<run.step or step>run.config.max_steps or len(digest)!=64: raise TrainingControlError("invalid checkpoint transition")
        run=replace(run,step=step,checkpoint_digest=digest); self._runs[run_id]=run; return run
    def state(self,run_id:str)->TrainingRun: return self._runs[run_id]
