"""Health-aware bounded endpoint selection."""
class HealthRouter:
 def __init__(self,targets):
  if not targets: raise ValueError("targets required")
  self._targets=list(dict.fromkeys(targets)); self._healthy=set(self._targets); self._cursor=0
 def mark(self,target,healthy):
  if target not in self._targets: raise KeyError(target)
  (self._healthy.add(target) if healthy else self._healthy.discard(target))
 def next(self):
  live=[x for x in self._targets if x in self._healthy]
  if not live: return None
  self._cursor=(self._cursor+1)%len(live); return live[self._cursor]
 @property
 def healthy(self): return tuple(x for x in self._targets if x in self._healthy)
