"""Read-only source-state report; does not run native model or imply release."""
from __future__ import annotations
from .contracts import identifier,digest_id,refuse
from .store import WorkOrderStore
def snapshot(root,*,tenant,subject,model_sha256):
    with WorkOrderStore(root,readonly=True) as queue:
        audit=queue.audit()
        jobs=queue.list_jobs(tenant=identifier(tenant),subject=identifier(subject),
                model_sha256=digest_id(model_sha256),limit=100)
        return {"schema":"offline-ai-work-report.v1","integrity":audit,
            "jobs_observed":len(jobs),
            "native_unknown":sum(x["status"] in ("dispatch-unknown","held") for x in jobs),
            "committed":sum(x["status"]=="committed" for x in jobs),
            "operator_approval_still_required":True,
            "real_model_tested_by_this_report":False,
            "release_certified":False}
