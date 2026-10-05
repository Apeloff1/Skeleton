"""Build, binary, installer and update supply-chain controls VOL-273..277."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .contracts import sha256_json

def _t(v:object,n:str)->str:
 if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} must be non-empty text")
 return v.strip()
def _d(v:object,n:str)->str:
 v=_t(v,n)
 if len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ValueError(f"{n} must be lowercase sha256")
 return v

@dataclass(frozen=True,slots=True)
class BuildInput: name:str; digest:str; source:str
@dataclass(frozen=True,slots=True)
class HermeticPolicy: network_allowed:bool; vendored_network_inputs:tuple[str,...]
@dataclass(frozen=True,slots=True)
class HermeticBuild:
    source_digest:str; toolchain_digest:str; inputs:tuple[BuildInput,...]; policy:HermeticPolicy
    def __post_init__(self):
    object.__setattr__(self,"source_digest",_d(self.source_digest,"source_digest")); object.__setattr__(self,"toolchain_digest",_d(self.toolchain_digest,"toolchain_digest"))
    if len({x.name for x in self.inputs})!=len(self.inputs) or any(not x.name or not x.source for x in self.inputs):raise ValueError("unique build input identity required")
    for x in self.inputs:_d(x.digest,"input_digest")
    if any(not x for x in self.policy.vendored_network_inputs) or len(set(self.policy.vendored_network_inputs))!=len(self.policy.vendored_network_inputs):raise ValueError("unique vendored input identity required")
    if self.policy.network_allowed and not self.policy.vendored_network_inputs: raise ValueError("qualified network build must declare vendored/cached inputs")
    @property
    def identity(self)->str: return sha256_json({"source":self.source_digest,"toolchain":self.toolchain_digest,"inputs":sorted((x.name,x.digest,x.source) for x in self.inputs),"network":self.policy.network_allowed,"vendored":sorted(self.policy.vendored_network_inputs)})

@dataclass(frozen=True,slots=True)
class CachePolicy: shared:bool; sensitive:bool; tenant_id:str|None
    def __post_init__(self):
    if self.shared and (self.sensitive or self.tenant_id): raise ValueError("sensitive or tenant data cannot use shared cache")
@dataclass(frozen=True,slots=True)
class BuildCacheKey:
    source_digest:str; toolchain_digest:str; config_digest:str; dependency_digest:str
    def __post_init__(self):
    for n in ("source_digest","toolchain_digest","config_digest","dependency_digest"): object.__setattr__(self,n,_d(getattr(self,n),n))
    @property
    def key(self)->str: return sha256_json({"source":self.source_digest,"toolchain":self.toolchain_digest,"config":self.config_digest,"deps":self.dependency_digest})
@dataclass(frozen=True,slots=True)
class CachedArtifact: cache_key:str; artifact_digest:str; policy:CachePolicy

@dataclass(frozen=True,slots=True)
class BuildIdentity: source_digest:str; environment_digest:str; toolchain_digest:str
@dataclass(frozen=True,slots=True)
class ArtifactSignature: artifact_digest:str; signer_id:str; signature_digest:str
@dataclass(frozen=True,slots=True)
class BinaryAttestation:
    artifact_digest:str; build:BuildIdentity; signature:ArtifactSignature
    def __post_init__(self):
    object.__setattr__(self,"artifact_digest",_d(self.artifact_digest,"artifact_digest"))
    for n in ("source_digest","environment_digest","toolchain_digest"):_d(getattr(self.build,n),n)
    _d(self.signature.artifact_digest,"signature_artifact_digest");_t(self.signature.signer_id,"signer_id");_d(self.signature.signature_digest,"signature_digest")
    if self.signature.artifact_digest!=self.artifact_digest: raise ValueError("signature must bind attested artifact")
def verify_attestation(a:BinaryAttestation,trusted_signers:tuple[str,...])->bool:
 if len(set(trusted_signers))!=len(trusted_signers) or any(not x for x in trusted_signers):return False
 return a.signature.signer_id in trusted_signers and a.signature.artifact_digest==a.artifact_digest

@dataclass(frozen=True,slots=True)
class InstallerSecurityPolicy: allowed_roots:tuple[str,...]; trusted_signers:tuple[str,...]
@dataclass(frozen=True,slots=True)
class InstallPath: root:str; relative_path:str; contains_symlink:bool=False
    def __post_init__(self):
    _t(self.root,"root");_t(self.relative_path,"relative_path")
    if self.relative_path.startswith("/") or ".." in self.relative_path.split("/"): raise ValueError("install path traversal")
    if self.contains_symlink: raise ValueError("symlink install target rejected")
@dataclass(frozen=True,slots=True)
class InstallVerification: artifact_digest:str; signature_verified:bool; path_verified:bool
    @property
    def privileged_write_allowed(self)->bool: return self.signature_verified and self.path_verified

@dataclass(frozen=True,slots=True)
class VersionFloor:
    minimum_version:int
    def __post_init__(self):
    if self.minimum_version<0:raise ValueError("version floor must be nonnegative")
@dataclass(frozen=True,slots=True)
class UpdateSignature: metadata_digest:str; signer_id:str
@dataclass(frozen=True,slots=True)
class UpdateMetadata:
    version:int; artifact_digest:str; metadata_digest:str; signature:UpdateSignature; authorized_rollback:bool=False
    def __post_init__(self):
    if self.version<0:raise ValueError("update version must be nonnegative")
    object.__setattr__(self,"artifact_digest",_d(self.artifact_digest,"artifact_digest")); object.__setattr__(self,"metadata_digest",_d(self.metadata_digest,"metadata_digest"))
    _d(self.signature.metadata_digest,"signature_metadata_digest");_t(self.signature.signer_id,"signer_id")
    if self.signature.metadata_digest!=self.metadata_digest: raise ValueError("signature must bind update metadata")
def admit_update(m:UpdateMetadata,floor:VersionFloor,trusted_signers:tuple[str,...])->bool:
 if len(set(trusted_signers))!=len(trusted_signers) or any(not x for x in trusted_signers):return False
 if m.signature.signer_id not in trusted_signers: return False
 if m.version<floor.minimum_version and not m.authorized_rollback: return False
 return True
