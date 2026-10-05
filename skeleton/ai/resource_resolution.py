from dataclasses import dataclass
import re
@dataclass(frozen=True)
class ResourceQuery: tenant:str; project:str; name:str; version:str|None
@dataclass(frozen=True)
class ResourceHandle: canonical_ref:str; lifecycle:str
@dataclass(frozen=True)
class ResolutionReceipt: query:ResourceQuery; resolved_ref:str; alias_used:bool
def _version_key(v):
 parts=re.findall(r"\d+|[^\d]+",v)
 return tuple((0,int(x)) if x.isdigit() else (1,x) for x in parts)
def resolve_resource(q,registry,*,authorized):
 if not q.tenant or not q.project or not q.name or q.version=="":raise ValueError("complete resource query required")
 if authorized is not True:raise PermissionError("resolution authority denied")
 registry=tuple(registry)
 required={"tenant","project","name","version","lifecycle"}
 if any(not isinstance(x,dict) or not required.issubset(x) for x in registry):raise ValueError("malformed resource registry")
 matches=[x for x in registry if x["tenant"]==q.tenant and x["project"]==q.project and x["name"]==q.name and x["lifecycle"]=="active"]
 if q.version is not None:matches=[x for x in matches if x["version"]==q.version]
 if not matches:raise KeyError("resource not found")
 alias=q.version is None
 if alias:matches=sorted(matches,key=lambda x:_version_key(x["version"]))
 if not alias and len(matches)!=1:raise ValueError("ambiguous resource")
 x=matches[-1];ref=f"res1:{x['tenant']}:{x['project']}:{x['version']}:{x['name']}"
 return ResourceHandle(ref,x["lifecycle"]),ResolutionReceipt(q,ref,alias)
