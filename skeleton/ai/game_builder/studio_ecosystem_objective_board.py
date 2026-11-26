"""Source-bound playable-handoff objective board and script-free HTML preview.

The board joins canonical quest replay with original scene/NPC authoring cues.
It does not pretend that a scene was played or that an NPC spoke.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import (
    StudioQuestError, available_stages, compile_quest_program, replay_quest,
)

OBJECTIVE_BOARD_SCHEMA = "skeleton.game_builder.studio_objective_board.v1"
MAX_OBJECTIVE_PAGE = 16
MAX_OBJECTIVE_HTML_BYTES = 64 * 1024


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical objective board") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _lease(value: object, kind: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise StudioQuestError("invalid " + kind + " lease")
    return value


def _safe_text(value: object) -> str:
    if type(value) is not str or len(value) > 512:
        raise StudioQuestError("invalid objective HTML text")
    return escape(value, quote=True)


def render_objective_board_html(board: Mapping[str, Any]) -> str:
    """Render accessible offline HTML with no JavaScript or remote resources."""
    if (not isinstance(board, Mapping)
            or board.get("schema") != OBJECTIVE_BOARD_SCHEMA
            or type(board.get("objectives")) is not list
            or len(board["objectives"]) > MAX_OBJECTIVE_PAGE):
        raise StudioQuestError("invalid objective board HTML input")
    project = _safe_text(board.get("project_id"))
    rows: list[str] = []
    for item in board["objectives"]:
        if type(item) is not dict or type(item.get("scene_links")) is not list:
            raise StudioQuestError("invalid objective HTML card")
        stage = _safe_text(item.get("stage_id"))
        status = _safe_text(item.get("status"))
        if status not in ("completed", "available", "locked"):
            raise StudioQuestError("invalid objective HTML status")
        reward = _safe_text(item.get("reward"))
        scenes = []
        for scene in item["scene_links"]:
            if type(scene) is not dict:
                raise StudioQuestError("invalid objective HTML scene")
            scenes.append(
                "<li>" + _safe_text(scene.get("scene_id")) + " — "
                + _safe_text(scene.get("site")) + " ("
                + _safe_text(scene.get("npc_id")) + ")</li>"
            )
        rows.append(
            "<li><section aria-label=\"" + stage + "\"><h2>" + stage
            + "</h2><p>Status: " + status + "</p><p>Reward: "
            + reward + "</p><ul>" + "".join(scenes) + "</ul></section></li>"
        )
    html = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta http-equiv=\"Content-Security-Policy\" "
        "content=\"default-src 'none'; base-uri 'none'; form-action 'none'\">"
        "<title>Original quest objectives</title></head><body>"
        "<main><h1>Original quest objectives: " + project + "</h1>"
        "<p>Authoring preview only; no external evidence or gameplay certified.</p>"
        "<ol>" + "".join(rows) + "</ol></main></body></html>"
    )
    if len(html.encode("utf-8", "strict")) > MAX_OBJECTIVE_HTML_BYTES:
        raise StudioQuestError("objective HTML exceeds output budget")
    return html


def page_objectives(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
    offset: int = 0, limit: int = 8,
    include_html: bool = False,
) -> dict[str, object]:
    """Compile source-verified quest objectives and linked NPC scene cues."""
    if authorized is not True:
        raise PermissionError("objective board requires operator authorization")
    _lease(expected_source_digest, "objective source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "objective session")
    if (type(offset) is not int or offset < 0
            or type(limit) is not int or not 1 <= limit <= MAX_OBJECTIVE_PAGE
            or type(include_html) is not bool):
        raise StudioQuestError("invalid objective board options")
    if offset and expected_session_digest is None:
        raise StudioQuestError("objective continuation requires session lease")
    staged = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest)
    program = compile_quest_program(documents)
    session = replay_quest(documents, actions, authorized=True)
    if session.digest != staged["session_digest"]:
        raise StudioQuestError("objective board staging replay mismatch")
    if expected_session_digest is not None and session.digest != expected_session_digest:
        raise StudioQuestError("stale objective board session lease")
    if offset > len(program.stages):
        raise StudioQuestError("objective page exceeds authored stage count")
    completed = set(session.completed)
    available = set(available_stages(session, documents))
    chosen = dict(session.choices)
    by_stage: dict[str, list[dict[str, object]]] = {}
    for card in staged["cards"]:
        by_stage.setdefault(card["quest_stage"], []).append({
            "scene_id": card["scene_id"], "npc_id": card["npc_id"],
            "site": card["site"], "status": card["status"],
            "card_digest": card["card_digest"],
        })
    objectives: list[dict[str, object]] = []
    for stage in program.stages[offset:offset + limit]:
        status = ("completed" if stage.key in completed else
                  "available" if stage.key in available else "locked")
        objectives.append({
            "stage_id": stage.key,
            "status": status,
            "prerequisites": list(stage.prerequisites),
            "unmet_prerequisites": sorted(set(stage.prerequisites) - completed),
            "reward": stage.reward,
            "authored_alternatives": list(stage.alternatives),
            "selected_alternative": chosen.get(stage.key),
            "scene_links": by_stage.get(stage.key, []),
            "npc_dialogue_spoken_verified": False,
        })
    payload: dict[str, object] = {
        "schema": OBJECTIVE_BOARD_SCHEMA,
        "project_id": program.project_id,
        "source_digest": staged["source_digest"],
        "quest_source_digest": program.source_digest,
        "session_digest": session.digest,
        "offset": offset, "limit": limit,
        "total_objectives": len(program.stages),
        "completed_objectives": len(completed),
        "available_objective_ids": [
            stage.key for stage in program.stages if stage.key in available
        ],
        "next_offset": offset + len(objectives)
        if offset + len(objectives) < len(program.stages) else None,
        "objectives": objectives,
        "source_unchanged": True, "file_write_performed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    if include_html:
        html = render_objective_board_html(payload)
        payload["html_preview"] = html
        payload["html_sha256"] = sha256(html.encode("utf-8")).hexdigest()
    if len(_canonical(payload)) > 128 * 1024:
        raise StudioQuestError("objective board receipt exceeds byte budget")
    payload["board_digest"] = _digest(payload)
    return payload
