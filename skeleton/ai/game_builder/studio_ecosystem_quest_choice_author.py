"""Authored quest alternative editing with source-bound replay and playable compile.

Edits existing original quest prose only; no stage graph, reward, evidence or
authority mutation. Both before and after paths are replayed by the canonical
quest engine and are never treated as externally fulfilled outcomes.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_author_revision import (
    REVISION_SCHEMA, preview_canon_revision,
)
from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress,
    replay_quest, step_quest,
)

CHOICE_AUTHOR_SCHEMA = "skeleton.game_builder.studio_quest_choice_author.v1"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical quest choice authoring") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _sample_quest_path(
    documents: Mapping[str, Any], stage_id: str, alternative: str,
) -> dict[str, object]:
    """Replay the shortest deterministic ancestor closure then chosen stage."""
    program = compile_quest_program(documents)
    stages = {stage.key: stage for stage in program.stages}
    if stage_id not in stages:
        raise StudioQuestError("unknown authored quest choice stage")
    needed: set[str] = set()

    def visit(key: str) -> None:
        for parent in stages[key].prerequisites:
            if parent not in needed:
                needed.add(parent)
                visit(parent)

    visit(stage_id)
    session = replay_quest(documents, [], authorized=True)
    actions: list[list[str]] = []
    for stage in program.stages:
        if stage.key not in needed:
            continue
        option = stage.alternatives[0]
        session = step_quest(
            session, documents, stage=stage.key,
            alternative=option, authorized=True)
        actions.append([stage.key, option])
    session = step_quest(
        session, documents, stage=stage_id,
        alternative=alternative, authorized=True)
    actions.append([stage_id, alternative])
    if replay_quest(documents, actions, authorized=True) != session:
        raise StudioQuestError("authored quest choice replay mismatch")
    return {
        "actions": actions,
        "session_digest": session.digest,
        "source_digest": session.source_digest,
        "progress": quest_progress(session, documents),
        "external_evidence_verified": False,
        "release_certified": False,
    }


def preview_quest_choice_revision(
    documents: Mapping[str, Any],
    *,
    stage_id: str,
    alternative_index: int,
    replacement: str,
    expected_source_digest: str,
    expected_alternative_digest: str,
    authorized: bool,
) -> tuple[dict[str, Any], bytes, dict[str, object], dict[str, object]]:
    """Compile a private revision and prove its authored quest choice is replayable.

    Two optimistic leases prevent applying an edit to the wrong source or to
    a silently changed stage alternative. The only modified source field is
    one already-authorized prose alternative. The resulting HTML is rendered
    by the canonical story compiler, not a shadow renderer.
    """
    if authorized is not True:
        raise PermissionError("quest choice authoring requires operator authorization")
    if (type(stage_id) is not str or not 1 <= len(stage_id) <= 512
            or stage_id != stage_id.strip()
            or any(ord(ch) < 32 for ch in stage_id)):
        raise StudioQuestError("invalid authored quest choice stage")
    if type(alternative_index) is not int or not 0 <= alternative_index < 8:
        raise StudioQuestError("invalid quest alternative index")
    if (type(replacement) is not str or not replacement
            or replacement != replacement.strip()
            or any(ord(ch) < 32 for ch in replacement)
            or len(replacement.encode("utf-8", "strict")) > 512):
        raise StudioQuestError("invalid authored quest alternative text")
    proof = audit_canon_source(documents, authorized=True)
    if (type(expected_source_digest) is not str
            or expected_source_digest != proof["source_digest"]):
        raise StudioQuestError("stale authored quest source lease")
    quest = documents.get("quest")
    if not isinstance(quest, Mapping):
        raise StudioQuestError("missing authored quest source")
    graph_name = "stage_graph" if quest.get("stage_graph") else "stages"
    graph = quest.get(graph_name)
    if type(graph) is not list or not 1 <= len(graph) <= 64:
        raise StudioQuestError("invalid authored quest stage graph")
    matches = [(index, stage) for index, stage in enumerate(graph)
               if type(stage) is dict and stage.get("id") == stage_id]
    if len(matches) != 1:
        raise StudioQuestError("unknown or ambiguous authored quest stage")
    stage_index, stage = matches[0]
    alternatives = stage.get("alternatives")
    if (type(alternatives) is not list
            or not 1 <= len(alternatives) <= 8
            or alternative_index >= len(alternatives)):
        raise StudioQuestError("unknown authored quest alternative index")
    previous = alternatives[alternative_index]
    if (type(previous) is not str or type(expected_alternative_digest) is not str
            or _digest(previous) != expected_alternative_digest
            or previous == replacement
            or replacement in alternatives):
        raise StudioQuestError("stale, duplicate or unchanged authored quest alternative")
    before_path = _sample_quest_path(documents, stage_id, previous)
    request = {
        "schema": REVISION_SCHEMA,
        "project_id": proof["project_id"],
        "expected_source_digest": expected_source_digest,
        "edits": [{
            "section": "quest",
            "path": [graph_name, stage_index, "alternatives", alternative_index],
            "value": replacement,
        }],
    }
    revised, html, receipt = preview_canon_revision(
        documents, request, authorized=True)
    after_path = _sample_quest_path(revised, stage_id, replacement)
    if (before_path["actions"][:-1] != after_path["actions"][:-1]
            or after_path["actions"][-1] != [stage_id, replacement]
            or before_path["source_digest"] == after_path["source_digest"]
            or receipt["base_source_digest"] != expected_source_digest
            or receipt["revised_source_digest"] !=
            audit_canon_source(revised, authorized=True)["source_digest"]):
        raise StudioQuestError("authored quest choice revision replay or source drift")
    detail: dict[str, object] = {
        "schema": CHOICE_AUTHOR_SCHEMA,
        "project_id": proof["project_id"],
        "quest_stage": stage_id,
        "alternative_index": alternative_index,
        "original_alternative_digest": expected_alternative_digest,
        "revised_alternative_digest": _digest(replacement),
        "base_source_digest": expected_source_digest,
        "revised_source_digest": receipt["revised_source_digest"],
        "playable_html_sha256": sha256(html).hexdigest(),
        "original_sample": before_path,
        "revised_sample": after_path,
        "revision_receipt": receipt,
        "original_catalog_unchanged": True,
        "playable_html_compiled": True,
        "file_write_performed": False,
        "native_genre_runtime_verified": False,
        "originality_rights_verified": False,
        "release_certified": False,
    }
    detail["author_digest"] = _digest(detail)
    return revised, html, receipt, detail
