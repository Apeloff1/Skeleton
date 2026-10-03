"""Deduplicated queue of exact-head CI repair work."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,asdict
from typing import Iterable
from .ci_log_evidence import CILogEvidence
from .ci_failure_attribution import attribute
@dataclass(frozen=True)
class CIRepairTask:
 id:str;gate:str;category:str;head_sha:str;run_id:int;job_id:int;evidence_sha256:str;objective:str
def task_from(e:CILogEvidence)->CIRepairTask|None:
 e.validate();a=attribute(e.gate)
 if not a.retryable:return None
 evidence_sha=hashlib.sha256(e.excerpt.encode()).hexdigest()
 identity=hashlib.sha256(f"{e.head_sha}:{e.run_id}:{e.job_id}:{e.gate}:{evidence_sha}".encode()).hexdigest()[:24]
 return CIRepairTask("ci-repair-"+identity,e.gate,a.category,e.head_sha,e.run_id,e.job_id,evidence_sha,f"Repair exact-head {e.gate} failure using bounded CI evidence; preserve and satisfy the failing gate.")
def dedupe(tasks:Iterable[CIRepairTask])->tuple[CIRepairTask,...]:
 by_id={t.id:t for t in tasks};return tuple(by_id[k] for k in sorted(by_id))
