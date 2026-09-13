"""Low-cardinality observability projections for swarm operations."""
from __future__ import annotations
from dataclasses import asdict
from skeleton.agents.swarm_runtime import SwarmRuntime

def metrics(runtime:SwarmRuntime)->dict[str,float|int]:
    s=runtime.snapshot(); total=s.succeeded+s.dead+s.cancelled; completed=s.succeeded+s.dead
    return {**asdict(s),"terminal":total,"completion_ratio":round(s.succeeded/max(1,completed),6),"retry_ratio":round(s.retries/max(1,s.submitted),6),"queue_per_worker":round(s.queued/max(1,s.workers),6)}
def prometheus(runtime:SwarmRuntime,prefix:str="skeleton_swarm")->str:
    lines=[]
    for key,value in metrics(runtime).items():
        name=f"{prefix}_{key}".replace("-","_")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value}")
    return "\n".join(lines)+"\n"
def event_counts(runtime:SwarmRuntime)->dict[str,int]:
    result={}
    for _,kind,_ in runtime.events(): result[kind]=result.get(kind,0)+1
    return dict(sorted(result.items()))
