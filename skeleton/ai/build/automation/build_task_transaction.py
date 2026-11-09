"""Task transaction preserves previously accepted build baseline."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class TaskTransaction:
 task_id:str;baseline_sha256:str;candidate_sha256:str="";phase:str="prepared"
 def applied(self,candidate_sha256:str):
  if self.phase!="prepared" or len(candidate_sha256)!=64:raise ValueError("invalid task apply")
  return TaskTransaction(self.task_id,self.baseline_sha256,candidate_sha256,"applied")
 def validated(self):
  if self.phase!="applied":raise ValueError("task not applied")
  return TaskTransaction(self.task_id,self.baseline_sha256,self.candidate_sha256,"validated")
 def accepted(self):
  if self.phase!="validated":raise ValueError("task not validated")
  return TaskTransaction(self.task_id,self.baseline_sha256,self.candidate_sha256,"accepted")
