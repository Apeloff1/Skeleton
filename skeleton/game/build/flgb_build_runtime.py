"""FLGB-16 deterministic asset, build, export, performance, and test contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Sequence
MAX_ID=256; MAX_ITEMS=100000; MAX_BYTES=2**63-1; MAX_SCORE=1000000
class BuildContractError(ValueError): pass
def _int(v): return isinstance(v,int) and not isinstance(v,bool)
def req_id(v,n):
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID: raise BuildContractError(f"invalid {n}")
    return v
def req_digest(v,n):
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise BuildContractError(f"invalid {n}")
    return v
def dig(v):
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode()
    except (TypeError,ValueError) as exc: raise BuildContractError("non-canonical value") from exc
    return sha256(raw).hexdigest()
@dataclass(frozen=True)
class AssetImportReceipt:
    asset_id:str; source_digest:str; importer_id:str; importer_version:str; output_digest:str; provenance_digest:str
    def __post_init__(self): req_id(self.asset_id,"asset_id"); req_digest(self.source_digest,"source_digest"); req_id(self.importer_id,"importer_id"); req_id(self.importer_version,"importer_version"); req_digest(self.output_digest,"output_digest"); req_digest(self.provenance_digest,"provenance_digest")
    @property
    def digest(self): return dig(self.__dict__)
@dataclass(frozen=True)
class NormalizedAsset:
    asset_id:str; input_digest:str; canonical_format:str; normalized_digest:str; normalization_version:str
    def __post_init__(self): req_id(self.asset_id,"asset_id"); req_digest(self.input_digest,"input_digest"); req_id(self.canonical_format,"canonical_format"); req_digest(self.normalized_digest,"normalized_digest"); req_id(self.normalization_version,"normalization_version")
@dataclass(frozen=True)
class BuildNode:
    node_id:str; input_digest:str; dependencies:tuple[str,...]
    def __post_init__(self):
        req_id(self.node_id,"node_id"); req_digest(self.input_digest,"input_digest"); deps=tuple(sorted(self.dependencies))
        if self.node_id in deps or len(set(deps))!=len(deps): raise BuildContractError("invalid dependencies")
        for d in deps: req_id(d,"dependency")
        object.__setattr__(self,"dependencies",deps)
class DependencyGraph:
    def __init__(self,nodes:Sequence[BuildNode]):
        by={n.node_id:n for n in nodes}
        if len(by)!=len(nodes): raise BuildContractError("duplicate build node")
        for n in nodes:
            if set(n.dependencies)-set(by): raise BuildContractError("missing build dependency")
        self._nodes=MappingProxyType(by); self.order=self._topo()
    def _topo(self):
        rem=set(self._nodes); done=[]
        while rem:
            ready=sorted(n for n in rem if set(self._nodes[n].dependencies).issubset(done))
            if not ready: raise BuildContractError("dependency cycle")
            done.extend(ready); rem.difference_update(ready)
        return tuple(done)
    @property
    def digest(self): return dig([{"node_id":n,"input_digest":self._nodes[n].input_digest,"dependencies":list(self._nodes[n].dependencies)} for n in self.order])
@dataclass(frozen=True)
class ContentAddress:
    namespace:str; algorithm:str; digest:str
    def __post_init__(self):
        req_id(self.namespace,"namespace")
        if self.algorithm!="sha256": raise BuildContractError("unsupported content-address algorithm")
        req_digest(self.digest,"digest")
    @property
    def uri(self): return f"ca://{self.namespace}/{self.algorithm}/{self.digest}"
def incremental_rebuild(graph:DependencyGraph,changed_nodes:Sequence[str])->tuple[str,...]:
    changed=set(changed_nodes)
    for n in changed: req_id(n,"changed_node")
    if changed-set(graph._nodes): raise BuildContractError("unknown changed node")
    impacted=set(changed); grew=True
    while grew:
        grew=False
        for n,node in graph._nodes.items():
            if n not in impacted and set(node.dependencies)&impacted: impacted.add(n); grew=True
    return tuple(n for n in graph.order if n in impacted)
@dataclass(frozen=True)
class ShaderBakeReceipt:
    shader_id:str; source_digest:str; compiler_digest:str; target:str; binary_digest:str
    def __post_init__(self): req_id(self.shader_id,"shader_id"); req_digest(self.source_digest,"source_digest"); req_digest(self.compiler_digest,"compiler_digest"); req_id(self.target,"target"); req_digest(self.binary_digest,"binary_digest")
@dataclass(frozen=True)
class PackageManifest:
    package_id:str; version:str; entry_digests:tuple[str,...]; build_graph_digest:str; signing_digest:str|None
    def __post_init__(self):
        req_id(self.package_id,"package_id"); req_id(self.version,"version"); req_digest(self.build_graph_digest,"build_graph_digest")
        entries=tuple(sorted(self.entry_digests))
        if not entries or len(set(entries))!=len(entries): raise BuildContractError("invalid package entries")
        for d in entries: req_digest(d,"entry_digest")
        object.__setattr__(self,"entry_digests",entries)
        if self.signing_digest is not None: req_digest(self.signing_digest,"signing_digest")
    @property
    def digest(self): return dig({"package_id":self.package_id,"version":self.version,"entry_digests":list(self.entry_digests),"build_graph_digest":self.build_graph_digest,"signing_digest":self.signing_digest})
@dataclass(frozen=True)
class PlatformExport:
    export_id:str; package_digest:str; platform:str; architecture:str; toolchain_digest:str; artifact_digest:str
    def __post_init__(self): req_id(self.export_id,"export_id"); req_digest(self.package_digest,"package_digest"); req_id(self.platform,"platform"); req_id(self.architecture,"architecture"); req_digest(self.toolchain_digest,"toolchain_digest"); req_digest(self.artifact_digest,"artifact_digest")
@dataclass(frozen=True)
class PerformanceBudget:
    metric_id:str; maximum:int; unit:str
    def __post_init__(self): req_id(self.metric_id,"metric_id"); req_id(self.unit,"unit");
    def allows(self,value:int)->bool:
        if not _int(value) or value<0 or not _int(self.maximum) or self.maximum<0: raise BuildContractError("invalid performance value")
        return value<=self.maximum
@dataclass(frozen=True)
class MemoryBudget:
    pool_id:str; maximum_bytes:int; reserve_bytes:int
    def __post_init__(self):
        req_id(self.pool_id,"pool_id")
        if not _int(self.maximum_bytes) or not 1<=self.maximum_bytes<=MAX_BYTES or not _int(self.reserve_bytes) or not 0<=self.reserve_bytes<self.maximum_bytes: raise BuildContractError("invalid memory budget")
    def available(self,used_bytes:int)->int:
        if not _int(used_bytes) or used_bytes<0: raise BuildContractError("invalid used_bytes")
        return max(0,self.maximum_bytes-self.reserve_bytes-used_bytes)
@dataclass(frozen=True)
class PlaytestResult:
    scenario_id:str; seed_digest:str; terminal_state_digest:str; passed:bool; assertion_digest:str
    def __post_init__(self): req_id(self.scenario_id,"scenario_id"); req_digest(self.seed_digest,"seed_digest"); req_digest(self.terminal_state_digest,"terminal_state_digest"); req_digest(self.assertion_digest,"assertion_digest");
@dataclass(frozen=True)
class ReleaseArtifact:
    artifact_digest:str; provenance_digest:str; signature_digest:str|None; sbom_digest:str; test_evidence_digest:str
    def __post_init__(self):
        req_digest(self.artifact_digest,"artifact_digest"); req_digest(self.provenance_digest,"provenance_digest"); req_digest(self.sbom_digest,"sbom_digest"); req_digest(self.test_evidence_digest,"test_evidence_digest")
        if self.signature_digest is not None: req_digest(self.signature_digest,"signature_digest")
def verify_release_artifact(artifact:ReleaseArtifact,require_signature:bool=True)->bool:
    if require_signature and artifact.signature_digest is None: return False
    return True
