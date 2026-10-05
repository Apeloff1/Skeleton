from dataclasses import dataclass
import math
@dataclass(frozen=True)
class Scorer: name:str; version:str; dependencies:tuple[str,...]
@dataclass(frozen=True)
class EvaluationResult: scorer:str; score:float; model_id:str; config_id:str; environment_id:str
@dataclass(frozen=True)
class EvaluationSDK:
 model_id:str; config_id:str; environment_id:str
 def run(self,scorer,inputs,fn):
  if not all((self.model_id,self.config_id,self.environment_id,scorer.name,scorer.version)) or any(not x for x in scorer.dependencies):raise ValueError("complete evaluation identity required")
  score=fn(inputs)
  if isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score):raise TypeError("scorer output must be numeric")
  return EvaluationResult(f"{scorer.name}@{scorer.version}",float(score),self.model_id,self.config_id,self.environment_id)
