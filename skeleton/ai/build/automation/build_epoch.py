"""Monotonic build epochs prevent state from leaking across canonical generations."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class BuildEpoch:
 number:int;generation:str;head_sha:str
def next_epoch(current:BuildEpoch|None,*,generation:str,head_sha:str)->BuildEpoch:
 if not generation or len(head_sha)!=40:raise ValueError("invalid epoch authority")
 if current is None:return BuildEpoch(0,generation,head_sha)
 if generation==current.generation and head_sha==current.head_sha:return current
 return BuildEpoch(current.number+1,generation,head_sha)
