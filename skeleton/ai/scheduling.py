"""Dependency/authority-first baseline scheduling for VOL-315."""
from dataclasses import dataclass
from enum import Enum
class SchedulingPolicy(str,Enum): FIFO="fifo"; EARLIEST_DEADLINE="earliest_deadline"
@dataclass(frozen=True)
class Assignment: task_id:str; worker_id:str
@dataclass(frozen=True)
class Schedule: assignments:tuple[Assignment,...]; deferred:tuple[str,...]; policy:SchedulingPolicy
def schedule(tasks,workers,*,policy=SchedulingPolicy.FIFO):
 # task: id, dependencies, authority, lease, deadline, sequence
 done=set();assign=[];deferred=[];remaining={t["id"]:t for t in tasks}
 worker_map={w["id"]:w for w in workers}
 while remaining:
  ready=[t for t in remaining.values() if set(t.get("dependencies",())).issubset(done)]
  if not ready: raise ValueError("dependency cycle or unsatisfied dependency")
  ready.sort(key=(lambda t:(t.get("deadline",float("inf")),t.get("sequence",0),t["id"])) if policy is SchedulingPolicy.EARLIEST_DEADLINE else (lambda t:(t.get("sequence",0),t["id"])))
  progress=False
  for t in ready:
   eligible=[w for w in worker_map.values() if t.get("lease",False) and t["authority"] in w.get("authorities",())]
   if not eligible:deferred.append(t["id"]);done.add(t["id"]);del remaining[t["id"]];progress=True;continue
   w=sorted(eligible,key=lambda x:x["id"])[0];assign.append(Assignment(t["id"],w["id"]));done.add(t["id"]);del remaining[t["id"]];progress=True
  if not progress:raise ValueError("scheduler made no progress")
 return Schedule(tuple(assign),tuple(sorted(deferred)),policy)
