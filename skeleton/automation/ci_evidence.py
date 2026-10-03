"""Fail-closed normalized exact-head CI evidence."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,asdict
from typing import Iterable,Mapping,Any
SUCCESS={"success","neutral","skipped"}
@dataclass(frozen=True)
class Gate:
 name:str; status:str; conclusion:str|None; run_id:int
@dataclass(frozen=True)
class CIEvidence:
 head_sha:str; gates:tuple[Gate,...]; required:tuple[str,...]
 def validate(self):
  if len(self.head_sha)!=40 or any(c not in "0123456789abcdef" for c in self.head_sha):raise ValueError("CI head malformed")
  names=[g.name for g in self.gates]
  if len(names)!=len(set(names)):raise ValueError("duplicate CI gate evidence")
  missing=set(self.required)-set(names)
  if missing:raise ValueError(f"missing required CI gates: {sorted(missing)}")
 def failures(self):return tuple(g for g in self.gates if g.name in self.required and g.conclusion not in SUCCESS)
 def green(self):
  self.validate()
  return all(g.status=="completed" and g.conclusion in SUCCESS for g in self.gates if g.name in self.required)
 def digest(self):
  self.validate(); return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(",",":")).encode()).hexdigest()

def from_workflow_runs(head_sha:str,runs,required:tuple[str,...])->CIEvidence:
 latest={}
 for raw in runs:
  name=str(raw.get("name",""))
  if not name:continue
  run_id=int(raw.get("id",0) or 0)
  previous=latest.get(name)
  if previous is None or run_id>previous.run_id:
   latest[name]=Gate(name,str(raw.get("status","")),raw.get("conclusion"),run_id)
 evidence=CIEvidence(head_sha,tuple(latest[k] for k in sorted(latest)),required)
 evidence.validate()
 return evidence
