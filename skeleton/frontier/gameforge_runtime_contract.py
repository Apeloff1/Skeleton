"""Composition boundary for the evolving runtime contracts."""
from dataclasses import dataclass
from .gameforge_admission import Admission,decide
from .gameforge_dependency import DependencyGate
from .gameforge_lifecycle import Lifecycle,ServiceLifecycle
@dataclass
class RuntimeContract:
 lifecycle:ServiceLifecycle
 dependencies:DependencyGate
 def admit(self,*,background=False,active=0,limit=1,read_only=False):
  if not self.lifecycle.can_accept or not self.dependencies.ready: return Admission.SHED
  return decide(background_allowed=True,read_only=read_only,active=active,limit=limit,background=background)
