"""Small deterministic quorum contract."""
from __future__ import annotations
def quorum(total:int)->int:
    if total<=0: raise ValueError("total must be positive")
    return total//2+1
def reached(total:int, votes:int)->bool:
    if votes<0 or votes>total: raise ValueError("votes out of range")
    return votes>=quorum(total)
