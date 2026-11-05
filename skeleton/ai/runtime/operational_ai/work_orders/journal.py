"""Persist full bounded event payloads and tie journal to post-mutation job state."""
from __future__ import annotations
import time
from .contracts import canonical,hash_bytes,fingerprint,identifier,refuse
COLUMNS=("job_id","tenant","subject","model_sha","tokenizer_sha","session_id",
         "request_id","prompt_sha","request_sha","seed","temperature","max_output",
         "status","revision","lease_sha","token_reservation","tokens_charged",
         "output_sha","updated_ns")
def job(conn,job_id):
    row=conn.execute("SELECT "+",".join(COLUMNS)+" FROM jobs WHERE job_id=?",
                     (identifier(job_id),)).fetchone()
    if row is None:refuse("unknown work order")
    return dict(zip(COLUMNS,row))
def state_digest(conn,job_id):
    return fingerprint(job(conn,job_id))
def append(conn,job_id,kind,data,*,clock=time.monotonic_ns):
    identifier(kind,"event")
    body=canonical(data)
    row=conn.execute("SELECT sequence,event_sha FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
    sequence=1 if row is None else row[0]+1
    prior="0"*64 if row is None else row[1]
    now=clock()
    if type(now) is not int or now<0:refuse("invalid monotonic journal clock")
    state_sha=state_digest(conn,job_id)
    record={"schema":"ai-work-order-event.v2","sequence":sequence,
            "job_id":job_id,"kind":kind,"body_sha":hash_bytes(body),
            "previous_sha":prior,"state_sha":state_sha,"created_ns":now}
    event_sha=fingerprint(record)
    conn.execute("""INSERT INTO events(sequence,job_id,kind,body,body_sha,
          previous_sha,event_sha,state_sha,created_ns) VALUES (?,?,?,?,?,?,?,?,?)""",
          (sequence,job_id,kind,body,record["body_sha"],prior,event_sha,state_sha,now))
    conn.execute("UPDATE jobs SET state_sha=? WHERE job_id=?",(state_sha,job_id))
    conn.execute("INSERT INTO outbox(event_sha,job_id,acknowledged) VALUES (?,?,0)",
                 (event_sha,job_id))
    return event_sha

def inspect(conn,*,maximum=1000000):
    if type(maximum) is not int or not 1<=maximum<=10000000:
        refuse("audit pagination bound required")
    rows=conn.execute("""SELECT sequence,job_id,kind,body,body_sha,
           previous_sha,event_sha,state_sha,created_ns FROM events
           ORDER BY sequence LIMIT ?""",(maximum+1,)).fetchall()
    if len(rows)>maximum:refuse("journal audit not exhaustive; paginate externally")
    previous="0"*64; latest={}
    for idx,(sequence,job_id,kind,body,body_sha,prior,event_sha,state_sha,created_ns) in enumerate(rows,1):
        if sequence!=idx or prior!=previous or hash_bytes(body)!=body_sha:
            refuse("journal gap, fork, or tampered payload")
        record={"schema":"ai-work-order-event.v2","sequence":sequence,
                "job_id":job_id,"kind":kind,"body_sha":body_sha,
                "previous_sha":prior,"state_sha":state_sha,"created_ns":created_ns}
        if fingerprint(record)!=event_sha:
            refuse("job event signature/digest mismatch")
        previous=event_sha;latest[job_id]=state_sha
    stored=conn.execute("SELECT job_id,state_sha FROM jobs").fetchall()
    for job_id,sha in stored:
        if latest.get(job_id)!=sha or state_digest(conn,job_id)!=sha:
            refuse("current job state diverged from append-only event evidence")
    return {"events":len(rows),"jobs":len(stored),
            "head_sha256":previous,"state":"complete-hash-chain-verified",
            "release_certified":False}
