from dataclasses import dataclass
import math
@dataclass(frozen=True)
class VectorIndexVersion:
 name:str; version:str; embedding_space:str
@dataclass(frozen=True)
class IndexValidation:
 recall:float; freshness:float; complete:bool
 def __post_init__(self):
  if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1 for x in (self.recall,self.freshness)) or not isinstance(self.complete,bool):raise ValueError("invalid index validation")
@dataclass(frozen=True)
class IndexMigration:
 active:VectorIndexVersion; shadow:VectorIndexVersion; validation:IndexValidation; promoted:bool=False
 def promote(self,min_recall,min_freshness):
  if self.active==self.shadow:raise ValueError("shadow index must differ from active")
  if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1 for x in (min_recall,min_freshness)):raise ValueError("invalid promotion threshold")
  if self.active.embedding_space!=self.shadow.embedding_space:raise ValueError("mixed embedding routing")
  if not self.validation.complete or self.validation.recall<min_recall or self.validation.freshness<min_freshness:raise PermissionError("shadow index validation failed")
  return IndexMigration(self.active,self.shadow,self.validation,True)
 def route(self):return self.shadow if self.promoted else self.active
 def rollback(self):return IndexMigration(self.active,self.shadow,self.validation,False)
