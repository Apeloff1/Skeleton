"""Independent plan-shape risk diagnostics; no generated plan promotion."""
from .dag import compile_plan

def analyze(plan):
    order=compile_plan(plan)
    nodes={s.step_id:s for s in plan.steps}
    width={}
    for n in order:
        width[n]=1+max((width[x] for x in nodes[n].depends_on),default=0)
    children={k:0 for k in order}
    for s in plan.steps:
        for dep in s.depends_on:children[dep]+=1
    return {'steps':len(order),'max_depth':max(width.values()),
            'roots':sum(not s.depends_on for s in plan.steps),
            'leaves':sum(children[k]==0 for k in order),
            'max_fanout':max(children.values()),
            'tool_steps':sum(s.kind=='tool' for s in plan.steps)}
