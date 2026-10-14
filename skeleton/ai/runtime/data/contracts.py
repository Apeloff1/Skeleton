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
 def __post_init__(self):
  names=[x.name for x in self.fields];cons=[x.consumer_id for x in self.consumers]
  if not self.contract_id or not self.version or len(names)!=len(set(names)) or len(cons)!=len(set(cons)) or isinstance(self.freshness_seconds,bool) or not isinstance(self.freshness_seconds,int) or self.freshness_seconds<0:raise ValueError("valid unique data contract required")
  if any(not all((x.name,x.meaning,x.unit,x.classification)) or not isinstance(x.nullable,bool) for x in self.fields):raise ValueError("complete field semantics required")
def breaking_change(old,new):
 a={x.name:x for x in old.fields};b={x.name:x for x in new.fields}
 return tuple(sorted(k for k in a if k not in b or a[k]!=b[k]))
def require_migration(old,new):
 impacted=breaking_change(old,new)
 if impacted and not old.consumers:raise ValueError("breaking change lacks consumer inventory")
 return impacted
