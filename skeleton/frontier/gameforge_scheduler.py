"""Bounded weighted work scheduler."""
class Scheduler:
 def __init__(self,weights):
  if not weights or any(v<=0 for v in weights.values()): raise ValueError("positive weights required")
  self._schedule=tuple(name for name,weight in weights.items() for _ in range(weight))
  self._cursor=0
 def next(self):
  name=self._schedule[self._cursor]
  self._cursor=(self._cursor+1)%len(self._schedule)
  return name
