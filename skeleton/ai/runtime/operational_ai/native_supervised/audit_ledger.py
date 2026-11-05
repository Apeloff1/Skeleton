"""Model run-bound HMAC audit and replay on top of existing SQLite custody."""
from __future__ import annotations
import sqlite3
from ..native_candidate.ledger import CandidateLedger
from .canonical import require_id,require_sha,digest
from .errors import reject

KINDS=frozenset((
    "source","policy","genesis","training","candidate","challenge",
    "measurement","comparison","hold","recovery",
))


class SupervisedLedger:
    def __init__(self,connection:sqlite3.Connection,*,key:bytes,run_id:str):
        require_id(run_id,"run")
        self.run_id="sft_"+run_id
        self.store=CandidateLedger(connection,key=key)

    def append(self,event_id:str,kind:str,record:dict)->dict:
        require_id(event_id,"event")
        if kind not in KINDS:
            reject("audit-event-kind")
        if type(record) is not dict or len(record)>10000:
            reject("audit-event-body")
        # The legacy candidate ledger provides serialized HMAC-custody,
        # transaction fencing, conflict detection and externally pinned heads.
        return self.store.append(self.run_id,event_id,kind,record)

    def verify(self,*,pinned_head:str|None=None)->dict:
        return self.store.verify(self.run_id,expected_head=pinned_head)

    def replay(self)->tuple[dict,...]:
        return self.store.replay(self.run_id)
