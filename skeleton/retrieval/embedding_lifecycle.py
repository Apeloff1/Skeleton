from dataclasses import dataclass
@dataclass(frozen=True)
class EmbeddingVersion:
 model:str; version:str; dimension:int; preprocessing:str
@dataclass(frozen=True)
class EmbeddingRecord:
 record_id:str; space:EmbeddingVersion; vector:tuple[float,...]; retired:bool=False
 def __post_init__(self):
  if len(self.vector)!=self.space.dimension:raise ValueError("embedding dimension mismatch")
@dataclass(frozen=True)
class EmbeddingMigration:
 source:EmbeddingVersion; target:EmbeddingVersion; complete:bool
def comparable(a,b):
 if a.retired or b.retired:raise ValueError("retired embedding")
 if a.space!=b.space:raise ValueError("mixed embedding spaces")
 return True
