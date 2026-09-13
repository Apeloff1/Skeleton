"""Health-aware bounded endpoint selection."""
class HealthRouter:
 def __init__(self,targets):
  if not targets: raise ValueError("targets required")
  self._targets=list(dict.fromkeys(targets)); self._healthy=set(self._targets); self._cursor=-1
 def mark(self,target,healthy):
  if target not in self._targets: raise KeyError(target)
  if healthy: self._healthy.add(target)
  else: self._healthy.discard(target)
 def next(self):
  for _ in self._targets:
   self._cursor=(self._cursor+1)%len(self._targets)
   target=self._targets[self._cursor]
   if target in self._healthy: return target
  return None
 @property
 def healthy(self): return tuple(x for x in self._targets if x in self._healthy)
