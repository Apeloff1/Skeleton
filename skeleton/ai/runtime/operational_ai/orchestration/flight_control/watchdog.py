"""Read-only bounded abandonment and capacity inspection.

Monitoring is not recovery. Call operator recovery separately with approval.
"""
from __future__ import annotations
from .contracts import FlightConflict
from . import controls


def report(ledger,*,limit:int=256)->dict:
    if type(limit)is not int or not 1<=limit<=4096:
        raise FlightConflict('invalid monitoring budget')
    stamp=ledger.clock.stamp()
    with ledger.db.snapshot() as conn:
        records=conn.execute("""SELECT job_id,state,worker,owner_fence,
            lease_boot,lease_until_ns,updated_ns FROM ai_flight_jobs
            WHERE principal=? AND state IN ('queued','claimed','running')
            ORDER BY updated_ns,job_id LIMIT ?""",
            (ledger.identity.key(),limit+1)).fetchall()
        if len(records)>limit:raise FlightConflict('monitor inventory exceeded bound')
        stale=[];pending=[]
        for job_id,state,worker,fence,boot,until,updated in records:
            if state=='queued':pending.append(job_id)
            elif boot!=stamp.boot or until is None or until<=stamp.tick:
                stale.append({'job_id':job_id,'state':state,'worker':worker,
                              'fence':fence,'boot_mismatch':boot!=stamp.boot})
        return {'schema':'skeleton.ai.flight-watch.v1','mode':controls.mode(conn),
                'principal':ledger.identity.key(),'active':len(records),
                'queued':len(pending),'stale_count':len(stale),'stale':stale,
                'status':'needs-operator-review' if stale else 'observed',
                'actions_taken':0}
