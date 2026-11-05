"""Transactional, bounded event outbox with replay-safe consumer acknowledgments."""
from __future__ import annotations
from hashlib import sha256
import time,json
from .contracts import canonical,Conflict,IntegrityFailure,identifier,SpineError

def emit(conn,event_key:str,stream:str,kind:str,payload:dict)->int:
    identifier(event_key,'event key');identifier(stream,'stream');identifier(kind,'kind')
    raw=canonical(payload,ceiling=262144);sha=sha256(raw).hexdigest()
    prior=conn.execute('SELECT sequence,event_sha256 FROM outbox WHERE event_key=?',(event_key,)).fetchone()
    if prior:
        if prior[1]!=sha:raise Conflict('outbox event ID reused with conflicting content')
        return prior[0]
    return conn.execute('INSERT INTO outbox(event_key,stream,kind,event_json,event_sha256,created_ns) VALUES(?,?,?,?,?,?)',
        (event_key,stream,kind,raw,sha,time.time_ns())).lastrowid

def pending(conn,*,limit:int=32)->tuple[dict,...]:
    if type(limit)is not int or not 1<=limit<=256:raise SpineError('invalid outbox batch bound')
    rows=conn.execute('SELECT sequence,event_key,stream,kind,event_json,event_sha256 FROM outbox WHERE acked=0 ORDER BY sequence LIMIT ?', (limit,)).fetchall()
    result=[]
    for seq,key,stream,kind,raw,sha in rows:
        if sha256(raw).hexdigest()!=sha:raise IntegrityFailure('outbox event payload tampered')
        try:payload=json.loads(raw)
        except(ValueError,TypeError):raise IntegrityFailure('outbox event invalid JSON')
        if canonical(payload,ceiling=262144)!=raw:raise IntegrityFailure('outbox event not canonical')
        result.append({'sequence':seq,'event_key':key,'stream':stream,'kind':kind,'payload':payload,'event_sha256':sha})
    return tuple(result)

def consume(conn,consumer:str,event:dict)->bool:
    identifier(consumer,'consumer');key=identifier(event['event_key'],'event key')
    digest=event['event_sha256']
    row=conn.execute('SELECT event_sha256 FROM deliveries WHERE consumer=? AND event_key=?',(consumer,key)).fetchone()
    if row:
        if row[0]!=digest:raise IntegrityFailure('consumer replay event digest conflict')
        return False
    conn.execute('INSERT INTO deliveries VALUES(?,?,?,?)',(consumer,key,digest,time.time_ns()))
    return True

def acknowledge(conn,event_key:str,expected_sha:str)->bool:
    identifier(event_key)
    row=conn.execute('SELECT event_sha256,acked FROM outbox WHERE event_key=?',(event_key,)).fetchone()
    if row is None or row[0]!=expected_sha:raise Conflict('cannot ack unknown or mutated outbox event')
    if row[1]:return False
    if conn.execute('UPDATE outbox SET acked=1 WHERE event_key=? AND event_sha256=?',(event_key,expected_sha)).rowcount!=1:
        raise Conflict('outbox ack raced')
    return True
