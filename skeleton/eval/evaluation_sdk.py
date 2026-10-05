from dataclasses import dataclass
@dataclass(frozen=True)
class Scorer: name:str; version:str; dependencies:tuple[str,...]
@dataclass(frozen=True)
class EvaluationResult: scorer:str; score:float; model_id:str; config_id:str; environment_id:str
@dataclass(frozen=True)
class EvaluationSDK:
 model_id:str; config_id:str; environment_id:str
 def run(self,scorer,inputs,fn):
  score=fn(inputs)
  if not isinstance(score,(int,float)):raise TypeError("scorer output must be numeric")
  return EvaluationResult(f"{scorer.name}@{scorer.version}",float(score),self.model_id,self.config_id,self.environment_id)
