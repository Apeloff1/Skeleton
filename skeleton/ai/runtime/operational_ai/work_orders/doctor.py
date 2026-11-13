"""Read-only exact-subject queue diagnostics; no model boot or native generation."""
from __future__ import annotations
from .store import WorkOrderStore
from .contracts import refuse
def inspect(store,*,tenant,subject,model_sha256):
    if not isinstance(store,WorkOrderStore):refuse("real private queue required")
    result=store.audit()
    rows=store.list_jobs(tenant=tenant,subject=subject,
                         model_sha256=model_sha256,limit=100)
    return {"schema":"offline-ai-work-doctor.v2",
            "integrity":result,
            "observed_jobs":len(rows),
            "uncertain_native":sum(x["status"] in ("dispatch-unknown","held") for x in rows),
            "automatic_native_retry_allowed":False,
            "source_only":True,"release_certified":False}
