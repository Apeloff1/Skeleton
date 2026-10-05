from dataclasses import dataclass
@dataclass(frozen=True)
class ModelConsumer: consumer_id:str; migrated:bool; exception:str|None=None
@dataclass(frozen=True)
class ModelDeprecation: model_id:str; replacement:str; deadline:int; consumers:tuple[ModelConsumer,...]
@dataclass(frozen=True)
class ModelRetirement: model_id:str; retired:bool; reason:str
def retire(d,now):
 pending=[c for c in d.consumers if not c.migrated and not c.exception]
 if pending:return ModelRetirement(d.model_id,False,"supported consumers remain")
 if now<d.deadline:return ModelRetirement(d.model_id,False,"deadline not reached")
 return ModelRetirement(d.model_id,True,"migration complete")
