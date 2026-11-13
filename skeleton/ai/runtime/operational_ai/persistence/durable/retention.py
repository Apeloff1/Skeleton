"""Prunable derivative data, never silent deletion of authoritative operations."""
from __future__ import annotations
from .database import DurableDatabase,DurableError
from .identifiers import valid_id

class Retention:
    def __init__(self,db:DurableDatabase):self.db=db

    def purge_completed_outbox(self,*,before_ns:int,limit:int=1000)->int:
        if type(before_ns) is not int or before_ns<0 or type(limit) is not int or not 1<=limit<=1000:
            raise DurableError('invalid bounded retention policy')
        with self.db.transaction() as conn:
            # Archive protocol: only explicitly sent derivative outbox rows.
            rows=conn.execute("SELECT tenant,owner,operation,message_id FROM ai_operation_outbox WHERE state='sent' AND next_attempt_ns<=? ORDER BY tenant,owner,operation,message_id LIMIT ?",(before_ns,limit)).fetchall()
            for key in rows:
                conn.execute('DELETE FROM ai_operation_outbox WHERE tenant=? AND owner=? AND operation=? AND message_id=? AND state=\'sent\'',key)
            return len(rows)

    def count(self)->dict[str,int]:
        return {name:self.db.query(f'SELECT COUNT(*) FROM {name}')[0][0] for name in
                ('ai_operation','ai_operation_events','ai_operation_outbox','ai_operation_inbox','ai_snapshots')}
