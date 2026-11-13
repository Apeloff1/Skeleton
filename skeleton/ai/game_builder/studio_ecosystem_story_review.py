"""Strictly replay an offline browser transcript against authoritative source.

A browser is not trusted to assert earned rewards, endings, or certification.
Only the original Python quest state machine can recompute the stage history.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest, quest_progress,
)

SCHEMA="skeleton.game_builder.offline_story_choices.v1"
KEYS={"schema","project_id","source_digest","choices","external_evidence_verified",
      "native_genre_runtime_verified","release_certified"}


def inspect_browser_story_receipt(raw: bytes, documents: Mapping[str, Any], *,
                                  authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("browser history inspection requires operator authorization")
    if not isinstance(raw,bytes) or not 1<=len(raw)<=65536:
        raise StudioQuestError("missing or oversized offline quest transcript")
    def unique(pairs: list[tuple[str,object]]) -> dict[str,object]:
        found={}
        for name,value in pairs:
            if name in found:
                raise StudioQuestError("duplicate transcript field")
            found[name]=value
        return found
    try:
        payload=json.loads(raw.decode("utf-8","strict"),object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               StudioQuestError("nonfinite transcript")))
    except (UnicodeError,ValueError) as exc:
        raise StudioQuestError("invalid offline transcript JSON") from exc
    program=compile_quest_program(documents)
    if (not isinstance(payload,dict) or set(payload)!=KEYS
            or payload["schema"]!=SCHEMA
            or payload["project_id"]!=program.project_id
            or payload["source_digest"]!=program.source_digest
            or any(payload[x] is not False for x in (
                "external_evidence_verified","native_genre_runtime_verified",
                "release_certified"))):
        raise StudioQuestError("unqualified or source-mismatched offline transcript")
    session=replay_quest(documents,payload["choices"],authorized=True)
    progress=quest_progress(session,documents)
    return {"schema":"skeleton.game_builder.offline_story_replay_review.v1",
            "project_id":program.project_id,
            "session_digest":session.digest,
            "completed_stages":list(session.completed),
            "sandbox_endings_eligible":progress["sandbox_endings_eligible"],
            "unmet_ending_predicates":progress["unmet_ending_predicates"],
            "replayed_from_authoritative_source":True,
            "browser_transcript_independently_attested":False,
            "release_certified":False}
