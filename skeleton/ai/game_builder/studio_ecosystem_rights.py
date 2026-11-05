"""Fail-closed release/rights triage of source-authored studio packages."""
from __future__ import annotations
from typing import Any, Mapping

from .studio_ecosystem_quest import compile_quest_program, StudioQuestError
from .studio_ecosystem_assets import planned_assets
from .studio_ecosystem_audio import compile_cue_sheet


def release_requirements(documents: Mapping[str, Any]) -> dict[str, object]:
    program=compile_quest_program(documents)
    review=documents.get("verification")
    if (not isinstance(review,dict) or review.get("project_id")!=program.project_id
            or review.get("release_certified") is not False):
        raise StudioQuestError("invalid verification source")
    gates=review.get("quality_gates")
    blockers=review.get("release_blockers")
    if (not isinstance(gates,list) or not gates or not isinstance(blockers,list)
            or not blockers or len(set(blockers))!=len(blockers)):
        raise StudioQuestError("missing or duplicate release obligations")
    ids=set()
    for gate in gates:
        if not isinstance(gate,dict) or not isinstance(gate.get("id"),str):
            raise StudioQuestError("invalid quality gate")
        if gate["id"] in ids or gate.get("status")!="not_tested":
            raise StudioQuestError("unearned or duplicate quality gate")
        ids.add(gate["id"])
    if any(not isinstance(item,str) or not item for item in blockers):
        raise StudioQuestError("invalid blocker")
    assets=planned_assets(documents)
    audio=compile_cue_sheet(documents)
    return {"schema":"skeleton.game_builder.studio_release_obligations.v1",
            "project_id":program.project_id,
            "source_digest":program.source_digest,
            "quality_gates":[{"id":g["id"],"verified":False} for g in gates],
            "unresolved_release_blockers":list(blockers),
            "pending_art_jobs":len(assets["jobs"]),
            "pending_audio_cues":len(audio["cues"]),
            "rights_approved":False,"device_qualified":False,
            "release_certified":False}
