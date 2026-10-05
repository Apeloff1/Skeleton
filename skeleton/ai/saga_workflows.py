from dataclasses import dataclass
@dataclass(frozen=True)
class SagaDefinition: saga_id:str; steps:tuple[str,...]; idempotency_keys:tuple[str,...]; timeout:int
@dataclass(frozen=True)
class SagaInstance: definition:SagaDefinition; completed:tuple[str,...]=(); failed:str|None=None
@dataclass(frozen=True)
class SagaTransition: before:SagaInstance; after:SagaInstance; durable:bool=True
def advance(i,step):
 if step not in i.definition.steps:raise ValueError("unknown saga step")
 if step in i.completed:return SagaTransition(i,i)
 expected=i.definition.steps[len(i.completed)]
 if step!=expected:raise ValueError("out of order saga transition")
 a=SagaInstance(i.definition,i.completed+(step,),None);return SagaTransition(i,a)
