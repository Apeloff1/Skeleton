"""Strictly replay an offline browser transcript against authoritative source.

A browser is not trusted to assert earned rewards, endings, or certification.
Only the original Python quest state machine can recompute the stage history.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest, quest_progress,
    step_quest,
)

SCHEMA="skeleton.game_builder.offline_story_choices.v1"
KEYS={"schema","project_id","source_digest","choices","external_evidence_verified",
      "native_genre_runtime_verified","release_certified"}


def _replay_browser_story_receipt(raw: bytes, documents: Mapping[str, Any], *,
                                  authorized: bool):
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
    return program, session


def inspect_browser_story_receipt(raw: bytes, documents: Mapping[str, Any], *,
                                  authorized: bool) -> dict[str, object]:
    program, session = _replay_browser_story_receipt(raw, documents, authorized=authorized)
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


def preview_browser_story_choice(raw: bytes, documents: Mapping[str, Any], *,
                                 stage: str, alternative: str,
                                 authorized: bool) -> dict[str, object]:
    """Replay a browser checkpoint, then simulate one authored choice without committing.

    This is an independently recomputed Python counterpart of the browser
    preview. A browser receipt grants no rights or evidence and cannot
    declare an ending earned outside the authored sandbox.
    """
    program, session = _replay_browser_story_receipt(raw, documents,
                                                     authorized=authorized)
    if type(stage) is not str or type(alternative) is not str:
        raise StudioQuestError("invalid preview choice identity")
    before = quest_progress(session, documents)
    candidate = step_quest(session, documents, stage=stage,
                           alternative=alternative, authorized=True)
    after = quest_progress(candidate, documents)
    newly = sorted(set(after["sandbox_endings_eligible"])
                   - set(before["sandbox_endings_eligible"]))
    return {
        "schema": "skeleton.game_builder.offline_story_choice_preview.v1",
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "base_session_digest": session.digest,
        "candidate_session_digest": candidate.digest,
        "stage_id": stage,
        "alternative": alternative,
        "newly_eligible_sandbox_endings": newly,
        "unmet_ending_predicates": after["unmet_ending_predicates"],
        "baseline_session_unchanged": True,
        "replayed_from_authoritative_source": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }


def compare_browser_story_receipts(current_raw: bytes, candidate_raw: bytes,
                                   documents: Mapping[str, Any], *,
                                   authorized: bool) -> dict[str, object]:
    """Compare two untrusted browser histories after independent canonical replay.

    This is a nonmutating authored-sandbox diff, not a merge, a new save, or
    evidence of external world consequences. Both histories must be bound to
    the exact same current authoritative quest source.
    """
    program, current = _replay_browser_story_receipt(current_raw, documents,
                                                     authorized=authorized)
    other_program, candidate = _replay_browser_story_receipt(candidate_raw,
                                                             documents,
                                                             authorized=authorized)
    if program.source_digest != other_program.source_digest:
        raise StudioQuestError("cross-source story comparison refused")
    common = 0
    for left, right in zip(current.choices, candidate.choices):
        if left != right:
            break
        common += 1
    before = quest_progress(current, documents)
    after = quest_progress(candidate, documents)
    previous = set(before["sandbox_endings_eligible"])
    proposed = set(after["sandbox_endings_eligible"])
    return {
        "schema": "skeleton.game_builder.offline_story_checkpoint_compare.v1",
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "current_session_digest": current.digest,
        "candidate_session_digest": candidate.digest,
        "common_action_prefix": common,
        "current_only_actions": [list(pair) for pair in current.choices[common:]],
        "candidate_only_actions": [list(pair) for pair in candidate.choices[common:]],
        "newly_eligible_sandbox_endings": sorted(proposed - previous),
        "no_longer_eligible_sandbox_endings": sorted(previous - proposed),
        "unmet_candidate_ending_predicates": after["unmet_ending_predicates"],
        "current_session_unchanged": True,
        "candidate_session_unchanged": True,
        "replayed_from_authoritative_source": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
