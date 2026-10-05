from dataclasses import dataclass
@dataclass(frozen=True)
class ToolCapability: name:str; schema:str
@dataclass(frozen=True)
class ToolManifest: tool_id:str; capabilities:tuple[ToolCapability,...]; signed:bool
@dataclass(frozen=True)
class ToolDiscoveryResult: manifest:ToolManifest; validated:bool; granted_authority:frozenset[str]=frozenset()
def validate_manifest(m,allowed):
 if not m.signed:return ToolDiscoveryResult(m,False)
 if any(c.name not in allowed for c in m.capabilities):return ToolDiscoveryResult(m,False)
 return ToolDiscoveryResult(m,True)
