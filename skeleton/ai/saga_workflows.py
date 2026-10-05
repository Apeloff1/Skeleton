from dataclasses import dataclass
@dataclass(frozen=True)
class SagaDefinition:
 saga_id:str; steps:tuple[str,...]; idempotency_keys:tuple[str,...]; timeout:int
 def __post_init__(self):
  if not self.saga_id or not self.steps or len(self.steps)!=len(self.idempotency_keys) or len(set(self.steps))!=len(self.steps) or len(set(self.idempotency_keys))!=len(self.idempotency_keys):raise ValueError("saga steps require unique idempotency keys")
  if isinstance(self.timeout,bool) or not isinstance(self.timeout,int) or self.timeout<=0:raise ValueError("positive saga timeout required")
@dataclass(frozen=True)
class SagaInstance: definition:SagaDefinition; completed:tuple[str,...]=(); failed:str|None=None; started_at:int=0
@dataclass(frozen=True)
class SagaTransition: before:SagaInstance; after:SagaInstance; durable:bool=True; reconciliation_required:bool=False
def advance(i,step,now=None):
 if i.failed is not None:raise PermissionError("failed saga requires reconciliation")
 if now is not None and (now<i.started_at or now-i.started_at>=i.definition.timeout):return SagaTransition(i,SagaInstance(i.definition,i.completed,"timeout",i.started_at),True,True)
 if step not in i.definition.steps:raise ValueError("unknown saga step")
 if step in i.completed:return SagaTransition(i,i)
 expected=i.definition.steps[len(i.completed)]
 if step!=expected:raise ValueError("out of order saga transition")
 a=SagaInstance(i.definition,i.completed+(step,),None,i.started_at);return SagaTransition(i,a)
