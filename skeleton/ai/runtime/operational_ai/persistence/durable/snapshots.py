"""Snapshot only after verified event-chain boundary; never trust a projection alone."""
from __future__ import annotations
from .database import DurableDatabase,DurableError
from .eventlog import OperationEvents,GENESIS
from .codec import canonical,parse
from .identifiers import scope

class OperationSnapshots:
    def __init__(self,db:DurableDatabase):self.db=db;self.events=OperationEvents(db)

    def save(self,tenant:str,owner:str,operation:str,state:dict)->tuple[int,str]:
        key=scope(tenant,owner,operation)
        events=self.events.replay(*key)
        seq=len(events)
        head=events[-1].digest if events else GENESIS
        blob=canonical(state)
        with self.db.transaction() as conn:
            old=conn.execute('SELECT payload,terminal_sha FROM ai_snapshots WHERE tenant=? AND owner=? AND operation=? AND seq=?',(*key,seq)).fetchone()
            if old and old!=(blob,head):raise DurableError('same event boundary snapshot differs')
            conn.execute('INSERT OR IGNORE INTO ai_snapshots VALUES (?,?,?,?,?,?)',(*key,seq,blob,head))
        return seq,head

    def load_verified(self,tenant:str,owner:str,operation:str)->tuple[int,dict]|None:
        key=scope(tenant,owner,operation)
        rows=self.db.query('SELECT seq,payload,terminal_sha FROM ai_snapshots WHERE tenant=? AND owner=? AND operation=? ORDER BY seq DESC LIMIT 1',key)
        if not rows:return None
        seq,blob,head=rows[0]
        events=self.events.replay(*key)
        if seq>len(events) or (events[seq-1].digest if seq else GENESIS)!=head:
            raise DurableError('snapshot cannot be anchored to verified event history')
        return seq,parse(blob)
