"""Permanent principal binding for every conversation and checkpoint identity."""
from __future__ import annotations
import time,json
from .contracts import Identity,Conflict,IntegrityFailure,canonical,digest,identifier
from .chain import append

def admit(conn,identity:Identity)->str:
    key=identity.key();raw=canonical(identity.as_dict());now=time.time_ns()
    row=conn.execute('SELECT identity_json FROM principals WHERE principal=?',(key,)).fetchone()
    if row is None:
        conn.execute('INSERT INTO principals VALUES (?,?,?)',(key,raw,now))
        append(conn,key,'principal_admitted',{'principal':key,'identity_sha256':digest(identity.as_dict())})
    elif row[0]!=raw:raise IntegrityFailure('principal record corrupted or collided')
    return key

def require_session(conn,identity:Identity,session:str):
    identifier(session,'session')
    row=conn.execute('SELECT principal,revision,state FROM sessions WHERE session=?',(session,)).fetchone()
    if not row:raise Conflict('unknown session')
    if row[0]!=identity.key():raise Conflict('session belongs to another principal or model')
    return {'revision':row[1],'state':row[2]}

def create_session(conn,identity:Identity,session:str):
    identifier(session,'session');key=admit(conn,identity)
    if conn.execute('SELECT 1 FROM sessions WHERE session=?',(session,)).fetchone():
        raise Conflict('session ID already allocated')
    conn.execute('INSERT INTO sessions VALUES(?,?,0,?,?)',(session,key,'open',time.time_ns()))
    append(conn,session,'session_created',{'principal':key})

def close_session(conn,identity:Identity,session:str):
    saved=require_session(conn,identity,session)
    if saved['state']=='closed':return False
    conn.execute("UPDATE sessions SET state='closed' WHERE session=?",(session,))
    append(conn,session,'session_closed',{'principal':identity.key(),'revision':saved['revision']})
    return True
