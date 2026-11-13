"""Operator-initiated recovery: never automatically re-run uncertain inference.

A claimed-but-not-started task may safely return to queue. A running task
may only complete from an already committed, exact-identity spine receipt.
If a running task has no authoritative committed receipt, hold the job.
"""
from __future__ import annotations
from hashlib import sha256
from .contracts import FlightConflict,FlightBusy
from .ledger import _receipt
from . import events


def expired(ledger,*,limit:int=256)->tuple[dict,...]:
    if type(limit)is not int or not 1<=limit<=4096:raise FlightConflict('invalid recovery ceiling')
    stamp=ledger.clock.stamp()
    with ledger.db.snapshot() as conn:
        rows=conn.execute("""SELECT job_id,state,owner_fence,lease_boot,lease_until_ns
            FROM ai_flight_jobs WHERE principal=? AND state IN ('claimed','running')
            ORDER BY updated_ns,job_id LIMIT ?""",(ledger.identity.key(),limit+1)).fetchall()
    if len(rows)>limit:raise FlightBusy('recovery candidate count exceeds review ceiling')
    return tuple({'job_id':j,'state':state,'owner_fence':fence,'expired':boot!=stamp.boot or deadline is None or deadline<=stamp.tick}
                 for j,state,fence,boot,deadline in rows)


def reconcile(ledger,spine,*,approved:bool=False,limit:int=256)->dict:
    if approved is not True:raise FlightConflict('independent operator recovery approval required')
    if spine.identity!=ledger.identity:raise FlightConflict('recovery model/principal mismatch')
    candidates=expired(ledger,limit=limit)
    completed=0;held=0;requeued=0;live=0
    for candidate in candidates:
        if not candidate['expired']:
            live+=1;continue
        spec=ledger.request_for(candidate['job_id'])
        # Read canonical model receipt OUTSIDE the queue write transaction.
        # Never call spine.turn(), even if no receipt exists.
        receipt=spine.replay(spec.session,spec.request_id,spec.prompt,
                             seed=spec.seed,temperature=spec.temperature)
        stamp=ledger.clock.stamp()
        with ledger.db.transaction() as conn:
            job=ledger._get(conn,spec.job_id)
            if (job['owner_fence']!=candidate['owner_fence'] or
                job['state']!=candidate['state'] or
                (job['lease_boot']==stamp.boot and
                 job['lease_until_ns'] is not None and job['lease_until_ns']>stamp.tick)):
                raise FlightConflict('recovery candidate changed before custody update')
            events.inspect(conn,spec.job_id)
            if job['state']=='claimed':
                # Prior to 'model-started' the worker never had permission to call inference.
                if receipt is not None:
                    raise FlightConflict('unstarted ticket has unexpected model receipt')
                conn.execute("""UPDATE ai_flight_jobs SET state='queued',worker=NULL,
                    lease_boot=NULL,lease_until_ns=NULL,owner_fence=owner_fence+1,
                    updated_ns=? WHERE job_id=?""",(stamp.wall,spec.job_id))
                events.append(conn,spec.job_id,'unstarted-requeued',{'previous_fence':job['owner_fence']})
                requeued+=1
            elif receipt is not None:
                raw=_receipt(job,receipt,ledger.identity)
                conn.execute("""UPDATE ai_flight_jobs SET state='completed',
                    receipt_json=?,receipt_sha256=?,lease_until_ns=NULL,
                    finished_ns=?,updated_ns=? WHERE job_id=?""",
                    (raw,sha256(raw).hexdigest(),stamp.wall,stamp.wall,spec.job_id))
                events.append(conn,spec.job_id,'receipt-recovered',{'receipt_sha256':sha256(raw).hexdigest()})
                completed+=1
            else:
                conn.execute("""UPDATE ai_flight_jobs SET state='held',
                    hold_reason='uncertain-inference',lease_until_ns=NULL,
                    finished_ns=?,updated_ns=? WHERE job_id=?""",
                    (stamp.wall,stamp.wall,spec.job_id))
                events.append(conn,spec.job_id,'uncertain-held',{'previous_fence':job['owner_fence']})
                held+=1
    return {'reviewed':len(candidates),'live':live,'requeued_unstarted':requeued,
            'recovered_from_committed_receipt':completed,'held_uncertain':held,
            'model_calls':0}
