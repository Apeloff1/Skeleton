"""Compare-and-swap operation state, tenant custody and immutable request fingerprints."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import time
from .database import DurableDatabase,DurableError
from .codec import canonical,parse,hash_bytes
from .identifiers import scope

_STATES={'admitted','running','waiting','succeeded','failed','cancelled'}
_MOVES={'admitted':{'running','cancelled'},'running':{'waiting','succeeded','failed','cancelled'},
        'waiting':{'running','failed','cancelled'},'succeeded':set(),'failed':set(),'cancelled':set()}

@dataclass(frozen=True,slots=True)
class OperationRecord:
    tenant:str
    owner:str
    operation:str
    state:str
    version:int
    fence:int
    request_sha:str
    payload:Any
    result:Any|None
    created_ns:int
    updated_ns:int


class OperationRepository:
    def __init__(self,db:DurableDatabase):self.db=db

    @staticmethod
    def _decode(row:tuple)->OperationRecord:
        return OperationRecord(row[0],row[1],row[2],row[3],row[4],row[5],row[6],parse(row[7]),
                               parse(row[8]) if row[8] is not None else None,row[9],row[10])

    def create(self,tenant:str,owner:str,operation:str,payload:dict)->OperationRecord:
        key=scope(tenant,owner,operation)
        raw=canonical(payload)
        if not isinstance(payload,dict):raise DurableError('operation payload must be an object')
        digest=hash_bytes(raw)
        now=time.time_ns()
        with self.db.transaction() as conn:
            row=conn.execute('SELECT * FROM ai_operation WHERE tenant=? AND owner=? AND operation=?',key).fetchone()
            if row:
                found=self._decode(row)
                if found.request_sha!=digest:raise DurableError('operation id reused with different request')
                return found
            conn.execute('INSERT INTO ai_operation VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (*key,'admitted',1,0,digest,raw,None,now,now))
            row=conn.execute('SELECT * FROM ai_operation WHERE tenant=? AND owner=? AND operation=?',key).fetchone()
            return self._decode(row)

    def get(self,tenant:str,owner:str,operation:str)->OperationRecord:
        key=scope(tenant,owner,operation)
        rows=self.db.query('SELECT * FROM ai_operation WHERE tenant=? AND owner=? AND operation=?',key)
        if not rows:raise DurableError('operation not found in scope')
        return self._decode(rows[0])

    def change(self,tenant:str,owner:str,operation:str,*,expected_version:int,
               state:str,result:Any|None=None,fence:int|None=None)->OperationRecord:
        key=scope(tenant,owner,operation)
        if type(expected_version) is not int or expected_version<1 or state not in _STATES:
            raise DurableError('invalid operation transition')
        raw=None if result is None else canonical(result)
        with self.db.transaction() as conn:
            row=conn.execute('SELECT * FROM ai_operation WHERE tenant=? AND owner=? AND operation=?',key).fetchone()
            if row is None:raise DurableError('operation not found')
            old=self._decode(row)
            if old.version!=expected_version or state not in _MOVES[old.state]:
                raise DurableError('stale operation version or forbidden transition')
            if fence is not None and (type(fence) is not int or fence!=old.fence):
                raise DurableError('stale lease fence')
            if state in {'succeeded','failed'} and result is None:
                raise DurableError('terminal operation requires explicit result')
            now=time.time_ns()
            conn.execute('UPDATE ai_operation SET state=?,version=?,result=?,updated_ns=? '
                         'WHERE tenant=? AND owner=? AND operation=?',
                         (state,old.version+1,raw,now,*key))
            return self._decode(conn.execute('SELECT * FROM ai_operation WHERE tenant=? AND owner=? AND operation=?',key).fetchone())

    def list_active(self,tenant:str,owner:str,*,limit:int=100)->tuple[OperationRecord,...]:
        if type(limit) is not int or not 1<=limit<=1000:raise DurableError('invalid listing limit')
        scope(tenant,owner,'placeholder')
        rows=self.db.query("SELECT * FROM ai_operation WHERE tenant=? AND owner=? AND state IN ('admitted','running','waiting') ORDER BY updated_ns,operation LIMIT ?",(tenant,owner,limit+1))
        if len(rows)>limit:raise DurableError('active operation page overflow; use narrower scope')
        return tuple(self._decode(row) for row in rows)
