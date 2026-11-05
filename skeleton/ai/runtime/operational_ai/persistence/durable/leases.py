"""Durable fenced worker leases, monotonic escalation and explicit renewal."""
from __future__ import annotations
from dataclasses import dataclass
import time
from .database import DurableDatabase,DurableError
from .identifiers import valid_id

@dataclass(frozen=True,slots=True)
class Lease:
    key:str
    owner:str
    fence:int
    expires_ns:int

class DurableLeases:
    def __init__(self,db:DurableDatabase,clock=time.time_ns):self.db=db;self.clock=clock

    def acquire(self,key:str,owner:str,ttl_ns:int)->Lease:
        valid_id(key,'lease key');valid_id(owner,'worker')
        if type(ttl_ns) is not int or not 1_000_000<=ttl_ns<=86_400_000_000_000:
            raise DurableError('invalid lease duration')
        now=self.clock()
        with self.db.transaction() as conn:
            row=conn.execute('SELECT owner,fence,expires_ns FROM ai_leases WHERE lease_key=?',(key,)).fetchone()
            if row and row[2]>now:
                raise DurableError('live lease already owned; refusing duplicate worker')
            fence=row[1]+1 if row else 1
            expires=now+ttl_ns
            conn.execute('INSERT INTO ai_leases VALUES (?,?,?,?) ON CONFLICT(lease_key) DO UPDATE SET owner=excluded.owner,fence=excluded.fence,expires_ns=excluded.expires_ns',
                         (key,owner,fence,expires))
            return Lease(key,owner,fence,expires)

    def renew(self,lease:Lease,ttl_ns:int)->Lease:
        if type(ttl_ns) is not int or not 1_000_000<=ttl_ns<=86_400_000_000_000:
            raise DurableError('invalid renewal duration')
        now=self.clock()
        with self.db.transaction() as conn:
            cur=conn.execute('UPDATE ai_leases SET expires_ns=? WHERE lease_key=? AND owner=? AND fence=? AND expires_ns>?',
                (now+ttl_ns,lease.key,lease.owner,lease.fence,now))
            if cur.rowcount!=1:raise DurableError('lease lost or expired; no implicit reacquire')
            return Lease(lease.key,lease.owner,lease.fence,now+ttl_ns)

    def validate(self,lease:Lease)->bool:
        rows=self.db.query('SELECT owner,fence,expires_ns FROM ai_leases WHERE lease_key=?',(lease.key,))
        return bool(rows and rows[0]==(lease.owner,lease.fence,lease.expires_ns) and lease.expires_ns>self.clock())

    def release(self,lease:Lease)->None:
        with self.db.transaction() as conn:
            cur=conn.execute('DELETE FROM ai_leases WHERE lease_key=? AND owner=? AND fence=?',(lease.key,lease.owner,lease.fence))
            if cur.rowcount!=1:raise DurableError('stale lease release')
