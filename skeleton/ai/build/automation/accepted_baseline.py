"""Content identity for preserving accepted work across later task rollback."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass
@dataclass(frozen=True)
class AcceptedBaseline:
 head_sha:str;tracked_diff_sha256:str;untracked:tuple[tuple[str,str],...]
 def digest(self):
  body={"head_sha":self.head_sha,"tracked_diff_sha256":self.tracked_diff_sha256,"untracked":self.untracked}
  return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def make(*,head_sha:str,tracked_diff:str,untracked:dict[str,bytes])->AcceptedBaseline:
 items=tuple(sorted((p,hashlib.sha256(b).hexdigest()) for p,b in untracked.items()))
 return AcceptedBaseline(head_sha,hashlib.sha256(tracked_diff.encode()).hexdigest(),items)
