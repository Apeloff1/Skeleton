from dataclasses import dataclass
@dataclass(frozen=True)
class ToolCapability: name:str; schema:str
@dataclass(frozen=True)
class ManifestAttestation: signer:str; digest:str; trusted:bool
@dataclass(frozen=True)
class ToolManifest: tool_id:str; capabilities:tuple[ToolCapability,...]; signed:bool=False; attestation:ManifestAttestation|None=None
@dataclass(frozen=True)
class ToolDiscoveryResult: manifest:ToolManifest; validated:bool; granted_authority:frozenset[str]=frozenset()
def validate_manifest(m,allowed):
 names=[c.name for c in m.capabilities]
 a=m.attestation
 if not m.tool_id or not names or len(names)!=len(set(names)) or any(not c.name or not c.schema for c in m.capabilities):return ToolDiscoveryResult(m,False)
 if a is None or not a.signer or not a.digest or a.trusted is not True:return ToolDiscoveryResult(m,False)
 if any(c.name not in allowed for c in m.capabilities):return ToolDiscoveryResult(m,False)
 return ToolDiscoveryResult(m,True)
