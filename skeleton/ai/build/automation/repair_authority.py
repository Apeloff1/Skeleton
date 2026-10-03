"""Keep CI feedback subordinate to canonical supervisor authority."""
from __future__ import annotations
from dataclasses import dataclass
from .ci_repair_queue import CIRepairTask
@dataclass(frozen=True)
class RepairAuthorization:
 task_id:str;authorized:bool;reason:str
def authorize(task:CIRepairTask,*,current_head:str,allowed_categories:set[str])->RepairAuthorization:
 if task.head_sha!=current_head:return RepairAuthorization(task.id,False,"stale exact-head evidence")
 if task.category not in allowed_categories:return RepairAuthorization(task.id,False,"category outside autonomous repair authority")
 return RepairAuthorization(task.id,True,"exact-head repair evidence authorized")
