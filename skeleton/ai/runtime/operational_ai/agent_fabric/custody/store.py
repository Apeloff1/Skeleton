"""Durable, principal-scoped workflow with at-most-once execution custody."""
from __future__ import annotations
from . import schema,events
from ..core.canonical import canonical,parse,digest,identifier,uint
from ..core.errors import Conflict,Invalid,Integrity,Held
from ..planning.parse import encode,decode
from ..planning.dag import compile_plan
import hashlib,time
class AgentStore:
    def __init__(self,db,identity):
        self.db=db;self.identity=identity;schema.install(db)
    def create(self,plan):
        compile_plan(plan)
        raw=encode(plan);now=time.time_ns();h=hashlib.sha256(raw).hexdigest()
        with self.db.transaction() as c:
            existing=c.execute('SELECT owner,plan_sha,plan_json FROM agent_plans WHERE plan_id=?',(plan.plan_id,)).fetchone()
            if existing:
                if existing!=(self.identity.key(),h,raw):raise Conflict('plan id reused with changed identity or plan')
                return {'replayed':True,'plan_sha256':h}
            c.execute('INSERT INTO agent_plans VALUES (?,?,?,?,?,?,?)',(plan.plan_id,self.identity.key(),h,raw,'active',now,now))
            for step in plan.steps:
                c.execute('INSERT INTO agent_steps(plan_id,step_id,state,kind,digest,updated_ns) VALUES (?,?,?,?,?,?)',
                          (plan.plan_id,step.step_id,'pending',step.kind,digest(step.record()),now))
            events.append(c,plan.plan_id,'created')
        return {'replayed':False,'plan_sha256':h}
    def load(self,plan_id):
        identifier(plan_id,'plan')
        with self.db.snapshot() as c:
            row=c.execute('SELECT owner,plan_sha,plan_json,state FROM agent_plans WHERE plan_id=?',(plan_id,)).fetchone()
            if row is None:raise Invalid('plan does not exist')
            owner,h,raw,state=row
            if owner!=self.identity.key():raise Conflict('plan principal/model mismatch')
            if hashlib.sha256(raw).hexdigest()!=h:raise Integrity('stored plan digest mismatch')
            plan=decode(raw)
            events.read(c,plan_id)
            steps={step_id:{'state':status,'attempt':attempt,'fence':fence,'kind':kind,'digest':step_digest,'result_sha':result_sha,'reason':reason}
              for step_id,status,attempt,fence,kind,step_digest,result_sha,reason in c.execute('SELECT step_id,state,attempt,fence,kind,digest,result_sha,reason FROM agent_steps WHERE plan_id=?',(plan_id,))}
            if set(steps)!={s.step_id for s in plan.steps}:raise Integrity('plan step inventory mismatch')
            for step in plan.steps:
                if steps[step.step_id]['kind']!=step.kind or steps[step.step_id]['digest']!=digest(step.record()):raise Integrity('step kind/content tampered')
            return plan,steps,state
    def start(self,plan_id,step_id,worker):
        identifier(worker,'worker');plan,steps,state=self.load(plan_id)
        if state!='active':raise Held('plan cannot be dispatched')
        from ..planning.dag import ready
        available=ready(plan,{k for k,v in steps.items() if v['state']=='complete'},{k for k,v in steps.items() if v['state']!='pending'})
        if step_id not in available:raise Conflict('step is blocked, already attempted or not ready')
        with self.db.transaction() as c:
            row=c.execute('SELECT state,attempt,fence FROM agent_steps WHERE plan_id=? AND step_id=?',(plan_id,step_id)).fetchone()
            if row[0]!='pending' or row[1]!=0:raise Conflict('execution already started')
            fence=row[2]+1
            result=c.execute("UPDATE agent_steps SET state='running',attempt=1,fence=?,worker=?,updated_ns=? WHERE plan_id=? AND step_id=? AND state='pending' AND attempt=0",
                             (fence,worker,time.time_ns(),plan_id,step_id))
            if result.rowcount!=1:raise Conflict('competing start won')
            events.append(c,plan_id,'started',step_id)
            return fence
    def finish(self,plan_id,step_id,worker,fence,receipt):
        identifier(worker,'worker');uint(fence,'writer fence',1,2**63-1)
        if not isinstance(receipt,dict) or set(receipt)!={'schema','kind','output_sha256','status','metadata'} or receipt['schema']!='agent.step-result.v1':raise Invalid('invalid step receipt')
        raw=canonical(receipt,ceiling=1048576);h=hashlib.sha256(raw).hexdigest()
        with self.db.transaction() as c:
            row=c.execute('SELECT state,worker,fence,kind FROM agent_steps WHERE plan_id=? AND step_id=?',(plan_id,step_id)).fetchone()
            if row is None or row!=('running',worker,fence,receipt['kind']):raise Conflict('step fence or kind mismatch')
            if receipt['status']!='complete':raise Invalid('only complete verified receipt may finish')
            c.execute("UPDATE agent_steps SET state='complete',result_json=?,result_sha=?,updated_ns=? WHERE plan_id=? AND step_id=?",
                      (raw,h,time.time_ns(),plan_id,step_id))
            events.append(c,plan_id,'completed',step_id)
            remaining=c.execute("SELECT COUNT(*) FROM agent_steps WHERE plan_id=? AND state!='complete'",(plan_id,)).fetchone()[0]
            if remaining==0:
                c.execute("UPDATE agent_plans SET state='complete',updated_ns=? WHERE plan_id=?",(time.time_ns(),plan_id))
                events.append(c,plan_id,'plan-completed')
        return h
    def hold(self,plan_id,step_id,worker,fence,reason):
        identifier(reason,'hold reason')
        with self.db.transaction() as c:
            row=c.execute('SELECT state,worker,fence FROM agent_steps WHERE plan_id=? AND step_id=?',(plan_id,step_id)).fetchone()
            if row!=('running',worker,fence):raise Conflict('cannot hold unowned execution')
            c.execute("UPDATE agent_steps SET state='held',reason=?,updated_ns=? WHERE plan_id=? AND step_id=?",(reason,time.time_ns(),plan_id,step_id))
            c.execute("UPDATE agent_plans SET state='held',updated_ns=? WHERE plan_id=?",(time.time_ns(),plan_id))
            events.append(c,plan_id,'held',step_id)
    def repair(self,plan_id,step_id,*,approved=False):
        # A failed side effect cannot safely be retried; only model/read/review
        # may be explicitly reset by operator after separate review.
        if approved is not True:raise Held('operator approval needed')
        plan,steps,_=self.load(plan_id)
        step=next(s for s in plan.steps if s.step_id==step_id)
        if step.kind=='tool':raise Held('uncertain tool side effect cannot be reset')
        if steps[step_id]['state']!='held':raise Conflict('step not held')
        with self.db.transaction() as c:
            c.execute("UPDATE agent_steps SET state='pending',attempt=0,worker=NULL,reason=NULL,updated_ns=? WHERE plan_id=? AND step_id=?",(time.time_ns(),plan_id,step_id))
            c.execute("UPDATE agent_plans SET state='active',updated_ns=? WHERE plan_id=?",(time.time_ns(),plan_id))
            events.append(c,plan_id,'operator-reset',step_id)

    def mark_uncertain(self,plan_id,step_id,*,approved=False,worker_terminated=False):
        """Independently authorized hold of a crashed writer, never a restart.

        Operator must separately prove the worker is no longer alive. This
        transition does not make an uncertain external side effect safe.
        """
        if approved is not True or worker_terminated is not True:
            raise Held('independent operator termination proof required')
        self.load(plan_id)
        with self.db.transaction() as c:
            row=c.execute('SELECT state FROM agent_steps WHERE plan_id=? AND step_id=?',(plan_id,step_id)).fetchone()
            if row!=('running',):raise Conflict('only running step eligible for uncertainty hold')
            c.execute("UPDATE agent_steps SET state='held',reason='UncertainWorkerTermination',updated_ns=? WHERE plan_id=? AND step_id=?",(time.time_ns(),plan_id,step_id))
            c.execute("UPDATE agent_plans SET state='held',updated_ns=? WHERE plan_id=?",(time.time_ns(),plan_id))
            events.append(c,plan_id,'operator-uncertainty-hold',step_id)
