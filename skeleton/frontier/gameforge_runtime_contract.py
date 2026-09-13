"""Composition boundary for evolving runtime admission contracts."""
from dataclasses import dataclass
from .gameforge_admission import Admission,decide
from .gameforge_dependency import DependencyGate
from .gameforge_lifecycle import Lifecycle,ServiceLifecycle
from .gameforge_receipt import Receipt
@dataclass
class RuntimeContract:
 lifecycle:ServiceLifecycle
 dependencies:DependencyGate
 def admit(self,request_id,*,background=False,active=0,limit=1,read_only=False):
  if not self.lifecycle.can_accept: return Receipt(request_id,Admission.SHED.value,"lifecycle")
  if not self.dependencies.ready: return Receipt(request_id,Admission.SHED.value,"dependency")
  decision=decide(background_allowed=True,read_only=read_only,active=active,limit=limit,background=background)
  return Receipt(request_id,decision.value,decision.value)
