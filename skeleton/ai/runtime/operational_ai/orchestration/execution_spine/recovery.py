"""Explicit operator-approved recovery of abandoned pending requests.

A crash may leave a pending fence. Never replay the model silently: identify a
bounded expired intent, hold it, and demand a fresh request ID. Existing
committed receipts and outbound events are never rewritten.
"""
from __future__ import annotations
import time
from .contracts import SpineError,Busy,Conflict
from .chain import append

def inspect(conn,*,limit:int=256)->tuple[dict,...]:
    if type(limit)is not int or not 1<=limit<=4096:raise SpineError('invalid recovery inventory ceiling')
    rows=conn.execute("SELECT session,request_id,state,owner_token,lease_deadline_ns FROM requests WHERE state='pending' ORDER BY updated_ns LIMIT ?", (limit+1,)).fetchall()
    if len(rows)>limit:raise SpineError('unbounded pending recovery inventory')
    now=time.monotonic_ns()
    return tuple({'session':s,'request_id':r,'state':st,'fence':f,'expired':expiry is not None and now>=expiry}
                 for s,r,st,f,expiry in rows)

def hold_expired(conn,*,approved:bool,limit:int=256)->dict:
    if approved is not True:raise Conflict('independent operator approval required for recovery hold')
    candidates=inspect(conn,limit=limit)
    expired=[x for x in candidates if x['expired']]
    now=time.monotonic_ns()
    for item in expired:
        result=conn.execute("UPDATE requests SET state='held',lease_deadline_ns=NULL,updated_ns=? WHERE session=? AND request_id=? AND state='pending' AND owner_token=? AND lease_deadline_ns<=?",
            (now,item['session'],item['request_id'],item['fence'],now))
        if result.rowcount!=1:raise Busy('recovery state changed concurrently')
        append(conn,item['session'],'request_recovery_held',{'request_id':item['request_id'],'fence':item['fence']})
    return {'held':len(expired),'still_live':len(candidates)-len(expired)}
