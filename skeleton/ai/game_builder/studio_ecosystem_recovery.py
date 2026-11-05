"""Read-only recovery inspection for studio jobs and content-addressed claims."""
from __future__ import annotations

from .studio_ecosystem_catalog import read_blueprint
from .studio_ecosystem_fence import assert_source_fence
from .studio_ecosystem_journal import WorkJournal
from .studio_ecosystem_spool import ArtifactSpool
from .studio_ecosystem_quest import StudioQuestError


def inspect_resumption(journal: WorkJournal, spool: ArtifactSpool, *,
                       authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("recovery inspection requires operator authorization")
    fence=assert_source_fence(journal,read_blueprint(journal.project),authorized=True)
    snapshot=journal.snapshot()
    event_audit=journal.verify_events()
    missing=[]
    pending=[]
    recovered=[]
    for task_id,task in sorted(snapshot["tasks"].items()):
        if task["status"]=="leased":
            recovered.append({"task_id":task_id,"worker":task["worker"],
                              "attempt":task["attempt"],
                              "manual_recovery_required":True})
        elif task["status"]=="pending":
            pending.append(task_id)
        elif task["status"] in ("submitted","reviewed_claim"):
            fingerprint=task["submitted_sha"]
            try:
                spool.verify(fingerprint)
            except (StudioQuestError,OSError):
                missing.append(task_id)
    return {"schema":"skeleton.game_builder.studio_work_resume.v1",
            "project_id":journal.project,"source_fence":fence,
            "event_audit":event_audit,"unresolved_claim_artifacts":missing,
            "pending_tasks":pending,"leases_requiring_manual_recovery":recovered,
            "recovery_safe_for_review":not missing and not recovered,
            "tasks_auto_released":0,
            "external_release_evidence_verified":False,
            "release_certified":False}
