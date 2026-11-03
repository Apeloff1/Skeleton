"""Independent full-store integrity checks before declaring queue recoverable.

Unlike hash-chain inspection alone, this validates every job's typed payload,
dependency identity, terminal state and source-bound result receipt.
"""
from __future__ import annotations
from .audit import verify_audit
from .canonical import decode
from .errors import deny
from .result import JobResult
from .store import JobStore


def verify_store(store:JobStore,*,max_jobs:int=100000)->dict:
    if type(store) is not JobStore:
        deny("invariants-store")
    from .canonical import require_int
    require_int(max_jobs,1,100000,"invariants-cap")
    with store.tx.exclusive() as db:
        event_proof=verify_audit(db)
        rows=db.execute(
           "SELECT job_id FROM ai_durable_jobs ORDER BY job_id LIMIT ?",
           (max_jobs+1,)
        ).fetchall()
        if len(rows)>max_jobs:
            deny("invariants-volume")
        terminal=0
        pending=0
        held=0
        for job_id, in rows:
            row=store._row(db,job_id)
            spec=store._parse(row)
            state=row[13]
            if state in ("completed","failed","cancelled"):
                terminal+=1
            elif state=="pending":
                pending+=1
            elif state=="held":
                held+=1
            if state=="completed":
                if row[19] is None or row[18] is None:
                    deny("invariants-missing-result")
                rec=decode(row[19])
                result=JobResult(
                    rec["text"],rec["output_sha256"],rec["model_sha256"],
                    rec["tokenizer_sha256"],rec["prompt_tokens"],
                    rec["generated_tokens"],rec["original_request_id"],
                )
                if result.digest!=row[18]:
                    deny("invariants-result-digest")
                if result.original_request_id!=spec.request_id:
                    deny("invariants-result-request")
            elif row[19] is not None or row[18] is not None:
                deny("invariants-phantom-result")
            for dep in spec.dependencies:
                row_dep=db.execute(
                  "SELECT tenant,user_id FROM ai_durable_jobs WHERE job_id=?", (dep,)
                ).fetchone()
                if row_dep is None or row_dep!=(spec.owner.tenant,spec.owner.user):
                    deny("invariants-dependency")
            deps=db.execute(
              "SELECT dependency_id FROM ai_job_deps WHERE job_id=? ORDER BY dependency_id",
              (job_id,)
            ).fetchall()
            if [d[0] for d in deps]!=sorted(spec.dependencies):
                deny("invariants-dependency-parity")
        return {
            "schema":"skeleton.ai.jobs.integrity.v1","verified":True,
            "jobs":len(rows),"terminal":terminal,"pending":pending,"held":held,
            "audit_events":event_proof["events"],"audit_sha":event_proof["head"],
            "native_model_qualified":False,
        }
