"""Dependency gate: readiness is fail-closed until all required checks pass."""
class DependencyGate:
 def __init__(self,dependencies): self._required=set(dependencies); self._ready=set()
 def mark(self,name,ready=True):
  if name not in self._required: raise KeyError(name)
  (self._ready.add(name) if ready else self._ready.discard(name))
 @property
 def ready(self): return self._required.issubset(self._ready)
