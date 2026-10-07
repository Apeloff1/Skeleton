"""Convert admitted CI repairs into canonical supervisor-compatible work items."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from .ci_repair_queue import CIRepairTask
from .repair_admission import Admission
@dataclass(frozen=True)
class SupervisorRepairItem:
 id:str;title:str;objective:str;target_team:str;status:str;dependencies:tuple[str,...];source_repair_id:str;source_gate:str;source_head:str
def ingest(repair:CIRepairTask,admission:Admission,*,team:str="night")->SupervisorRepairItem:
 if not admission.accepted or admission.repair_id!=repair.id:raise ValueError("repair lacks canonical admission")
 if not admission.canonical_task_id:raise ValueError("repair missing canonical task")
 return SupervisorRepairItem(admission.canonical_task_id,f"Repair {repair.gate}",repair.objective,team,"queued",(),repair.id,repair.gate,repair.head_sha)
