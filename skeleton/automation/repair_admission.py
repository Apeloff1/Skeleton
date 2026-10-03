"""Canonical admission gate between CI evidence and autonomous implementation."""
from __future__ import annotations
from dataclasses import dataclass
from .ci_repair_queue import CIRepairTask
@dataclass(frozen=True)
class Admission:
 repair_id:str;accepted:bool;reason:str;canonical_task_id:str=""
def admit(repair:CIRepairTask,*,head_sha:str,supervisor_generation:str,authorized_gates:set[str],canonical_task_id:str="")->Admission:
 if repair.head_sha!=head_sha:return Admission(repair.id,False,"stale exact-head evidence")
 if not supervisor_generation:return Admission(repair.id,False,"missing supervisor generation")
 if repair.gate not in authorized_gates:return Admission(repair.id,False,"gate not authorized by canonical supervisor")
 if not canonical_task_id:return Admission(repair.id,False,"repair has no canonical task identity")
 return Admission(repair.id,True,"canonical repair admitted",canonical_task_id)
