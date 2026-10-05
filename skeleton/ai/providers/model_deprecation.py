from dataclasses import dataclass
@dataclass(frozen=True)
class ModelConsumer: consumer_id:str; migrated:bool; exception:str|None=None
@dataclass(frozen=True)
class ModelDeprecation: model_id:str; replacement:str; deadline:int; consumers:tuple[ModelConsumer,...]
@dataclass(frozen=True)
class ModelRetirement: model_id:str; retired:bool; reason:str
def retire(d,now):
 if not d.model_id or not d.replacement or d.model_id==d.replacement or isinstance(d.deadline,bool) or not isinstance(d.deadline,int) or d.deadline<0 or isinstance(now,bool) or not isinstance(now,int) or now<0:return ModelRetirement(d.model_id,False,"invalid deprecation record")
 ids=[c.consumer_id for c in d.consumers]
 if len(ids)!=len(set(ids)) or any(not c.consumer_id or not isinstance(c.migrated,bool) for c in d.consumers):return ModelRetirement(d.model_id,False,"invalid consumer inventory")
 pending=[c for c in d.consumers if not c.migrated and not c.exception]
 if pending:return ModelRetirement(d.model_id,False,"supported consumers remain")
 if now<d.deadline:return ModelRetirement(d.model_id,False,"deadline not reached")
 return ModelRetirement(d.model_id,True,"migration complete")
