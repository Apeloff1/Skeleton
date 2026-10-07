from dataclasses import dataclass
import math
@dataclass(frozen=True)
class EmbeddingVersion:
 model:str; version:str; dimension:int; preprocessing:str
 def __post_init__(self):
  if not self.model or not self.version or not self.preprocessing or isinstance(self.dimension,bool) or not isinstance(self.dimension,int) or self.dimension<=0:raise ValueError("valid embedding identity and dimension required")
@dataclass(frozen=True)
class EmbeddingRecord:
 record_id:str; space:EmbeddingVersion; vector:tuple[float,...]; retired:bool=False
 def __post_init__(self):
  if len(self.vector)!=self.space.dimension:raise ValueError("embedding dimension mismatch")
  if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in self.vector):raise ValueError("embedding vector must be finite numeric")
@dataclass(frozen=True)
class EmbeddingMigration:
 source:EmbeddingVersion; target:EmbeddingVersion; complete:bool
def comparable(a,b):
 if a.retired or b.retired:raise ValueError("retired embedding")
 if a.space!=b.space:raise ValueError("mixed embedding spaces")
 return True
