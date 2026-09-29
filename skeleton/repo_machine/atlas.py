"""Deterministic human/machine repository information architecture.
The atlas is derived from the live repository model plus the canonical
.machine/repository.toml zone policy. It is metadata-only and never imports,
executes, moves, or rewrites repository content.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import PurePosixPath
from .config import MachineConfig
from .model import RepositoryModel, ZoneRule

@dataclass(frozen=True, slots=True)
class PathPlacement:
    path: str; zone: str; owner: str; criticality: str; audience: str; lifecycle: str; purpose: str; matched_prefix: str
    def as_dict(self)->dict[str,str]:
        return {"path":self.path,"zone":self.zone,"owner":self.owner,"criticality":self.criticality,"audience":self.audience,"lifecycle":self.lifecycle,"purpose":self.purpose,"matched_prefix":self.matched_prefix}

@dataclass(frozen=True, slots=True)
class AtlasZone:
    name: str; owner: str; criticality: str; audience: str; lifecycle: str; purpose: str; prefixes: tuple[str,...]; file_count:int; code_files:int; test_files:int; workflow_files:int; total_lines:int; dependencies:tuple[str,...]; dependents:tuple[str,...]
    def as_dict(self)->dict[str,object]:
        return {"name":self.name,"owner":self.owner,"criticality":self.criticality,"audience":self.audience,"lifecycle":self.lifecycle,"purpose":self.purpose,"prefixes":list(self.prefixes),"file_count":self.file_count,"code_files":self.code_files,"test_files":self.test_files,"workflow_files":self.workflow_files,"total_lines":self.total_lines,"dependencies":list(self.dependencies),"dependents":list(self.dependents)}

@dataclass(frozen=True, slots=True)
class RepositoryAtlas:
    schema_version:int; repository:str; repository_fingerprint:str; contract:str; zones:tuple[AtlasZone,...]; unclassified_count:int; unclassified_roots:tuple[str,...]; truncated:bool
    def as_dict(self)->dict[str,object]:
        return {"schema_version":self.schema_version,"repository":self.repository,"repository_fingerprint":self.repository_fingerprint,"contract":self.contract,"classification":{"first_match_wins":True,"fallback_zone":"unclassified","unclassified_count":self.unclassified_count,"unclassified_roots":list(self.unclassified_roots),"truncated":self.truncated},"zones":[item.as_dict() for item in self.zones]}

def _canonical_path(path:str)->str:
    if not isinstance(path,str): raise TypeError("path must be text")
    normalized=path.replace("\\","/")
    if not normalized or normalized!=normalized.strip("/"): raise ValueError("path must be canonical and repository-relative")
    posix=PurePosixPath(normalized)
    if posix.is_absolute() or any(part in {"",".",".."} for part in posix.parts) or posix.as_posix()!=normalized: raise ValueError("path must be canonical and repository-relative")
    return normalized

def placement_for_path(config:MachineConfig,path:str)->PathPlacement:
    normalized=_canonical_path(path)
    for rule in config.zones:
        if rule.matches(normalized):
            matches=tuple(prefix for prefix in rule.prefixes if normalized==prefix.rstrip("/") or normalized.startswith(prefix))
            return PathPlacement(normalized,rule.name,rule.owner,rule.criticality,rule.audience,rule.lifecycle,rule.purpose,max(matches,key=len))
    return PathPlacement(normalized,"unclassified",config.default_owner,"medium","internal","transitional","Path is not covered by the canonical repository taxonomy.","")

def _atlas_zone(rule:ZoneRule,subsystem:object|None)->AtlasZone:
    if subsystem is None: return AtlasZone(rule.name,rule.owner,rule.criticality,rule.audience,rule.lifecycle,rule.purpose,rule.prefixes,0,0,0,0,0,(),())
    return AtlasZone(rule.name,rule.owner,rule.criticality,rule.audience,rule.lifecycle,rule.purpose,rule.prefixes,subsystem.file_count,subsystem.code_files,subsystem.test_files,subsystem.workflow_files,subsystem.total_lines,subsystem.dependencies,subsystem.dependents)

def build_repository_atlas(model:RepositoryModel,config:MachineConfig)->RepositoryAtlas:
    by_name={item.name:item for item in model.subsystems}
    roots=tuple(sorted({PurePosixPath(record.path).parts[0] for record in model.files if record.zone=="unclassified" and PurePosixPath(record.path).parts}))
    return RepositoryAtlas(1,model.repository,model.fingerprint,".machine/repository.toml",tuple(_atlas_zone(rule,by_name.get(rule.name)) for rule in config.zones),model.unclassified_count,roots,model.truncated)
