"""Threshold and diversity requirements for provenance signatures."""
from __future__ import annotations
from dataclasses import dataclass
from .signed_envelope import Signature

@dataclass(frozen=True,slots=True)
class QuorumPolicy:
    minimum_valid:int=1
    minimum_distinct_keys:int=1
    minimum_distinct_algorithms:int=1
    required_algorithms:tuple[str,...]=()
    def __post_init__(self)->None:
        if min(self.minimum_valid,self.minimum_distinct_keys,self.minimum_distinct_algorithms)<1: raise ValueError("quorum minima must be positive")

def quorum_satisfied(valid:tuple[Signature,...],policy:QuorumPolicy)->bool:
    if len(valid)<policy.minimum_valid: return False
    if len({s.key_id for s in valid})<policy.minimum_distinct_keys: return False
    algorithms={s.algorithm for s in valid}
    if len(algorithms)<policy.minimum_distinct_algorithms: return False
    if not set(policy.required_algorithms)<=algorithms: return False
    return True

__all__=["QuorumPolicy","quorum_satisfied"]
