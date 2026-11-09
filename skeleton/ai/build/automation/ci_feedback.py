"""Turn exact-head GitHub Actions observations into bounded autonomous feedback."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable,Mapping,Any
from .ci_evidence import CIEvidence,from_workflow_runs
from .ci_log_evidence import CILogEvidence,extract
from .ci_repair_queue import CIRepairTask,task_from,dedupe
@dataclass(frozen=True)
class Feedback:
 evidence:CIEvidence;repairs:tuple[CIRepairTask,...];quarantined:tuple[str,...];pending:tuple[str,...]
def build_feedback(*,head_sha:str,runs:Iterable[Mapping[str,Any]],required:tuple[str,...],job_logs:Mapping[int,tuple[int,str]])->Feedback:
 runs=tuple(runs);e=from_workflow_runs(head_sha,runs,required)
 repairs=[];quarantined=[];pending=[]
 for g in e.gates:
  if g.name not in required:continue
  if g.status!="completed":pending.append(g.name);continue
  if g.conclusion in {"success","neutral","skipped"}:continue
  pair=job_logs.get(g.run_id)
  if pair is None:quarantined.append(g.name);continue
  job_id,log=pair
  le=extract(run_id=g.run_id,job_id=job_id,gate=g.name,head_sha=head_sha,log=log)
  task=task_from(le)
  if task is None:quarantined.append(g.name)
  else:repairs.append(task)
 return Feedback(e,dedupe(repairs),tuple(sorted(set(quarantined))),tuple(sorted(set(pending))))
