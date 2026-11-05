"""Read-only validation of complete plan state, step receipts and event chain."""
from __future__ import annotations
from hashlib import sha256
from ..core.canonical import parse,digest
from ..core.errors import Integrity
from ..planning.dag import compile_plan
from ..custody.events import read

def inspect(store,plan_id):
    plan,steps,state=store.load(plan_id)
    order=compile_plan(plan)
    with store.db.snapshot() as c:
        events=read(c,plan_id)
        records=c.execute('SELECT step_id,state,attempt,fence,result_json,result_sha FROM agent_steps WHERE plan_id=?',(plan_id,)).fetchall()
        for step_id,status,attempt,fence,raw,h in records:
            if status=='complete':
                if raw is None or sha256(raw).hexdigest()!=h:raise Integrity('step receipt changed')
                rec=parse(raw)
                if rec['status']!='complete':raise Integrity('stored step completion inconsistent')
            elif raw is not None or h is not None:raise Integrity('pending/held step contains forged result')
            if status=='running' and attempt!=1:raise Integrity('running step not fenced')
    if state=='complete' and any(s['state']!='complete' for s in steps.values()):raise Integrity('plan marked complete with pending steps')
    return {'status':state,'plan_id':plan_id,'steps':len(order),'events':len(events),
            'complete':sum(v['state']=='complete' for v in steps.values()),
            'held':sum(v['state']=='held' for v in steps.values()),
            'model_or_tool_certified':False}
