"""Cross-restart request deduplication with semantic conflict detection."""
from __future__ import annotations
from .database import DurableDatabase,DurableError
from .codec import canonical,parse,hash_bytes
from .identifiers import valid_id

class RequestDedupe:
    def __init__(self,db:DurableDatabase):self.db=db

    def record(self,scope:str,request_id:str,fingerprint:dict,receipt:dict)->tuple[dict,bool]:
        valid_id(scope,'scope');valid_id(request_id,'request identifier')
        key=hash_bytes(canonical(fingerprint))
        raw=canonical(receipt)
        with self.db.transaction() as conn:
            old=conn.execute('SELECT fingerprint,receipt FROM ai_requests WHERE scope=? AND request_id=?',(scope,request_id)).fetchone()
            if old:
                if old[0]!=key:raise DurableError('idempotency key reused for different request')
                return parse(old[1]),True
            conn.execute('INSERT INTO ai_requests VALUES (?,?,?,?)',(scope,request_id,key,raw))
            return receipt,False

    def read(self,scope:str,request_id:str,fingerprint:dict)->dict|None:
        valid_id(scope,'scope');valid_id(request_id,'request identifier')
        rows=self.db.query('SELECT fingerprint,receipt FROM ai_requests WHERE scope=? AND request_id=?',(scope,request_id))
        if not rows:return None
        if rows[0][0]!=hash_bytes(canonical(fingerprint)):
            raise DurableError('different request under existing idempotency key')
        return parse(rows[0][1])
