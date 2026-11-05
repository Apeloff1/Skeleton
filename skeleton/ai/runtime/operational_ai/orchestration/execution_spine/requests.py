"""Idempotent, request-bound pending intent with monotone fencing tokens."""
from __future__ import annotations
import secrets,time
from .contracts import InferenceRequest,SpineLimits,Busy,Conflict,IntegrityFailure
from .principal import require_session
from .chain import append

def reserve(conn,req:InferenceRequest,limits:SpineLimits,*,lease_ns:int=60_000_000_000)->dict:
    saved=require_session(conn,req.identity,req.session)
    if saved['state']!='open':raise Conflict('session is closed')
    if len(req.prompt.encode('utf8'))>limits.input_bytes:raise Conflict('prompt exceeds admission budget')
    signature=req.bound_digest();now=time.monotonic_ns()
    row=conn.execute('SELECT request_sha256,state,owner_token,lease_deadline_ns,generation_nonce FROM requests WHERE session=? AND request_id=?',
        (req.session,req.request_id)).fetchone()
    if row is not None:
        digest,state,token,deadline,nonce=row
        if signature!=digest:raise Conflict('request ID reused for different input or identity')
        if state=='committed':return {'state':'committed','token':token,'nonce':nonce}
        if state in ('cancelled','held'):raise Conflict(f'request held terminal state {state}')
        if deadline is None or now<deadline:raise Busy('request is already in flight')
        # Expiry is not proof that the native model stopped running. Never
        # reclaim and regenerate an ambiguous pending inference. An independent
        # recovery action may hold the request after its deadline, but cannot
        # silently re-execute the same request ID.
        raise Busy('expired inference requires explicit operator recovery hold')
    competing=conn.execute("SELECT request_id FROM requests WHERE session=? AND state='pending' LIMIT 1",(req.session,)).fetchone()
    if competing:raise Busy('another session operation has pending custody')
    count=conn.execute("SELECT COUNT(*) FROM requests WHERE state='pending'").fetchone()[0]
    if count>=limits.max_pending:raise Busy('global pending admission ceiling')
    nonce=secrets.token_hex(16)
    conn.execute('INSERT INTO requests VALUES (?,?,?,?,?,0,?,?,?)',
        (req.session,req.request_id,signature,nonce,'pending',now+lease_ns,now,now))
    append(conn,req.session,'request_reserved',{'request_id':req.request_id,'sha256':signature})
    return {'state':'reserved','token':0,'nonce':nonce}

def heartbeat(conn,req:InferenceRequest,token:int,*,lease_ns:int=60_000_000_000):
    if type(token)is not int or token<0:raise Conflict('invalid fence token')
    now=time.monotonic_ns()
    result=conn.execute("UPDATE requests SET lease_deadline_ns=?,updated_ns=? WHERE session=? AND request_id=? AND owner_token=? AND request_sha256=? AND state='pending' AND lease_deadline_ns>?",
        (now+lease_ns,now,req.session,req.request_id,token,req.bound_digest(),now))
    if result.rowcount!=1:raise Conflict('lost inference lease')

def abort(conn,req:InferenceRequest,token:int,*,terminal:bool=False):
    now=time.monotonic_ns()
    state='cancelled' if terminal else 'held'
    result=conn.execute("UPDATE requests SET state=?,lease_deadline_ns=NULL,updated_ns=? WHERE session=? AND request_id=? AND owner_token=? AND request_sha256=? AND state='pending' AND lease_deadline_ns>?",
        (state,now,req.session,req.request_id,token,req.bound_digest(),now))
    if result.rowcount!=1:raise Conflict('failed to abort pending request with current ownership')
    append(conn,req.session,'request_'+state,{'request_id':req.request_id,'token':token})
