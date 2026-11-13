"""Transactional outbox with fenced claims, dedupe inbox and bounded retry."""
from __future__ import annotations
from dataclasses import dataclass
import time
from .database import DurableDatabase,DurableError
from .codec import canonical,parse,hash_bytes
from .identifiers import scope,valid_id

@dataclass(frozen=True,slots=True)
class OutboxMessage:
    tenant:str
    owner:str
    operation:str
    message_id:str
    destination:str
    payload:dict
    state:str
    attempts:int
    next_attempt_ns:int
    fence:int

class TransactionalOutbox:
    def __init__(self,db:DurableDatabase,*,max_attempts:int=8):
        if type(max_attempts) is not int or not 1<=max_attempts<=32:raise DurableError('invalid max attempts')
        self.db=db;self.max_attempts=max_attempts

    def enqueue(self,tenant:str,owner:str,operation:str,message_id:str,destination:str,payload:dict)->bool:
        key=scope(tenant,owner,operation)
        valid_id(message_id,'message');valid_id(destination,'destination')
        if not isinstance(payload,dict):raise DurableError('outbox payload must be object')
        raw=canonical(payload)
        with self.db.transaction() as conn:
            old=conn.execute('SELECT destination,payload FROM ai_operation_outbox WHERE tenant=? AND owner=? AND operation=? AND message_id=?',(*key,message_id)).fetchone()
            if old:
                if old!=(destination,raw):raise DurableError('outbox message ID collision')
                return False
            conn.execute('INSERT INTO ai_operation_outbox VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (*key,message_id,destination,raw,'pending',0,0,0))
            return True

    def pending(self,*,limit:int=64,now_ns:int|None=None)->tuple[OutboxMessage,...]:
        if type(limit) is not int or not 1<=limit<=512:raise DurableError('invalid outbox page')
        now=time.time_ns() if now_ns is None else now_ns
        rows=self.db.query("SELECT * FROM ai_operation_outbox WHERE state='pending' AND next_attempt_ns<=? ORDER BY next_attempt_ns,message_id LIMIT ?",(now,limit))
        return tuple(OutboxMessage(*row[:5],parse(row[5]),*row[6:]) for row in rows)

    def claim(self,msg:OutboxMessage)->OutboxMessage:
        with self.db.transaction() as conn:
            cur=conn.execute("UPDATE ai_operation_outbox SET state='claimed',fence=fence+1 WHERE tenant=? AND owner=? AND operation=? AND message_id=? AND state='pending' AND fence=?",
                (msg.tenant,msg.owner,msg.operation,msg.message_id,msg.fence))
            if cur.rowcount!=1:raise DurableError('stale or already claimed outbox message')
            return OutboxMessage(msg.tenant,msg.owner,msg.operation,msg.message_id,msg.destination,msg.payload,'claimed',msg.attempts,msg.next_attempt_ns,msg.fence+1)

    def ack(self,msg:OutboxMessage)->None:
        with self.db.transaction() as conn:
            cur=conn.execute("UPDATE ai_operation_outbox SET state='sent' WHERE tenant=? AND owner=? AND operation=? AND message_id=? AND state='claimed' AND fence=?",
                (msg.tenant,msg.owner,msg.operation,msg.message_id,msg.fence))
            if cur.rowcount!=1:raise DurableError('outbox acknowledgement lost fencing')

    def reject(self,msg:OutboxMessage,*,now_ns:int|None=None)->None:
        now=time.time_ns() if now_ns is None else now_ns
        attempts=msg.attempts+1
        next_ns=now+min(3_600,2**min(attempts,12))*1_000_000_000
        state='dead' if attempts>=self.max_attempts else 'pending'
        with self.db.transaction() as conn:
            cur=conn.execute("UPDATE ai_operation_outbox SET state=?,attempts=?,next_attempt_ns=? WHERE tenant=? AND owner=? AND operation=? AND message_id=? AND state='claimed' AND fence=?",
                (state,attempts,next_ns,msg.tenant,msg.owner,msg.operation,msg.message_id,msg.fence))
            if cur.rowcount!=1:raise DurableError('stale outbox failure report')

    def inbox_accept(self,consumer:str,message_id:str,payload:dict)->bool:
        valid_id(consumer,'consumer');valid_id(message_id,'message')
        digest=hash_bytes(canonical(payload))
        with self.db.transaction() as conn:
            old=conn.execute('SELECT message_sha FROM ai_operation_inbox WHERE consumer=? AND message_id=?',(consumer,message_id)).fetchone()
            if old:
                if old[0]!=digest:raise DurableError('inbox event ID reused with different content')
                return False
            conn.execute('INSERT INTO ai_operation_inbox VALUES (?,?,?,?)',(consumer,message_id,digest,time.time_ns()))
            return True
