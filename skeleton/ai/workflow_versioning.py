"""Pinned workflow versions and explicit compatibility for VOL-309."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
class WorkflowCompatibility(str,Enum): COMPATIBLE="compatible"; MIGRATION_REQUIRED="migration_required"; INCOMPATIBLE="incompatible"
@dataclass(frozen=True,order=True)
class WorkflowVersion:
 major:int; minor:int; patch:int
 def __post_init__(self):
  if any(not isinstance(x,int) or isinstance(x,bool) or x<0 for x in (self.major,self.minor,self.patch)):raise ValueError("version parts must be nonnegative integers")
 def compatible_with(self,other):
  return WorkflowCompatibility.COMPATIBLE if self.major==other.major else WorkflowCompatibility.MIGRATION_REQUIRED
@dataclass(frozen=True)
class WorkflowBinding:
 operation_id:str; workflow_id:str; pinned_version:WorkflowVersion
 def __post_init__(self):
  if not self.operation_id or not self.workflow_id:raise ValueError("operation/workflow identity required")
 def resolve(self,current_version:WorkflowVersion,migration_approved:bool=False):
  if current_version==self.pinned_version:return self
  if not migration_approved:return self
  if self.pinned_version.compatible_with(current_version) is WorkflowCompatibility.MIGRATION_REQUIRED:
   raise ValueError("major workflow migration requires explicit migration artifact")
  return WorkflowBinding(self.operation_id,self.workflow_id,current_version)
@dataclass(frozen=True)
class WorkflowMigration:
 operation_id:str; from_version:WorkflowVersion; to_version:WorkflowVersion; evidence_id:str
 def __post_init__(self):
  if self.from_version==self.to_version or not self.evidence_id:raise ValueError("migration requires version change and evidence")
 def apply(self,binding:WorkflowBinding):
  if binding.operation_id!=self.operation_id or binding.pinned_version!=self.from_version:raise ValueError("migration does not bind operation/version")
  return WorkflowBinding(binding.operation_id,binding.workflow_id,self.to_version)
