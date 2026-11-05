"""Hash-chained job transition ledger; the model never writes transitions."""
from __future__ import annotations
from hashlib import sha256
import json
from .contracts import FlightConflict
from ..execution_spine.contracts import canonical
from ..execution_spine.outbox import emit

ZERO='0'*64


def append(conn,job_id:str,kind:str,fields:dict)->dict:
    # Caller is in same BEGIN IMMEDIATE transaction as the transition.
    inspect(conn,job_id)  # Refuse to extend a damaged chain.
    row=conn.execute('SELECT ordinal,event_digest FROM ai_flight_events WHERE job_id=? ORDER BY ordinal DESC LIMIT 1',(job_id,)).fetchone()
    ordinal=1 if row is None else row[0]+1
    prior=ZERO if row is None else row[1]
    event={'schema':'skeleton.ai.flight-event.v1','job_id':job_id,
           'ordinal':ordinal,'kind':kind,'fields':fields,'prior_digest':prior}
    raw=canonical(event,ceiling=65536)
    event_hash=sha256(raw).hexdigest()
    conn.execute('INSERT INTO ai_flight_events(job_id,ordinal,kind,prior_digest,event_digest,event_json) VALUES (?,?,?,?,?,?)',
                 (job_id,ordinal,kind,prior,event_hash,raw))
    # A separate outbox makes supervision observable without leaking prompt text.
    emit(conn,'flight_'+sha256(f'{job_id}:{ordinal}'.encode('ascii')).hexdigest(),job_id,'ai_flight',event)
    return event


def inspect(conn,job_id:str,*,max_events:int=4096)->tuple[dict,...]:
    if type(max_events)is not int or not 1<=max_events<=4096:raise FlightConflict('invalid event ceiling')
    rows=conn.execute('SELECT ordinal,kind,prior_digest,event_digest,event_json FROM ai_flight_events WHERE job_id=? ORDER BY ordinal LIMIT ?',
                      (job_id,max_events+1)).fetchall()
    if len(rows)>max_events:raise FlightConflict('event ceiling exceeded')
    previous=ZERO
    items=[]
    for ordinal,kind,stored_prior,stored_hash,raw in rows:
        if ordinal!=len(items)+1 or stored_prior!=previous or sha256(raw).hexdigest()!=stored_hash:
            raise FlightConflict('flight event chain damaged')
        try:event=json.loads(raw)
        except (ValueError,TypeError) as exc:raise FlightConflict('flight event JSON damaged') from exc
        if canonical(event,ceiling=65536)!=raw or event.get('job_id')!=job_id or event.get('ordinal')!=ordinal or event.get('kind')!=kind or event.get('prior_digest')!=previous:
            raise FlightConflict('flight event canonical identity mismatch')
        event_key='flight_'+sha256(f'{job_id}:{ordinal}'.encode('ascii')).hexdigest()
        outbox=conn.execute('SELECT stream,kind,event_json,event_sha256 FROM outbox WHERE event_key=?',
                            (event_key,)).fetchone()
        if (outbox is None or outbox[0]!=job_id or outbox[1]!='ai_flight' or
            outbox[2]!=raw or outbox[3]!=stored_hash):
            raise FlightConflict('flight event outbox integrity mismatch')
        items.append(event);previous=stored_hash
    return tuple(items)
