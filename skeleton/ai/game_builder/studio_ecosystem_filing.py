"""Make every producer artifact submission reference actual locally verified bytes."""
from __future__ import annotations

from .studio_ecosystem_journal import WorkJournal, HEX
from .studio_ecosystem_spool import ArtifactSpool
from .studio_ecosystem_quest import StudioQuestError


def submit_local_artifact(journal: WorkJournal, spool: ArtifactSpool, *,
                          task_id: str, worker: str, token: str,
                          sha256: str, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("verified local submission requires operator authorization")
    if not isinstance(sha256,str) or not HEX.fullmatch(sha256):
        raise StudioQuestError("malformed submitted artifact identity")
    actual_size=spool.verify(sha256)
    journal.submit(task_id,worker=worker,token=token,
                   artifact_sha256=sha256,authorized=True)
    return {"schema":"skeleton.game_builder.studio_local_submission.v1",
            "task_id":task_id,"sha256":sha256,"verified_bytes":actual_size,
            "local_content_integrity_verified":True,
            "external_provenance_verified":False,"release_certified":False}


def review_local_artifact(journal: WorkJournal, spool: ArtifactSpool, *,
                          task_id: str, reviewer: str,
                          accepted: bool, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("independent local artifact review requires authorization")
    current=journal.snapshot()["tasks"].get(task_id)
    if not isinstance(current,dict) or current["status"]!="submitted":
        raise StudioQuestError("no pending local artifact to review")
    digest=current["submitted_sha"]
    if not isinstance(digest,str) or not HEX.fullmatch(digest):
        raise StudioQuestError("submitted local artifact SHA is unavailable")
    spool.verify(digest)
    journal.review(task_id,reviewer=reviewer,accepted=accepted,authorized=True)
    return {"task_id":task_id,"sha256":digest,
            "independent_reviewer_recorded":True,
            "review_accepted_as_claim":accepted,
            "external_evidence_verified":False,"rights_verified":False,
            "release_certified":False}
