from dataclasses import dataclass
@dataclass(frozen=True)
class VectorIndexVersion:
 name:str; version:str; embedding_space:str
@dataclass(frozen=True)
class IndexValidation:
 recall:float; freshness:float; complete:bool
@dataclass(frozen=True)
class IndexMigration:
 active:VectorIndexVersion; shadow:VectorIndexVersion; validation:IndexValidation; promoted:bool=False
 def promote(self,min_recall,min_freshness):
  if self.active.embedding_space!=self.shadow.embedding_space:raise ValueError("mixed embedding routing")
  if not self.validation.complete or self.validation.recall<min_recall or self.validation.freshness<min_freshness:raise PermissionError("shadow index validation failed")
  return IndexMigration(self.active,self.shadow,self.validation,True)
 def route(self):return self.shadow if self.promoted else self.active
 def rollback(self):return IndexMigration(self.active,self.shadow,self.validation,False)
