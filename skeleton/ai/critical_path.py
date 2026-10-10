"""Known-answer critical path analysis for VOL-314."""
from dataclasses import dataclass
import math
@dataclass(frozen=True)
class TaskSlack: task_id:str; duration:float; earliest_start:float; latest_start:float
@dataclass(frozen=True)
class PathBlocker: task_id:str; reason:str
@dataclass(frozen=True)
class CriticalPath:
 task_ids:tuple[str,...]; duration:float; slack:tuple[TaskSlack,...]; blockers:tuple[PathBlocker,...]
def analyze_critical_path(durations:dict[str,float],dependencies:tuple[tuple[str,str],...],blocked:dict[str,str]|None=None):
 if not durations or any(not n or isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for n,v in durations.items()):raise ValueError("durations required and nonnegative")
 pred={n:[] for n in durations};succ={n:[] for n in durations}
 for a,b in dependencies:
  if a not in pred or b not in pred or a==b:raise ValueError("invalid dependency")
  pred[b].append(a);succ[a].append(b)
 indeg={n:len(pred[n]) for n in pred};queue=sorted(n for n,v in indeg.items() if v==0);order=[]
 while queue:
  n=queue.pop(0);order.append(n)
  for q in succ[n]:
   indeg[q]-=1
   if indeg[q]==0:queue.append(q);queue.sort()
 if len(order)!=len(durations):raise ValueError("dependency cycle")
 es={}
 for n in order:es[n]=max((es[p]+durations[p] for p in pred[n]),default=0)
 total=max(es[n]+durations[n] for n in order)
 ls={}
 for n in reversed(order):ls[n]=min((ls[s]-durations[n] for s in succ[n]),default=total-durations[n])
 slack=tuple(TaskSlack(n,durations[n],es[n],ls[n]) for n in sorted(order))
 critical=tuple(n for n in order if abs(ls[n]-es[n])<1e-9)
 blockers=tuple(PathBlocker(n,r) for n,r in sorted((blocked or {}).items()) if n in durations)
 return CriticalPath(critical,total,slack,blockers)
