"""A replayable event cursor, not uncommitted token streaming.

Tokens are deliberately never emitted before durable commit. This avoids a
client observing text that disappears after an interrupted transaction.
"""
from __future__ import annotations
from hashlib import sha256
from .contracts import Identity,Conflict,SpineError
from .outbox import pending

def committed_events(conn,identity:Identity,*,after_sequence:int=0,limit:int=32):
    if type(after_sequence)is not int or after_sequence<0:raise SpineError('invalid cursor')
    if type(limit)is not int or not 1<=limit<=128:raise SpineError('invalid event batch')
    rows=conn.execute('SELECT sequence,event_key,stream,kind,event_json,event_sha256 FROM outbox WHERE sequence>? ORDER BY sequence LIMIT ?', (after_sequence,limit)).fetchall()
    result=[]
    for seq,key,stream,kind,raw,digest in rows:
        row=conn.execute('SELECT principal FROM sessions WHERE session=?',(stream,)).fetchone()
        if row is None or row[0]!=identity.key():continue
        if sha256(raw).hexdigest()!=digest:raise SpineError('committed event mutation')
        result.append({'sequence':seq,'event_key':key,'kind':kind,'event_sha256':digest})
    return tuple(result)
