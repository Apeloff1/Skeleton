"""Fail-closed tool effect claims: at-most-once attempt, never blind retries.

SQLite custody is not an atomic transaction with arbitrary external effects.
A crash after execution but before receipt is ambiguous: keep a durable hold.
"""
from __future__ import annotations
import time
from hashlib import sha256
from .contracts import Identity,Conflict,IntegrityFailure,canonical,identifier
from .principal import require_session
from .policy import EffectGrant,require_effect
from .chain import append
from .outbox import emit

def prepare(conn,identity:Identity,session:str,grant:EffectGrant,signature:str,
            name:str,args:dict,*,key:bytes)->dict:
    require_session(conn,identity,session)
    require_effect(identity,grant,name,args,authorizing_key=key,signature=signature)
    raw=canonical(args,ceiling=64000)
    row=conn.execute('SELECT status,args_sha256 FROM effects WHERE grant_id=?',(grant.grant_id,)).fetchone()
    if row:
        if row[1]!=sha256(raw).hexdigest():raise IntegrityFailure('effect grant reused with altered arguments')
        raise Conflict('effect grant already attempted: no automatic replay')
    now=time.time_ns()
    conn.execute('INSERT INTO effects(grant_id,session,principal,tool,args_sha256,status,started_ns) VALUES (?,?,?,?,?,?,?)',
        (grant.grant_id,session,identity.key(),name,sha256(raw).hexdigest(),'attempting',now))
    append(conn,session,'tool_effect_attempted',{'grant_id':grant.grant_id,'tool':name,'args_sha256':sha256(raw).hexdigest()})
    return {'grant_id':grant.grant_id,'status':'attempting'}

def finalize(conn,identity:Identity,session:str,grant:EffectGrant,response:dict):
    raw=canonical(response,ceiling=262144)
    result=conn.execute("UPDATE effects SET status='completed',response_sha256=?,completed_ns=? WHERE grant_id=? AND session=? AND principal=? AND status='attempting'",
        (sha256(raw).hexdigest(),time.time_ns(),grant.grant_id,session,identity.key()))
    if result.rowcount!=1:raise Conflict('no current effect attempt to finalize')
    record={'grant_id':grant.grant_id,'tool':grant.operation,'response_sha256':sha256(raw).hexdigest()}
    append(conn,session,'tool_effect_completed',record)
    emit(conn,'tool_'+grant.grant_id,session,'tool_effect',record)
    return record

def inventory(conn,identity:Identity,session:str,*,limit:int=256)->tuple[dict,...]:
    require_session(conn,identity,session)
    rows=conn.execute('SELECT grant_id,tool,status,started_ns,completed_ns FROM effects WHERE session=? ORDER BY started_ns LIMIT ?', (session,limit+1)).fetchall()
    if len(rows)>limit:raise Conflict('tool effect inventory exceeds bound')
    return tuple(dict(zip(('grant_id','tool','status','started_ns','completed_ns'),row)) for row in rows)
