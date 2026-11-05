"""Verify the *entire* durable job transition chain before exposing a cursor.

No outbox read is trusted without FlightControl's full hash chain check. A
read-only SQLite snapshot binds the job, principal, chain and response atomically.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .contracts import StreamError,StreamConflict,StreamUnavailable,FlightEvent,terminal,bounded,identifier
from .cursor import CursorAuthority

@dataclass(frozen=True,slots=True)
class StreamSnapshot:
    job_id:str
    state:str
    events:tuple[FlightEvent,...]
    next_cursor:str|None
    backlog:bool
    latest_ordinal:int
    terminal:bool
    def record(self)->dict:
        return {'schema':'skeleton.ai.flight-snapshot.v1','job_id':self.job_id,
                'state':self.state,'events':len(self.events),
                'next_cursor':self.next_cursor,'backlog':self.backlog,
                'latest_ordinal':self.latest_ordinal,'terminal':self.terminal,
                'model_calls':0}

class EventReader:
    def __init__(self,ledger,cursors:CursorAuthority):
        if not hasattr(ledger,'db') or not hasattr(ledger,'identity') or not callable(getattr(ledger,'_get',None)):
            raise StreamError('authoritative flight ledger required')
        if not isinstance(cursors,CursorAuthority):
            raise StreamError('authenticated cursor authority required')
        self.ledger=ledger
        self.cursors=cursors

    def read(self,job_id:str,cursor:str|None=None,*,limit:int=32)->StreamSnapshot:
        from skeleton.ai.runtime.operational_ai.orchestration.flight_control import events,lifecycle
        from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import canonical
        identifier(job_id)
        bounded(limit,1,64,'read window')
        position=self.cursors.decode(job_id,cursor) if cursor is not None else None
        with self.ledger.db.snapshot() as conn:
            # Distinguish unknown/foreign jobs from a corrupt event chain.
            # A damaged chain is a server integrity hold, never a recoverable
            # caller syntax conflict or a fabricated empty event response.
            job=self.ledger._get(conn,job_id)
            from skeleton.ai.runtime.operational_ai.orchestration.flight_control.contracts import FlightConflict
            try:
                sequence=events.inspect(conn,job_id,max_events=4096)
                lifecycle.verify(sequence,job['state'])
            except FlightConflict as exc:
                raise StreamUnavailable('authoritative job event continuity unverified') from exc
            if position is not None:
                if position.ordinal>len(sequence):
                    raise StreamConflict('cursor references an event not in the committed ledger')
                previous=sequence[position.ordinal-1]
                expected=sha256(canonical(previous,ceiling=65536)).hexdigest()
                if position.digest!=expected:
                    raise StreamConflict('cursor does not match the committed event')
            ordinal=position.ordinal if position is not None else 0
            selections=sequence[ordinal:ordinal+limit]
            projections=[]
            for event in selections:
                n=event['ordinal']; digest=sha256(canonical(event,ceiling=65536)).hexdigest()
                projections.append(FlightEvent(job_id,n,event['kind'],digest,self.cursors.encode(job_id,n,digest)))
            next_cursor=projections[-1].cursor if projections else cursor
            return StreamSnapshot(job_id,job['state'],tuple(projections),next_cursor,
                ordinal+len(projections)<len(sequence),len(sequence),terminal(job['state']))
