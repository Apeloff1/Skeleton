from dataclasses import dataclass
@dataclass(frozen=True)
class BenchmarkManifest:
 plugin:str; version:str; dataset_id:str; dataset_rights:bool; max_resources:int
@dataclass(frozen=True)
class BenchmarkPlugin:
 manifest:BenchmarkManifest; entrypoint:str
@dataclass(frozen=True)
class BenchmarkExecution:
 plugin_identity:str; dataset_id:str; admitted:bool
def admit(plugin,resource_request,allowed_entrypoints):
 m=plugin.manifest
 if not m.dataset_rights or resource_request>m.max_resources or plugin.entrypoint not in allowed_entrypoints:
  raise PermissionError("benchmark admission denied")
 return BenchmarkExecution(f"{m.plugin}@{m.version}",m.dataset_id,True)
