"""Bounded trustworthy queue observations; no sensitive user prompts are returned."""
from __future__ import annotations
from .audit import verify_audit
from .canonical import require_int
from .spec import require_id
from .store import JobStore
from .errors import deny

STATUSES=("pending","running","completed","failed","held","cancelled","cancel_requested")


def metrics(store:JobStore,tenant:str,*,top:int=16)->dict:
    if type(store) is not JobStore:
        deny("metrics-store")
    require_id(tenant,"tenant")
    require_int(top,1,64,"metrics-top")
    with store.tx.exclusive() as db:
        proof=verify_audit(db)
        counts={state:0 for state in STATUSES}
        for state,count in db.execute(
          "SELECT state,COUNT(*) FROM ai_durable_jobs WHERE tenant=? GROUP BY state",
          (tenant,)
        ):
            if state not in counts:
                deny("metrics-state")
            counts[state]=count
        recent=db.execute("""SELECT job_id,state,attempt,updated_ms
           FROM ai_durable_jobs WHERE tenant=? ORDER BY updated_ms DESC,job_id LIMIT ?""",
           (tenant,top)).fetchall()
        return {
          "schema":"skeleton.ai.job.metrics.v1","tenant":tenant,"states":counts,
          "recent":[{"job_id":j,"state":s,"attempt":n,"updated_ms":t}
                    for j,s,n,t in recent],
          "audit_events":proof["events"],"audit_head":proof["head"],
          "verified":proof["verified"],"real_model_tested":False,
        }
