from dataclasses import dataclass
@dataclass(frozen=True)
class CompensationStep: step_id:str; effect_id:str; action:str
@dataclass(frozen=True)
class Compensation:
 operation_id:str; steps:tuple[CompensationStep,...]
 def __post_init__(self):
  ids=[s.step_id for s in self.steps];effects=[s.effect_id for s in self.steps]
  if not self.operation_id or not self.steps or len(ids)!=len(set(ids)) or len(effects)!=len(set(effects)) or any(not s.action for s in self.steps):raise ValueError("valid unique compensation steps required")
@dataclass(frozen=True)
class CompensationResult: operation_id:str; completed:tuple[str,...]; failed:tuple[str,...]; rolled_back:bool=False; reconciliation_required:bool=False
def execute(c,fn):
 done=[];failed=[]
 for s in c.steps:
  try: fn(s);done.append(s.step_id)
  except Exception:
   failed.append(s.step_id);break
 return CompensationResult(c.operation_id,tuple(done),tuple(failed),False,bool(failed))
