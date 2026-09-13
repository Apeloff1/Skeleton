"""Bounded weighted work scheduler."""
class Scheduler:
 def __init__(self,weights):
  if not weights or any(v<=0 for v in weights.values()): raise ValueError("positive weights required")
  self._names=tuple(weights); self._weights=tuple(weights.values()); self._cursor=0; self._quota=0; self._cycle=0
  self._total=sum(self._weights)
 def next(self):
  for _ in range(len(self._names)*2):
   name=self._names[self._cursor]
   if self._quota * self._total < self._weights[self._cursor] * (self._cycle + 1):
    self._quota+=1; self._cursor=(self._cursor+1)%len(self._names)
    if self._quota>=self._total: self._quota=0; self._cycle+=1
    return name
   self._cursor=(self._cursor+1)%len(self._names)
  self._quota=0; self._cycle+=1
  return self.next()
