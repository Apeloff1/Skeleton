"""Permissioned reversible plugin lifecycle for VOL-162."""
from __future__ import annotations
from dataclasses import dataclass,replace
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class PluginError(ValueError):pass
class PluginState(str,Enum): INSTALLED="installed";ACTIVE="active";DISABLED="disabled";REMOVED="removed"
@dataclass(frozen=True,slots=True)
class PluginManifest:
 plugin_id:str;package_digest:str;capabilities:frozenset[str];permissions:frozenset[str];api_version:int
 def __post_init__(self):
  if not _ID.fullmatch(self.plugin_id) or not _SHA.fullmatch(self.package_digest) or self.api_version<1:raise PluginError("invalid manifest")
  if not self.capabilities:raise PluginError("capabilities required")
@dataclass(frozen=True,slots=True)
class PluginGrant:
 plugin_id:str;permissions:frozenset[str];grant_digest:str
 def __post_init__(self):
  if not _SHA.fullmatch(self.grant_digest):raise PluginError("grant digest required")
@dataclass(frozen=True,slots=True)
class PluginLifecycle:
 manifest:PluginManifest;state:PluginState=PluginState.INSTALLED
 def activate(self,grant,supported_api):
  if self.state is PluginState.REMOVED:raise PluginError("removed plugin")
  if self.manifest.api_version not in supported_api:raise PluginError("incompatible plugin")
  if grant.plugin_id!=self.manifest.plugin_id or not grant.permissions<=self.manifest.permissions:raise PluginError("permission grant mismatch")
  return replace(self,state=PluginState.ACTIVE)
 def disable(self):
  if self.state is PluginState.REMOVED:raise PluginError("removed plugin")
  return replace(self,state=PluginState.DISABLED)
 def remove(self):return replace(self,state=PluginState.REMOVED)