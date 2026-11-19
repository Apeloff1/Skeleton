"""Conservative semantic task classification for VOL-311."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
class TaskType(str,Enum):
 GENERIC="generic"; RESEARCH="research"; CODE_CHANGE="code_change"; SECURITY="security"; DATA_CHANGE="data_change"; RELEASE="release"
@dataclass(frozen=True)
class TaskProfile:
 task_type:TaskType; default_budget:int; required_tests:tuple[str,...]; policy_tags:tuple[str,...]; grants_privilege:bool=False
 def __post_init__(self):
  if self.default_budget<0:raise ValueError("budget must be nonnegative")
  if self.grants_privilege:raise ValueError("task profiles cannot grant privilege")
@dataclass(frozen=True)
class TaskClassification:
 task_type:TaskType; confidence:float; reasons:tuple[str,...]; profile:TaskProfile
 def __post_init__(self):
  if not 0<=self.confidence<=1:raise ValueError("confidence out of range")
  if self.profile.task_type is not self.task_type:raise ValueError("profile/type mismatch")
_PROFILES={
 TaskType.GENERIC:TaskProfile(TaskType.GENERIC,1,("generic-validation",),("conservative",)),
 TaskType.RESEARCH:TaskProfile(TaskType.RESEARCH,2,("source-validation",),("read-mostly",)),
 TaskType.CODE_CHANGE:TaskProfile(TaskType.CODE_CHANGE,3,("unit","integration"),("code-change",)),
 TaskType.SECURITY:TaskProfile(TaskType.SECURITY,4,("unit","security","integration"),("security-sensitive",)),
 TaskType.DATA_CHANGE:TaskProfile(TaskType.DATA_CHANGE,4,("schema","rollback"),("data-sensitive",)),
 TaskType.RELEASE:TaskProfile(TaskType.RELEASE,5,("integration","release"),("release-sensitive",)),
}
def classify_task(label:str)->TaskClassification:
 if not isinstance(label,str) or not label.strip():raise ValueError("task label required")
 text=label.lower()
 rules=((TaskType.SECURITY,("security","vulnerability","secret")),(TaskType.RELEASE,("release","deploy","publish")),(TaskType.DATA_CHANGE,("migration","schema","database")),(TaskType.CODE_CHANGE,("code","implement","refactor","fix")),(TaskType.RESEARCH,("research","investigate","analyze")))
 matches=[(t,k) for t,keys in rules for k in keys if k in text]
 if not matches:return TaskClassification(TaskType.GENERIC,0.0,("unknown-conservative-generic",),_PROFILES[TaskType.GENERIC])
 types={t for t,_ in matches}
 if len(types)>1:return TaskClassification(TaskType.GENERIC,0.0,("ambiguous-conservative-generic",),_PROFILES[TaskType.GENERIC])
 t=matches[0][0];reasons=tuple(sorted({k for _,k in matches}))
 return TaskClassification(t,min(0.95,0.6+0.1*len(reasons)),reasons,_PROFILES[t])
