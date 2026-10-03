"""Bound evidence history without discarding unresolved identities."""
from __future__ import annotations
def retain(items:tuple[dict,...],*,limit:int=256)->tuple[dict,...]:
 if limit<16:raise ValueError("unsafe retention limit")
 unresolved=[x for x in items if x.get("state") not in {"retired","complete"}]
 resolved=[x for x in items if x.get("state") in {"retired","complete"}]
 keep_resolved=max(0,limit-len(unresolved))
 return tuple(unresolved+resolved[-keep_resolved:] if keep_resolved else unresolved)
