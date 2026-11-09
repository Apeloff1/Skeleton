"""Complete patch bundle represents tracked and authorized additive files."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass
@dataclass(frozen=True)
class PatchBundle:
 tracked_patch:str;new_files:tuple[tuple[str,str],...]
 def digest(self):return hashlib.sha256(json.dumps({"tracked":self.tracked_patch,"new_files":self.new_files},sort_keys=True,separators=(",",":")).encode()).hexdigest()
def bundle(tracked_patch:str,new_files:dict[str,str])->PatchBundle:return PatchBundle(tracked_patch,tuple(sorted(new_files.items())))
