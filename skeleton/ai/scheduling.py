"""Dependency/authority-first baseline scheduling for VOL-315."""
from dataclasses import dataclass
from enum import Enum
class SchedulingPolicy(str,Enum): FIFO="fifo"; EARLIEST_DEADLINE="earliest_deadline"
@dataclass(frozen=True)
class Assignment: task_id:str; worker_id:str
@dataclass(frozen=True)
class Schedule: assignments:tuple[Assignment,...]; deferred:tuple[str,...]; policy:SchedulingPolicy
def schedule(tasks,workers,*,policy=SchedulingPolicy.FIFO):
 completed=set();blocked=set();assign=[];deferred=[];remaining={t["id"]:t for t in tasks};worker_map={w["id"]:w for w in workers}
 while remaining:
  newly_blocked=[t for t in remaining.values() if set(t.get("dependencies",()))&blocked]
  for t in newly_blocked: blocked.add(t["id"]);deferred.append(t["id"]);del remaining[t["id"]]
  ready=[t for t in remaining.values() if set(t.get("dependencies",())).issubset(completed)]
  if not ready:
   if remaining:raise ValueError("dependency cycle or unsatisfied dependency")
   break
  ready.sort(key=(lambda t:(t.get("deadline",float("inf")),t.get("sequence",0),t["id"])) if policy is SchedulingPolicy.EARLIEST_DEADLINE else (lambda t:(t.get("sequence",0),t["id"])))
  for t in ready:
   eligible=[w for w in worker_map.values() if t.get("lease",False) and t["authority"] in w.get("authorities",())]
   if not eligible:deferred.append(t["id"]);blocked.add(t["id"]);del remaining[t["id"]];continue
   w=sorted(eligible,key=lambda x:x["id"])[0];assign.append(Assignment(t["id"],w["id"]));completed.add(t["id"]);del remaining[t["id"]]
 return Schedule(tuple(assign),tuple(sorted(deferred)),policy)
