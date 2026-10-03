"""Continuation handshake: accepted work requires fresh supervisor generation."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class RefreshDecision:
 ready:bool;reason:str
def require_fresh(*,previous_generation:str,current_generation:str,accepted:int,terminal:bool)->RefreshDecision:
 if terminal:return RefreshDecision(False,"canonical queue terminal")
 if accepted<=0:return RefreshDecision(False,"no accepted work to advance")
 if not previous_generation or not current_generation:return RefreshDecision(False,"missing generation identity")
 if previous_generation==current_generation:return RefreshDecision(False,"awaiting fresh supervisor generation")
 return RefreshDecision(True,"fresh canonical generation observed")
