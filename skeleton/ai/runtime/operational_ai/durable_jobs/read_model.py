"""Bounded, owner-scoped job views; never expose another principal's question."""
from __future__ import annotations
from .audit import verify_audit
from .canonical import require_int
from .errors import deny
from .pagination import CursorCodec
from .spec import JobIdentity
from .store import JobStore


def list_jobs(store:JobStore,owner:JobIdentity,*,page_size:int=32,
              last_job_id:str|None=None)->dict:
    if type(store) is not JobStore or type(owner) is not JobIdentity:
        deny("read-model-contract")
    require_int(page_size,1,64,"read-page-size")
    from .spec import require_id
    if last_job_id is not None:
        require_id(last_job_id,"read-cursor")
    with store.tx.exclusive() as db:
        verify_audit(db)
        conditions="tenant=? AND user_id=? AND session_id=? AND model_sha=? AND tokenizer_sha=?"
        args=[
            owner.tenant,owner.user,owner.session,
            owner.model_sha256,owner.tokenizer_sha256,
        ]
        if last_job_id is not None:
            conditions+=" AND job_id>?"
            args.append(last_job_id)
        rows=db.execute("""SELECT job_id FROM ai_durable_jobs WHERE """+
                        conditions+" ORDER BY job_id LIMIT ?",
                        tuple(args+[page_size+1])).fetchall()
        has_more=len(rows)>page_size
        names=[r[0] for r in rows[:page_size]]
        visible=[store._public(store._row(db,name)) for name in names]
        return {
            "schema":"skeleton.ai.jobs.page.v1",
            "owner":owner.principal,"items":visible,
            "next_job_id":names[-1] if has_more else None,
            "has_more":has_more,
            "verified":True,
        }
