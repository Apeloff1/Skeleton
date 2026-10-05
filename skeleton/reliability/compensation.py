from dataclasses import dataclass
@dataclass(frozen=True)
class CompensationStep: step_id:str; effect_id:str; action:str
@dataclass(frozen=True)
class Compensation: operation_id:str; steps:tuple[CompensationStep,...]
@dataclass(frozen=True)
class CompensationResult: operation_id:str; completed:tuple[str,...]; failed:tuple[str,...]; rolled_back:bool=False
def execute(c,fn):
 done=[];failed=[]
 for s in c.steps:
  try: fn(s);done.append(s.step_id)
  except Exception:failed.append(s.step_id)
 return CompensationResult(c.operation_id,tuple(done),tuple(failed),False)
