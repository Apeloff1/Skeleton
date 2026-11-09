"""Jeeves app-wide capability discovery and least-privilege action planning.

The inventory describes code surfaces; it NEVER treats a Python module as an
automatically safe executable tool. UI/editor/forge/crawler operations require
a separately registered, reviewed adapter with a typed schema.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import PurePosixPath

DOMAINS={
 "forges":r"forge|asset_builder|construct",
 "editors":r"editor|workbench|workspace",
 "directors":r"director|orchestrat|pipeline",
 "game_building":r"game_builder|gameforge|engine|world|scene",
 "crawlers":r"crawl|scrap|rss|research|source",
 "companion":r"companion|dragon|hatchling",
 "learning_weights":r"weight|learn|train|model|almanac",
 "internal_systems":r"runtime|supervisor|memory|evidence|assurance|security",
 "user_interface":r"frontend|/ui/|routes|screens|components",
 "internal_filetree":r"filetree|filesystem|repository|organization",
}
DENY=("secrets/","credentials/","private/","node_modules/",
      ".git/","__pycache__/")
EXTS={".py",".ts",".tsx",".js",".jsx",".json",".yaml",".yml",".md"}
MAX_ENTRIES=100000


def discover(paths):
    """Deterministic coverage inventory with explicit non-executable status."""
    rows=[]
    for path in paths:
        if not isinstance(path,str) or len(path)>500 or "\\" in path:
            raise ValueError("unsafe inventory path")
        part=PurePosixPath(path)
        if part.is_absolute() or ".." in part.parts or not part.parts:
            raise ValueError("path escapes repository")
        if any(segment.startswith(".") and segment not in
               (".github",) for segment in part.parts):
            continue
        if any(prefix in path.lower() for prefix in DENY):
            continue
        if part.suffix.lower() not in EXTS:
            continue
        domains=[key for key,pattern in DOMAINS.items()
                 if re.search(pattern,path,re.I)]
        if domains:
            rows.append({"path":path,"domains":domains,
                         "executable_by_jeeves":False,
                         "adapter_registered":False,
                         "access":"discover_only"})
        if len(rows)>MAX_ENTRIES:
            raise ValueError("inventory exceeds bounded review capacity")
    rows.sort(key=lambda x:x["path"])
    if len({x["path"] for x in rows})!=len(rows):
        raise ValueError("duplicate repository paths")
    counts={key:sum(key in row["domains"] for row in rows)
            for key in DOMAINS}
    body={"schema":"skeleton.jeeves.app_surface_inventory.v1",
          "total":len(rows),"domain_counts":counts,"surfaces":rows,
          "full_runtime_capability_proven":False}
    raw=json.dumps(body,sort_keys=True,separators=(",",":")).encode()
    return {**body,"sha256":hashlib.sha256(raw).hexdigest()}


class CapabilityRegistry:
    """Only explicitly registered, permissioned adapters may execute."""
    def __init__(self):
        self._tools={}
    def register(self,name,adapter,*,domain,mutates=False):
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,80}",name):
            raise ValueError("invalid capability identifier")
        if name in self._tools or domain not in DOMAINS or not callable(adapter):
            raise ValueError("invalid or duplicate registered adapter")
        self._tools[name]=(adapter,domain,bool(mutates))
    def describe(self):
        return [{"name":name,"domain":domain,"mutates":mutates}
                for name,(_,domain,mutates) in sorted(self._tools.items())]
    def execute(self,name,payload,*,authorized=False,approved=False,
                dry_run=True):
        if name not in self._tools:
            raise PermissionError("unregistered application capability")
        if not isinstance(payload,dict) or len(payload)>32:
            raise ValueError("bounded typed adapter arguments required")
        adapter,domain,mutates=self._tools[name]
        if not authorized or (mutates and not approved):
            raise PermissionError("explicit authority and edit approval required")
        if dry_run:
            return {"tool":name,"domain":domain,"would_mutate":mutates,
                    "executed":False,"approval_required":mutates}
        return adapter(payload)
