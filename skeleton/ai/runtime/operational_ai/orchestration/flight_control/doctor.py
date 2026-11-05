"""Read-only queue, event-chain and receipt integrity diagnostics."""
from __future__ import annotations
from hashlib import sha256
import json
from .contracts import FlightConflict
from . import events,lifecycle,controls
from ..execution_spine.contracts import canonical


def inspect(ledger,*,max_jobs:int=4096,max_events_per_job:int=4096)->dict:
    if type(max_jobs)is not int or not 1<=max_jobs<=4096:
        raise FlightConflict('invalid job inventory bound')
    with ledger.db.snapshot() as conn:
        rows=conn.execute('SELECT job_id,state,receipt_json,receipt_sha256,owner_fence FROM ai_flight_jobs WHERE principal=? ORDER BY job_id LIMIT ?',
                          (ledger.identity.key(),max_jobs+1)).fetchall()
        if len(rows)>max_jobs:raise FlightConflict('job inventory is larger than the review budget')
        counts={state:0 for state in ('queued','claimed','running','completed','held','cancelled')}
        event_count=0
        for job_id,state,raw,stored_hash,fence in rows:
            if state not in counts:raise FlightConflict('unsupported job state')
            if type(fence)is not int or fence<0:raise FlightConflict('job fence corrupted')
            history=events.inspect(conn,job_id,max_events=max_events_per_job)
            if not history or history[0]['kind']!='submitted':
                raise FlightConflict('job has no initial admission event')
            lifecycle.verify(history,state)
            event_count+=len(history);counts[state]+=1
            if state=='completed':
                if raw is None or sha256(raw).hexdigest()!=stored_hash:
                    raise FlightConflict('committed queue receipt corrupted')
                try:receipt=json.loads(raw)
                except (TypeError,ValueError) as exc:raise FlightConflict('committed receipt JSON corrupted') from exc
                if (canonical(receipt,ceiling=4096)!=raw or receipt.get('job_id')!=job_id or
                    history[-1]['kind'] not in ('completed','receipt-recovered')):
                    raise FlightConflict('committed receipt or event state diverged')
        return {'schema':'skeleton.ai.flight-doctor.v1','status':'verified',
                'mode':controls.mode(conn),
                'jobs':len(rows),'events':event_count,'states':counts,
                'principal':ledger.identity.key(),'model_sha256':ledger.identity.model_sha256}
