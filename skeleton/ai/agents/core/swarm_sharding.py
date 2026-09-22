"""Stable rendezvous hashing for distributing swarm ownership."""
from __future__ import annotations
from hashlib import blake2b

def _score(key:str,node:str)->int: return int.from_bytes(blake2b(f"{key}\0{node}".encode(),digest_size=8).digest(),"big")
def owners(key:str,nodes:list[str]|tuple[str,...],replicas:int=1)->tuple[str,...]:
 if replicas<1: raise ValueError("replicas must be positive")
 unique=tuple(dict.fromkeys(n for n in nodes if n))
 if not unique: return ()
 ranked=sorted(unique,key=lambda n:(-_score(key,n),n))
 return tuple(ranked[:min(replicas,len(ranked))])
def distribution(keys:list[str],nodes:list[str],replicas:int=1)->dict[str,int]:
 result={n:0 for n in dict.fromkeys(nodes)}
 for key in keys:
  for node in owners(key,nodes,replicas): result[node]=result.get(node,0)+1
 return result
