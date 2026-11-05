"""Evidence-aware DAG projection: submitted jobs depend only on admitted parents."""
from __future__ import annotations
from .errors import deny
from .spec import JobIdentity,require_id
from .store import JobStore

SUCCESS="completed"
TERMINAL=("completed","cancelled","failed")
UNCERTAIN=("held","cancel_requested")


def status(store:JobStore,job_id:str,owner:JobIdentity)->dict:
    if type(store) is not JobStore:
        deny("dependency-store")
    require_id(job_id,"job")
    parents=store.dependencies(job_id,owner)
    own=store.inspect(job_id,owner)
    ready=all(parent["state"]==SUCCESS for parent in parents)
    blocked=any(parent["state"] in ("failed","cancelled","held") for parent in parents)
    return {
      "job_id":job_id,"required":len(parents),"satisfied":sum(
        parent["state"]=="completed" for parent in parents
      ),"blocked":blocked,"ready":ready and not blocked,
      "states":{parent["job_id"]:parent["state"] for parent in parents},
      "own_state":own["state"],
    }
