"""Minimal fail-closed workflow DSL for VOL-307."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
class DSLVersion(str,Enum): V1="workflow/v1"
@dataclass(frozen=True)
class DSLDiagnostic:
 line:int; code:str; message:str
@dataclass(frozen=True)
class WorkflowSource:
 version:DSLVersion; source:str
@dataclass(frozen=True)
class ParsedStep:
 step_id:str; capability:str; authority:str
_LINE=re.compile(r"^step ([a-z0-9_-]+) capability=([a-z0-9_.:-]+) authority=([a-z0-9_.:-]+)$")
def parse_workflow(source:WorkflowSource,declared_capabilities:set[str],declared_authorities:set[str]):
 if source.version is not DSLVersion.V1:return (),(DSLDiagnostic(1,"version","unsupported version"),)
 steps=[];diags=[];seen=set()
 for no,raw in enumerate(source.source.splitlines(),1):
  if not raw or raw.startswith("#"):continue
  m=_LINE.fullmatch(raw)
  if not m:diags.append(DSLDiagnostic(no,"syntax","expected canonical step declaration"));continue
  sid,cap,auth=m.groups()
  if sid in seen:diags.append(DSLDiagnostic(no,"duplicate-step",sid));continue
  seen.add(sid)
  if cap not in declared_capabilities:diags.append(DSLDiagnostic(no,"undeclared-capability",cap));continue
  if auth not in declared_authorities:diags.append(DSLDiagnostic(no,"undeclared-authority",auth));continue
  steps.append(ParsedStep(sid,cap,auth))
 return (tuple(steps),tuple(diags)) if not diags else ((),tuple(diags))
