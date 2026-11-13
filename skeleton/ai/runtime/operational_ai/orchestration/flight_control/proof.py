"""Read-only bounded flight event inventory and source-digest commitment."""
from __future__ import annotations
from hashlib import sha256
from .contracts import FlightConflict
from . import events,lifecycle
from ..execution_spine.contracts import canonical


def export(ledger,*,limit:int=1024)->dict:
    if type(limit)is not int or not 1<=limit<=4096:
        raise FlightConflict('invalid proof inventory budget')
    heads=[]
    with ledger.db.snapshot() as conn:
        rows=conn.execute("""SELECT job_id,state,receipt_sha256 FROM ai_flight_jobs
            WHERE principal=? ORDER BY job_id LIMIT ?""",(ledger.identity.key(),limit+1)).fetchall()
        if len(rows)>limit:raise FlightConflict('proof inventory exceeded limit')
        for job_id,state,receipt_hash in rows:
            chain=events.inspect(conn,job_id)
            lifecycle.verify(chain,state)
            head=sha256(canonical(chain[-1])).hexdigest() if chain else '0'*64
            heads.append({'job_id':job_id,'state':state,'event_count':len(chain),
                          'head_sha256':head,'receipt_sha256':receipt_hash})
    manifest={'schema':'skeleton.ai.flight-proof.v1','principal':ledger.identity.key(),
              'model_sha256':ledger.identity.model_sha256,
              'jobs':heads,'status':'integrity-inventory-not-signed'}
    return {'manifest':manifest,'manifest_sha256':sha256(canonical(manifest)).hexdigest()}
