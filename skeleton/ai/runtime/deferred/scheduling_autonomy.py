"""Task scheduling and bounded autonomy contracts VOL-313..319 (318 already hardened)."""
from dataclasses import dataclass
from enum import Enum
@dataclass(frozen=True,slots=True)
class Subtask: task_id:str; duration:int; authority:frozenset[str]; constraints:frozenset[str]; integration:bool=False
@dataclass(frozen=True,slots=True)
class TaskDependency: before:str; after:str
@dataclass(frozen=True,slots=True)
class TaskDecomposition: parent_authority:frozenset[str]; parent_constraints:frozenset[str]; subtasks:tuple[Subtask,...]; dependencies:tuple[TaskDependency,...]
def validate_decomposition(d,max_subtasks=64):
 ids={x.task_id for x in d.subtasks}
 if len(ids)!=len(d.subtasks) or len(ids)>max_subtasks or not any(x.integration for x in d.subtasks):return False
 if any(not x.authority<=d.parent_authority or not d.parent_constraints<=x.constraints for x in d.subtasks):return False
 g={i:[] for i in ids}
 for e in d.dependencies:
  if e.before not in ids or e.after not in ids:return False
  g[e.before].append(e.after)
 seen=set();active=set()
 def cyc(n):
  if n in active:return True
  if n in seen:return False
  active.add(n)
  if any(cyc(x) for x in g[n]):return True
  active.remove(n);seen.add(n);return False
 return not any(cyc(n) for n in ids)
@dataclass(frozen=True,slots=True)
class TaskSlack: task_id:str; slack:int
@dataclass(frozen=True,slots=True)
class PathBlocker: task_id:str; reason:str
@dataclass(frozen=True,slots=True)
class CriticalPath: task_ids:tuple[str,...]; duration:int; slack:tuple[TaskSlack,...]
def critical_path(d):
 if not validate_decomposition(d):raise ValueError("invalid decomposition")
 tasks={x.task_id:x for x in d.subtasks};pred={i:[] for i in tasks}
 for e in d.dependencies:pred[e.after].append(e.before)
 memo={}
 def finish(n):
  if n not in memo:memo[n]=tasks[n].duration+max((finish(p) for p in pred[n]),default=0)
  return memo[n]
 end=max(tasks,key=finish);path=[end]
 while pred[path[-1]]:path.append(max(pred[path[-1]],key=finish))
 path.reverse();total=finish(end)
 return CriticalPath(tuple(path),total,tuple(TaskSlack(i,total-finish(i)) for i in tasks))
@dataclass(frozen=True,slots=True)
class SchedulingPolicy: name:str
@dataclass(frozen=True,slots=True)
class Assignment: task_id:str; worker_id:str
@dataclass(frozen=True,slots=True)
class Schedule: policy:SchedulingPolicy; assignments:tuple[Assignment,...]
def schedule_ready(d,completed,workers,leases,worker_authority):
 ready=[]
 for t in d.subtasks:
  deps={e.before for e in d.dependencies if e.after==t.task_id}
  if t.task_id not in completed and deps<=completed:ready.append(t)
 out=[]
 for t in ready:
  for w in workers:
   if w in leases and t.authority<=worker_authority.get(w,frozenset()):
    out.append(Assignment(t.task_id,w));break
 return Schedule(SchedulingPolicy("dependency-first"),tuple(out))
@dataclass(frozen=True,slots=True)
class WorkloadTrace: task_durations:tuple[int,...]; assumptions:tuple[str,...]
@dataclass(frozen=True,slots=True)
class SimulationMetric: throughput:float; latency:float; fairness:float; resource:float
@dataclass(frozen=True,slots=True)
class SchedulingSimulation:
 trace:WorkloadTrace; policy:SchedulingPolicy; metric:SimulationMetric
    @property
    def authoritative(self):return False
@dataclass(frozen=True,slots=True)
class ControlState: measured:float; target:float; resource_remaining:float
@dataclass(frozen=True,slots=True)
class ControlSignal: adjustment:float; bounded:bool
@dataclass(frozen=True,slots=True)
class AutonomyController: gain:float; max_adjustment:float
def control(c,s,*,policy_allowed,authority_allowed):
 if not policy_allowed or not authority_allowed or s.resource_remaining<=0:return ControlSignal(0,True)
 raw=c.gain*(s.target-s.measured);return ControlSignal(max(-c.max_adjustment,min(c.max_adjustment,raw)),True)
@dataclass(frozen=True,slots=True)
class EscalationEvidence: eligibility:bool; approval_receipt:str|None
@dataclass(frozen=True,slots=True)
class AutonomyEscalation: request_id:str; requested_authority:frozenset[str]; evidence:EscalationEvidence
@dataclass(frozen=True,slots=True)
class EscalationGrant: request_id:str; authority:frozenset[str]; expires_at:str; revoked:bool=False
def grant_escalation(r,expires_at):
 if not r.evidence.eligibility or not r.evidence.approval_receipt:return None
 return EscalationGrant(r.request_id,r.requested_authority,expires_at)
