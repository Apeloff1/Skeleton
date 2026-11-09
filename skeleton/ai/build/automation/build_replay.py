"""Replay guard preventing duplicate autonomous build acceptance."""
from __future__ import annotations
import hashlib
def replay_key(*,head_sha:str,generation:str,allocation:str,task:str)->str:
 if not all((head_sha,generation,allocation,task)):raise ValueError("replay identity incomplete")
 return hashlib.sha256(f"{head_sha}:{generation}:{allocation}:{task}".encode()).hexdigest()
def reject_seen(key:str,seen:set[str])->None:
 if key in seen:raise ValueError("duplicate autonomous build replay")
