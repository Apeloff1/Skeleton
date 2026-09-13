"""Bounded weighted work scheduler."""
class Scheduler:
 def __init__(self,weights):
  if not weights or any(v<=0 for v in weights.values()): raise ValueError("positive weights required")
  self._names=tuple(weights); self._weights=weights; self._cursor=0
 def next(self):
  name=self._names[self._cursor%len(self._names)]; self._cursor+=1; return name
