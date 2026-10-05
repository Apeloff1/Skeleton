from dataclasses import dataclass
@dataclass(frozen=True)
class DataField:
 name:str; meaning:str; nullable:bool; unit:str; classification:str
@dataclass(frozen=True)
class DataConsumer:
 consumer_id:str; accepted_version:str
@dataclass(frozen=True)
class DataContract:
 contract_id:str; version:str; fields:tuple[DataField,...]; freshness_seconds:int; consumers:tuple[DataConsumer,...]
def breaking_change(old,new):
 a={x.name:x for x in old.fields};b={x.name:x for x in new.fields}
 return tuple(sorted(k for k in a if k not in b or a[k]!=b[k]))
def require_migration(old,new):
 impacted=breaking_change(old,new)
 if impacted and not old.consumers:raise ValueError("breaking change lacks consumer inventory")
 return impacted
