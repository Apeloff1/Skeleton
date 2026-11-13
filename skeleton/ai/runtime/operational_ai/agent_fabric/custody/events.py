"""Hash-chain of operator/model workflow transitions committed with state."""
from __future__ import annotations
import hashlib
from ..core.canonical import canonical,parse,hex_digest,uint
from ..core.errors import Integrity
ZERO='0'*64

def read(conn,plan_id,limit=8192):
    uint(limit,'event review bound',1,65536)
    rows=conn.execute('SELECT sequence,kind,step_id,prior_sha,event_sha,event_json FROM agent_events WHERE plan_id=? ORDER BY sequence LIMIT ?', (plan_id,limit+1)).fetchall()
    if len(rows)>limit:raise Integrity('event inventory exceeded review bound')
    out=[];prior=ZERO
    for seq,kind,step,stored_prior,stored_hash,raw in rows:
        if seq!=len(out)+1 or stored_prior!=prior or hashlib.sha256(raw).hexdigest()!=stored_hash:raise Integrity('workflow event hash chain corrupt')
        v=parse(raw)
        if v!={'schema':'agent.event.v1','plan':plan_id,'sequence':seq,'kind':kind,'step':step,'prior':prior}:raise Integrity('workflow event schema mismatch')
        out.append(v);prior=stored_hash
    return tuple(out)

def append(conn,plan_id,kind,step_id=None):
    events=read(conn,plan_id)
    previous=ZERO if not events else conn.execute('SELECT event_sha FROM agent_events WHERE plan_id=? AND sequence=?',(plan_id,len(events))).fetchone()[0]
    event={'schema':'agent.event.v1','plan':plan_id,'sequence':len(events)+1,'kind':kind,'step':step_id,'prior':previous}
    raw=canonical(event)
    sha=hashlib.sha256(raw).hexdigest()
    conn.execute('INSERT INTO agent_events VALUES (?,?,?,?,?,?,?)',(plan_id,len(events)+1,kind,step_id,previous,sha,raw))
    return sha
