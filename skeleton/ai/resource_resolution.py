from dataclasses import dataclass
@dataclass(frozen=True)
class ResourceQuery: tenant:str; project:str; name:str; version:str|None
@dataclass(frozen=True)
class ResourceHandle: canonical_ref:str; lifecycle:str
@dataclass(frozen=True)
class ResolutionReceipt: query:ResourceQuery; resolved_ref:str; alias_used:bool
def resolve_resource(q,registry,*,authorized):
 if not authorized:raise PermissionError("resolution authority denied")
 matches=[x for x in registry if x["tenant"]==q.tenant and x["project"]==q.project and x["name"]==q.name and x["lifecycle"]=="active"]
 if q.version is not None:matches=[x for x in matches if x["version"]==q.version]
 if not matches:raise KeyError("resource not found")
 alias=q.version is None
 if alias:matches=sorted(matches,key=lambda x:x["version"])
 if not alias and len(matches)!=1:raise ValueError("ambiguous resource")
 x=matches[-1]
 ref=f"res1:{x['tenant']}:{x['project']}:{x['version']}:{x['name']}"
 return ResourceHandle(ref,x["lifecycle"]),ResolutionReceipt(q,ref,alias)
