"""Per-operation hash chain for commands and state transitions."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from .database import DurableDatabase,DurableError
from .identifiers import scope,valid_id
from .codec import canonical,parse
GENESIS='0'*64

@dataclass(frozen=True,slots=True)
class OperationEvent:
    seq:int
    event_id:str
    name:str
    payload:dict
    previous:str
    digest:str


def digest_event(seq:int,event_id:str,name:str,raw:bytes,previous:str)->str:
    return hashlib.sha256(canonical({'seq':seq,'event_id':event_id,'name':name,
                       'payload_sha':hashlib.sha256(raw).hexdigest(),'previous':previous})).hexdigest()

class OperationEvents:
    def __init__(self,db:DurableDatabase):self.db=db

    def append(self,tenant:str,owner:str,operation:str,event_id:str,name:str,payload:dict)->OperationEvent:
        key=scope(tenant,owner,operation)
        valid_id(event_id,'event');valid_id(name,'event name')
        raw=canonical(payload)
        with self.db.transaction() as conn:
            old=conn.execute('SELECT seq,name,payload,prior_sha,event_sha FROM ai_operation_events WHERE tenant=? AND owner=? AND operation=? AND event_id=?',(*key,event_id)).fetchone()
            if old:
                if old[1]!=name or old[2]!=raw:raise DurableError('event collision')
                self._verify_conn(conn,key)
                return OperationEvent(old[0],event_id,name,payload,old[3],old[4])
            events=self._verify_conn(conn,key)
            seq=len(events)+1
            prior=events[-1].digest if events else GENESIS
            hashed=digest_event(seq,event_id,name,raw,prior)
            conn.execute('INSERT INTO ai_operation_events VALUES (?,?,?,?,?,?,?,?,?)',(*key,seq,event_id,name,raw,prior,hashed))
            return OperationEvent(seq,event_id,name,payload,prior,hashed)

    def _verify_conn(self,conn,key:tuple[str,str,str])->tuple[OperationEvent,...]:
        rows=conn.execute('SELECT seq,event_id,name,payload,prior_sha,event_sha FROM ai_operation_events WHERE tenant=? AND owner=? AND operation=? ORDER BY seq',key).fetchall()
        out=[];prior=GENESIS;seen=set()
        for seq,event_id,name,raw,parent,hashed in rows:
            if (seq!=len(out)+1 or parent!=prior or event_id in seen or
                hashed!=digest_event(seq,event_id,name,raw,parent)):
                raise DurableError('event stream corrupt or reordered')
            out.append(OperationEvent(seq,event_id,name,parse(raw),parent,hashed));prior=hashed;seen.add(event_id)
        return tuple(out)

    def replay(self,tenant:str,owner:str,operation:str)->tuple[OperationEvent,...]:
        key=scope(tenant,owner,operation)
        with self.db._lock:
            return self._verify_conn(self.db._db,key)
