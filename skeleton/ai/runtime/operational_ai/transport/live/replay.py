"""Bounded journal event replay with previous-hash continuity checks."""
from __future__ import annotations
from dataclasses import dataclass
from .cursor import CursorSigner,EventCursor,CursorError
import time
from ...persistence.journal import EventJournal,GENESIS

@dataclass(frozen=True,slots=True)
class ReplayPage:
    events:tuple[dict,...]
    next_cursor:str
    has_more:bool
    latest_seq:int

class EventReplay:
    def __init__(self,journal:EventJournal,signer:CursorSigner,*,max_page:int=128):
        if type(max_page) is not int or not 1<=max_page<=1024:
            raise CursorError('replay page bound invalid')
        self.journal=journal;self.signer=signer;self.max_page=max_page

    def page(self,*,session:str,tenant:str,user:str,cursor:str|None=None,
             limit:int=32)->ReplayPage:
        if type(limit) is not int or not 1<=limit<=self.max_page:
            raise CursorError('replay query limit exceeds admission')
        events=self.journal.replay(session)
        previous=GENESIS;start=0
        if cursor is not None:
            state=self.signer.verify(cursor,session=session,tenant=tenant,user=user)
            start=state.seq
            if start>len(events):raise CursorError('journal replay gap or truncation')
            previous=events[start-1].digest if start else GENESIS
            if previous!=state.head_sha:raise CursorError('cursor no longer anchored to journal')
        batch=events[start:start+limit]
        records=[{'seq':e.seq,'event_id':e.event_id,'kind':e.kind,
                  'payload':e.payload,'previous':e.previous_digest,'sha256':e.digest} for e in batch]
        if batch:previous=batch[-1].digest
        next_cursor=self.signer.issue(EventCursor(session,tenant,user,start+len(batch),
                                                   previous,time.time_ns()+3_600_000_000_000))
        return ReplayPage(tuple(records),next_cursor,start+len(batch)<len(events),len(events))
