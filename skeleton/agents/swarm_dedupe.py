"""Bounded result deduplication for at-least-once swarm execution."""
from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from typing import Callable
@dataclass(frozen=True,slots=True)
class Completion: task_id:str; token:str; recorded_at:float
class CompletionCache:
 def __init__(self,*,max_entries:int=100000,ttl_seconds:float=3600,clock:Callable[[],float]=monotonic):
  if max_entries<1 or ttl_seconds<=0: raise ValueError("invalid completion cache configuration")
  self.max_entries=max_entries; self.ttl_seconds=ttl_seconds; self.clock=clock; self._items=OrderedDict()
 def record(self,task_id:str,token:str)->bool:
  self.purge(); key=(task_id,token)
  if key in self._items: self._items.move_to_end(key); return False
  self._items[key]=Completion(task_id,token,self.clock())
  while len(self._items)>self.max_entries: self._items.popitem(last=False)
  return True
 def contains(self,task_id:str,token:str)->bool: self.purge(); return (task_id,token) in self._items
 def purge(self)->int:
  cutoff=self.clock()-self.ttl_seconds; removed=0
  while self._items:
   key,item=next(iter(self._items.items()))
   if item.recorded_at>cutoff: break
   self._items.pop(key); removed+=1
  return removed
 def __len__(self): self.purge(); return len(self._items)
