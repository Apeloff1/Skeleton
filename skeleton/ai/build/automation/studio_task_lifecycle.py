"""State machine for one authorized Studio task."""
from __future__ import annotations
from dataclasses import dataclass
STATES=("authorized","building","reviewing","validating","accepted","rejected","quarantined")
ALLOWED={
 "authorized":{"building","rejected"},"building":{"reviewing","rejected"},
 "reviewing":{"building","validating","rejected"},"validating":{"building","accepted","rejected","quarantined"},
 "accepted":set(),"rejected":set(),"quarantined":set(),
}
@dataclass(frozen=True)
class TaskLifecycle:
    task_id:str; state:str="authorized"; revision:int=0
    def transition(self,target:str)->"TaskLifecycle":
        if target not in STATES: raise ValueError("unknown task lifecycle state")
        if target not in ALLOWED.get(self.state,set()): raise ValueError(f"illegal task transition {self.state}->{target}")
        return TaskLifecycle(self.task_id,target,self.revision+1)
