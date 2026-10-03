"""Canonical worktree identity including tracked, staged, and untracked state."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass
@dataclass(frozen=True)
class WorktreeSnapshot:
 head_sha:str;tracked_sha256:str;staged_sha256:str;untracked:tuple[tuple[str,str,int],...]
 def digest(self):return hashlib.sha256(json.dumps({"head":self.head_sha,"tracked":self.tracked_sha256,"staged":self.staged_sha256,"untracked":self.untracked},sort_keys=True,separators=(",",":")).encode()).hexdigest()
def snapshot(*,head_sha:str,tracked_diff:bytes,staged_diff:bytes,untracked:dict[str,bytes])->WorktreeSnapshot:
 return WorktreeSnapshot(head_sha,hashlib.sha256(tracked_diff).hexdigest(),hashlib.sha256(staged_diff).hexdigest(),tuple(sorted((p,hashlib.sha256(b).hexdigest(),len(b)) for p,b in untracked.items())))
