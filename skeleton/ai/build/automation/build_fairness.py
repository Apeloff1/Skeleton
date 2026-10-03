"""Deterministic starvation-resistant lane ordering."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class Lane:
 id:str;priority:int;age:int;failures:int
def order(lanes:tuple[Lane,...])->tuple[Lane,...]:
 return tuple(sorted(lanes,key=lambda x:(-(x.priority+min(x.age,20)),x.failures,x.id)))
