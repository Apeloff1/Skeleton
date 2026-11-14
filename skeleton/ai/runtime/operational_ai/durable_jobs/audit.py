"""Hash-chained global event sequence, verifies every link before trusted reads."""
from __future__ import annotations
import hashlib
from .canonical import encode,decode,sha256
from .errors import deny
from .spec import require_id

GENESIS="0"*64


def append_event(db,job_id:str,kind:str,body:dict)->str:
    require_id(job_id,"audit-job")
    require_id(kind,"event-kind")
    prev=db.execute("SELECT audit_sha FROM ai_job_state WHERE singleton=1").fetchone()
    if prev is None:
        deny("audit-head-missing")
    event=encode(body)
    content=encode({"previous":prev[0],"job_id":job_id,"kind":kind,
                    "payload_sha256":sha256(event)})
    digest=sha256(content)
    db.execute("""INSERT INTO ai_job_audit(job_id,kind,event_json,previous_sha,event_sha)
                  VALUES(?,?,?,?,?)""",(job_id,kind,event,prev[0],digest))
    db.execute("UPDATE ai_job_state SET audit_sha=? WHERE singleton=1",(digest,))
    return digest


def verify_audit(db,*,max_events:int=100000)->dict:
    from .canonical import require_int
    require_int(max_events,1,100000,"audit-events")
    prev=GENESIS
    count=0
    last_seq=0
    for seq,job_id,kind,event_bytes,old,digest in db.execute(
       "SELECT seq,job_id,kind,event_json,previous_sha,event_sha FROM ai_job_audit ORDER BY seq"
    ):
        count+=1
        if count>max_events or seq<=last_seq or old!=prev:
            deny("audit-chain")
        if encode(decode(event_bytes)) != event_bytes:
            deny("audit-noncanonical")
        computed=sha256(encode({"previous":prev,"job_id":job_id,"kind":kind,
                                "payload_sha256":sha256(event_bytes)}))
        if computed!=digest:
            deny("audit-digest")
        prev=digest
        last_seq=seq
    row=db.execute("SELECT audit_sha FROM ai_job_state WHERE singleton=1").fetchone()
    if not row or row[0]!=prev:
        deny("audit-head-mismatch")
    return {"events":count,"head":prev,"verified":True}


def events_for_job(db,job_id:str,*,limit:int=256)->list[dict]:
    from .canonical import require_int
    require_id(job_id,"audit-job")
    require_int(limit,1,1000,"audit-page")
    verify_audit(db)
    rows=db.execute(
      "SELECT seq,kind,event_json,event_sha FROM ai_job_audit WHERE job_id=? ORDER BY seq LIMIT ?",
      (job_id,limit)
    ).fetchall()
    return [{"seq":seq,"kind":kind,"body":decode(payload),"sha256":digest}
            for seq,kind,payload,digest in rows]
