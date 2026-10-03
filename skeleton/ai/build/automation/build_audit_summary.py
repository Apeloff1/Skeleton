"""Compact final audit summary for humans and automation."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import json
@dataclass(frozen=True)
class AuditSummary:
 head_sha:str;status:str;cycles:int;accepted:int;repairs:int;quarantined:int;certificate_sha256:str=""
def render(x:AuditSummary)->str:return json.dumps({"schema":"autonomous-studio.audit-summary.v1",**asdict(x)},sort_keys=True,indent=2)+"\n"
