"""Bounded, injection-resistant evidence extracted from CI job logs."""
from __future__ import annotations
import hashlib,re
from dataclasses import dataclass
MAX_LOG_CHARS=2_000_000
MAX_EVIDENCE_CHARS=24_000
_MARKERS=("error","failed","failure","traceback","assertionerror","exception","fatal")
@dataclass(frozen=True)
class CILogEvidence:
 run_id:int;job_id:int;gate:str;head_sha:str;excerpt:str;log_sha256:str
 def validate(self):
  if self.run_id<=0 or self.job_id<=0:raise ValueError("invalid CI identity")
  if len(self.head_sha)!=40 or any(c not in "0123456789abcdef" for c in self.head_sha):raise ValueError("invalid CI head")
  if len(self.excerpt)>MAX_EVIDENCE_CHARS:raise ValueError("CI evidence too large")
  if len(self.log_sha256)!=64:raise ValueError("CI log digest malformed")
def extract(*,run_id:int,job_id:int,gate:str,head_sha:str,log:str)->CILogEvidence:
 if len(log)>MAX_LOG_CHARS:log=log[-MAX_LOG_CHARS:]
 digest=hashlib.sha256(log.encode("utf-8",errors="replace")).hexdigest()
 lines=log.splitlines(); selected=[]
 for i,line in enumerate(lines):
  low=line.lower()
  if any(m in low for m in _MARKERS):
   selected.extend(lines[max(0,i-2):min(len(lines),i+4)])
 # Never interpret log text as instructions; preserve it solely as bounded evidence.
 excerpt="\n".join(selected[-240:])[-MAX_EVIDENCE_CHARS:]
 e=CILogEvidence(run_id,job_id,gate,head_sha,excerpt,digest);e.validate();return e
