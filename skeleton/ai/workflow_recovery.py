"""Deterministic workflow DAG recovery and compensation contracts."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x): return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class Step:
    step_id:str; generation:int; dependencies:tuple[str,...]; compensatable:bool=True
    def __post_init__(self):
        _id(self.step_id,"step_id");_u(self.generation,"generation")
        if len(self.dependencies)!=len(set(self.dependencies)): raise ValueError("duplicate dependency")
        if any(not isinstance(x,str) or not x.strip() for x in self.dependencies): raise ValueError("invalid dependency")

@dataclass(frozen=True)
class WorkflowPlan:
    plan_id:str; workflow_id:str; deadline_ns:int; steps:tuple[Step,...]
    @classmethod
    def create(cls,workflow_id,deadline_ns,steps):
        _id(workflow_id,"workflow_id");_u(deadline_ns,"deadline_ns");steps=tuple(sorted(steps,key=lambda x:x.step_id))
        ids=[s.step_id for s in steps]
        if not steps or len(ids)!=len(set(ids)): raise ValueError("workflow steps must be nonempty and unique")
        known=set(ids)
        if any(d not in known for s in steps for d in s.dependencies): raise ValueError("unknown dependency")
        visiting=set();done=set();by={s.step_id:s for s in steps}
        def visit(x):
            if x in visiting: raise ValueError("workflow dependency cycle")
            if x in done:return
            visiting.add(x)
            for d in by[x].dependencies:visit(d)
            visiting.remove(x);done.add(x)
        for x in ids:visit(x)
        payload={"workflow_id":workflow_id,"deadline_ns":deadline_ns,"steps":[{"step_id":s.step_id,"generation":s.generation,"dependencies":sorted(s.dependencies),"compensatable":s.compensatable} for s in steps]}
        return cls(_h("workflow-plan-sha256:",payload),workflow_id,deadline_ns,steps)

@dataclass(frozen=True)
class StepCheckpoint:
    checkpoint_id:str; plan_id:str; step_id:str; generation:int; outcome:str; evidence_id:str
    @classmethod
    def create(cls,plan,step_id,generation,outcome,evidence_id):
        _id(evidence_id,"evidence_id");_u(generation,"generation")
        if outcome not in {"committed","failed","compensated"}: raise ValueError("invalid checkpoint outcome")
        step=next((s for s in plan.steps if s.step_id==step_id),None)
        if step is None or step.generation!=generation: raise PermissionError("step generation is not current")
        x={"plan_id":plan.plan_id,"step_id":step_id,"generation":generation,"outcome":outcome,"evidence_id":evidence_id}
        return cls(_h("workflow-checkpoint-sha256:",x),plan.plan_id,step_id,generation,outcome,evidence_id)

@dataclass(frozen=True)
class WorkflowReceipt:
    receipt_id:str; plan_id:str; outcome:str; checkpoint_ids:tuple[str,...]

def recover(plan,checkpoints,now_ns):
    _u(now_ns,"now_ns")
    by_step={}
    for c in checkpoints:
        if c.plan_id!=plan.plan_id: raise PermissionError("foreign workflow checkpoint")
        if c.step_id in by_step and by_step[c.step_id]!=c: raise PermissionError("conflicting workflow checkpoint")
        by_step[c.step_id]=c
    committed={s for s,c in by_step.items() if c.outcome=="committed"}
    failed={s for s,c in by_step.items() if c.outcome=="failed"}
    if failed or now_ns>=plan.deadline_ns:
        return "compensating",compensation_order(plan,committed),()
    ready=tuple(s.step_id for s in plan.steps if s.step_id not in by_step and set(s.dependencies)<=committed)
    if len(committed)==len(plan.steps): return "committed",(),()
    return "running",(),ready

def compensation_order(plan,committed):
    committed=set(committed);by={s.step_id:s for s in plan.steps}
    if any(x not in by for x in committed): raise ValueError("unknown committed step")
    remaining=set(committed);order=[]
    while remaining:
        leaves=sorted(x for x in remaining if not any(x in by[y].dependencies for y in remaining))
        if not leaves: raise ValueError("compensation graph is cyclic")
        for x in reversed(leaves):
            if by[x].compensatable:order.append(x)
            remaining.remove(x)
    return tuple(order)

def terminal_receipt(plan,checkpoints,outcome):
    if outcome not in {"committed","compensated"}: raise ValueError("invalid terminal outcome")
    cps=tuple(sorted(checkpoints,key=lambda x:x.step_id))
    if any(c.plan_id!=plan.plan_id for c in cps): raise PermissionError("foreign checkpoint")
    by={c.step_id:c for c in cps}
    if outcome=="committed":
        if set(by)!=set(s.step_id for s in plan.steps) or any(c.outcome!="committed" for c in cps): raise PermissionError("workflow is not fully committed")
    else:
        needed={s.step_id for s in plan.steps if s.compensatable and s.step_id in by and by[s.step_id].outcome=="committed"}
        compensated={c.step_id for c in cps if c.outcome=="compensated"}
        if not needed<=compensated: raise PermissionError("workflow compensation is incomplete")
    ids=tuple(c.checkpoint_id for c in cps);x={"plan_id":plan.plan_id,"outcome":outcome,"checkpoint_ids":ids}
    return WorkflowReceipt(_h("workflow-receipt-sha256:",x),plan.plan_id,outcome,ids)
