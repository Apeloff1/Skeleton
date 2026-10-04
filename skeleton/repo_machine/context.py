"""Purpose-specific bounded machine context slices using one shared intelligence graph."""
from __future__ import annotations
import json
from typing import Literal
from .coordination import build_coordination_plan
from .execution_plan import build_execution_plan
from .health import repository_health
from .metrics import structural_metrics
from .model import RepositoryModel
from .query import RepositoryQuery
from .workgraph import build_work_graph
Intent=Literal["overview","repair","architecture","testing","security","documentation","performance"]
MAX_CONTEXT_BYTES=48_000
def _fits(payload,limit): return len(json.dumps(payload,sort_keys=True,separators=(",",":")).encode())<=limit
def _bounded(payload,limit):
    compact=dict(payload); compact["truncated_for_context"]=False
    if _fits(compact,limit): return compact
    compact["truncated_for_context"]=True
    while not _fits(compact,limit):
        changed=False
        for key in ("files","work","findings","subsystems","topology","coordination","intelligence"):
            value=compact.get(key)
            if isinstance(value,list) and value: compact[key]=value[:max(1,len(value)//2)]; changed=True
            elif isinstance(value,dict) and value:
                if key=="topology":
                    e=value.get("edges",[]); compact[key]={"edges":e[:max(1,len(e)//2)],"cycles":value.get("cycles",[])[:4]}; changed=True
                elif key=="intelligence":
                    compact[key]={"graph_fingerprint":value.get("graph_fingerprint"),"strategic_value":value.get("strategic_value",0),"decision_surface":value.get("decision_surface",[])[:8],"counterfactual_surface":value.get("counterfactual_surface",[])[:8],"bridge_candidates":value.get("bridge_candidates",[])[:8],"safe_parallel_groups":value.get("safe_parallel_groups",[])[:4]}; changed=True
                elif key=="coordination":
                    d=value.get("decisions",[]); compact[key]={"decisions":d[:max(1,len(d)//2)],"bottleneck":value.get("bottleneck"),"frontier_size":value.get("frontier_size",0),"max_parallelism":value.get("max_parallelism",0),"coordination_pressure":value.get("coordination_pressure",0),"safe_parallel_groups":value.get("safe_parallel_groups",[])[:4]}; changed=True
            if _fits(compact,limit): return compact
        if not changed: break
    if not _fits(compact,limit):
        keep={"intent","fingerprint","health","metrics","coordination","execution","intelligence","truncated_for_context"}
        compact={k:compact[k] for k in keep if k in compact}; compact["truncated_for_context"]=True
    return compact
def context_for_intent(model:RepositoryModel,intent:Intent="overview",*,byte_limit:int=MAX_CONTEXT_BYTES):
    if isinstance(byte_limit,bool) or not isinstance(byte_limit,int) or not 4096<=byte_limit<=256000: raise ValueError("byte_limit must be in [4096,256000]")
    query=RepositoryQuery(model); graph=build_work_graph(model,limit=32)
    coordination=build_coordination_plan(model,limit=8,graph=graph); execution=build_execution_plan(model,limit=8,graph=graph)
    intelligence={"graph_fingerprint":graph.fingerprint,"strategic_value":graph.strategic_value(),"coordination_pressure":graph.pressure(),"critical_path_depth":graph.critical_depth,"bottleneck":graph.bottleneck(),"safe_parallel_groups":[list(x) for x in graph.safe_parallel_groups(limit=4)],"decision_surface":list(graph.decision_surface(limit=8)),"counterfactual_surface":list(graph.counterfactual_surface(limit=8)),"bridge_candidates":list(graph.bridge_candidates(limit=12))}
    base={"intent":intent,"fingerprint":model.fingerprint,"health":repository_health(model).as_dict(),"metrics":structural_metrics(model).as_dict(),
          "subsystems":[x.as_dict() for x in model.subsystems],"work":[x.as_dict() for x in graph.ordered_nodes],
          "coordination":coordination,"execution":execution.as_dict(),"intelligence":intelligence,
          "findings":[x.as_dict() for x in model.findings[:40]]}
    if intent=="architecture": base["topology"]={"edges":[x.as_dict() for x in model.edges],"cycles":[list(x) for x in model.cycles]}; base["files"]=[x.as_dict() for x in query.largest_files(limit=40).files]
    elif intent=="testing": base["files"]=[x.as_dict() for x in query.verification_files(tuple(x.name for x in model.subsystems),limit=100).files]
    elif intent=="repair": base["files"]=[x.as_dict() for x in query.files(kinds=["source","workflow","config"],limit=80).files]
    elif intent=="security": base["files"]=[x.as_dict() for x in query.files(zones=["automation","github","backend","core"],kinds=["source","workflow","config","script"],limit=80).files]
    elif intent=="documentation": base["files"]=[x.as_dict() for x in query.files(kinds=["docs"],limit=100).files]
    elif intent=="performance": base["files"]=[x.as_dict() for x in query.largest_files(limit=60).files]
    else: base["entrypoints"]=[x.as_dict() for x in query.entrypoints(limit=50).files]
    return _bounded(base,byte_limit)
