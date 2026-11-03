"""Safe recovery inspection; never auto-execute a held native-model request."""
from __future__ import annotations
from .errors import deny
from .spec import JobIdentity
from .store import JobStore
from .canonical import require_int


def inspect_hold(store:JobStore,job_id:str,owner:JobIdentity,*,now_ms:int)->dict:
    if type(store) is not JobStore:
        deny("recovery-store")
    require_int(now_ms,0,2**63-1,"recovery-clock")
    row=store.inspect(job_id,owner)
    if row["state"]!="held":
        deny("recovery-not-held")
    audits=store.audit(job_id,owner)
    return {
      "schema":"skeleton.ai.job.recovery.v1","job_id":job_id,
      "last_failure":row["failure_code"],
      "attempt":row["attempt"],"expired":now_ms>=row["expires_ms"],
      "events":len(audits),"last_event_sha":audits[-1]["sha256"] if audits else None,
      "automatic_retry_allowed":False,
      "required_action":"inspect-authoritative-chat-receipt-and-approve-explicit-reconciliation",
    }
