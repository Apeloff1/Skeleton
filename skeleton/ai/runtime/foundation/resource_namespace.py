"""Canonical scoped resource namespace for VOL-332."""
from dataclasses import dataclass
import re,unicodedata
_NAME=re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")
@dataclass(frozen=True)
class ResourceName:
 value:str
 def __post_init__(self):
  if self.value!=unicodedata.normalize("NFKC",self.value) or not _NAME.fullmatch(self.value) or self.value in {".",".."} or ".." in self.value:raise ValueError("ambiguous or unsafe resource name")
@dataclass(frozen=True)
class ResourceRef:
 tenant:ResourceName; project:ResourceName; version:ResourceName; resource:ResourceName
 def canonical(self):return f"res1:{self.tenant.value}:{self.project.value}:{self.version.value}:{self.resource.value}"
@dataclass(frozen=True)
class ResourceNamespace:
 tenant:ResourceName; project:ResourceName; version:ResourceName
 def resolve(self,name:ResourceName):return ResourceRef(self.tenant,self.project,self.version,name)
def parse_resource_ref(raw:str):
 if not isinstance(raw,str) or raw!=raw.lower() or raw!=unicodedata.normalize("NFKC",raw):raise ValueError("noncanonical resource ref")
 p=raw.split(":")
 if len(p)!=5 or p[0]!="res1":raise ValueError("invalid resource ref")
 r=ResourceRef(*(ResourceName(x) for x in p[1:]))
 if r.canonical()!=raw:raise ValueError("noncanonical resource ref")
 return r
