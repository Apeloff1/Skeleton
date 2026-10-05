from dataclasses import dataclass
@dataclass(frozen=True)
class SDKVersion: api_version:str
@dataclass(frozen=True)
class SDKMethod: name:str; http_method:str; path:str; auth_required:bool
@dataclass(frozen=True)
class ClientSDK: version:SDKVersion; methods:tuple[SDKMethod,...]
def generate_client(api_version,operations):
 methods=[]
 for op in operations:
  if op.get("api_version")!=api_version:raise ValueError("operation contract version drift")
  if "auth_required" not in op:raise ValueError("auth semantics must be explicit")
  methods.append(SDKMethod(op["name"],op["method"],op["path"],op["auth_required"]))
 return ClientSDK(SDKVersion(api_version),tuple(sorted(methods,key=lambda x:x.name)))
def check_compatibility(client,server_operations):
 expected={(x.name,x.http_method,x.path,x.auth_required) for x in client.methods}
 actual={(x["name"],x["method"],x["path"],x["auth_required"]) for x in server_operations if x.get("api_version")==client.version.api_version}
 return expected==actual
