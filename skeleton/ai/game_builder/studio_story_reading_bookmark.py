"""Canonical source-bound original story reading bookmarks and safe review.

A bookmark is a private reader/editor position, never a quest action or a
claim of gameplay progression. All context is recompiled from source and
cannot be supplied by an untrusted bookmark request or receipt.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import re
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError, compile_quest_program
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from .studio_ecosystem_story_accessibility import compile_story_accessibility
from .studio_ecosystem_story_html import story_source

SCHEMA = "skeleton.game_builder.story_reading_bookmark.v1"
REQUEST_SCHEMA = "skeleton.game_builder.story_reading_bookmark_request.v1"
MAX_NOTE_CHARS = 240
MAX_RECEIPT_BYTES = 16384
MAX_HTML_BYTES = 32768
_MAX_STAGES = 128
_CSS = (
    ":root{color-scheme:dark;background:#142334;color:#f4f7fb;"
    "font:16px system-ui}body{max-width:60rem;margin:auto;padding:2rem}"
    "section{border:1px solid #8fb7d0;border-radius:12px;padding:1.5rem}"
    "dt{font-weight:700;margin-top:1rem}dd{margin-left:0}"
    "a{color:#b6e4ff}a:focus-visible{outline:3px solid #ffdc8b}"
    "pre{white-space:pre-wrap;overflow-wrap:anywhere}"
)


def _note(value: object) -> str:
    if (type(value) is not str or not 1 <= len(value) <= MAX_NOTE_CHARS
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise StudioQuestError("reading bookmark note must be bounded single-line text")
    return value


def _request(value: object) -> dict[str, str]:
    if type(value) is not dict or set(value) != {
            "schema", "stage_id", "reader_note"}:
        raise StudioQuestError("reading bookmark requires exact typed fields")
    if value["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported reading bookmark request schema")
    stage_id = value["stage_id"]
    if (type(stage_id) is not str or not 1 <= len(stage_id) <= 128
            or re.fullmatch(r"[a-zA-Z0-9_-]+", stage_id) is None):
        raise StudioQuestError("invalid reading bookmark stage")
    note = _note(value["reader_note"])
    if len(_canonical(value)) > 1024:
        raise StudioQuestError("reading bookmark request exceeds byte budget")
    return {"stage_id": stage_id, "reader_note": note}


def compile_story_reading_bookmark(
    documents: Mapping[str, Any], request: object, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, object]:
    """Compile one exact-source reader position with context and no mutations."""
    if authorized is not True:
        raise PermissionError("story bookmark compilation requires operator authorization")
    _lease(expected_source_digest, "reading bookmark source")
    fields = _request(request)
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale reading bookmark source lease")
    story = story_source(documents)
    accessible = compile_story_accessibility(documents, authorized=True)
    if (story["source_digest"] != expected_source_digest
            or accessible["source_digest"] != expected_source_digest
            or story["project_id"] != program.project_id
            or accessible["project_id"] != program.project_id):
        raise StudioQuestError("reading bookmark source owners diverged")
    stages = story["stages"]
    if type(stages) is not list or not 1 <= len(stages) <= _MAX_STAGES:
        raise StudioQuestError("reading bookmark stage count exceeds bound")
    index = next((i for i, stage in enumerate(stages)
                  if stage["id"] == fields["stage_id"]), None)
    if index is None:
        raise StudioQuestError("reading bookmark references an unauthored stage")
    stage = stages[index]
    if type(stage["alternatives"]) is not list:
        raise StudioQuestError("invalid authored bookmark choices")
    before = stages[index - 1]["id"] if index else None
    after = stages[index + 1]["id"] if index + 1 < len(stages) else None
    excerpt = {
        "stage_id": stage["id"], "scene_id": stage["scene_id"],
        "authored_goal": stage["authored_goal"],
        "authored_decision": stage["authored_decision"],
        "alternatives": list(stage["alternatives"]),
        "prerequisites": list(stage["prerequisites"]),
        "sandbox_reward": stage["reward"],
    }
    payload: dict[str, object] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "accessibility_manifest_digest": accessible["manifest_digest"],
        "stage_count": len(stages), "stage_index": index,
        "reader_note": fields["reader_note"], "stage": excerpt,
        "previous_stage_id": before, "next_stage_id": after,
        "reading_position_only": True,
        "quest_action_committed": False, "file_write_performed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    payload["bookmark_digest"] = _digest(payload)
    if len(_canonical(payload)) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("reading bookmark receipt exceeds byte budget")
    return payload


def replay_story_reading_bookmark(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, object]:
    """Reject forged stage context even when the caller recomputed a digest."""
    if authorized is not True:
        raise PermissionError("story bookmark replay requires operator authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid reading bookmark receipt")
    stage = receipt.get("stage")
    if type(stage) is not dict:
        raise StudioQuestError("invalid reading bookmark stage context")
    rebuilt = compile_story_reading_bookmark(
        documents, {
            "schema": REQUEST_SCHEMA, "stage_id": stage.get("stage_id"),
            "reader_note": receipt.get("reader_note"),
        }, authorized=True, expected_source_digest=expected_source_digest)
    if receipt != rebuilt:
        raise StudioQuestError("reading bookmark differs from canonical source replay")
    return rebuilt


def render_story_reading_bookmark_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> bytes:
    """A non-executable accessible reading handoff with source proof."""
    verified = replay_story_reading_bookmark(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest)
    stage = verified["stage"]
    digest = b64encode(sha256(_CSS.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; base-uri 'none'; form-action 'none'; "
           "style-src 'sha256-" + digest + "'")
    safe = lambda value: escape(value, quote=True)
    alternatives = "".join("<li>" + safe(choice) + "</li>"
                           for choice in stage["alternatives"])
    dependencies = "".join("<li>" + safe(dep) + "</li>"
                           for dep in stage["prerequisites"])
    page = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\""
        + safe(csp) + "\"><title>Original story reading bookmark</title>"
        "<style>" + _CSS + "</style></head><body><main>"
        "<h1>Original story reading bookmark</h1>"
        "<p>Reader position only. No quest action was committed, no external "
        "evidence was verified, and no native gameplay or release is certified.</p>"
        "<section><h2>" + safe(stage["stage_id"]) + "</h2><dl>"
        "<dt>Scene</dt><dd>" + safe(stage["scene_id"]) + "</dd>"
        "<dt>Authored goal</dt><dd>" + safe(stage["authored_goal"]) + "</dd>"
        "<dt>Authored decision</dt><dd>" + safe(stage["authored_decision"]) + "</dd>"
        "<dt>Sandbox reward</dt><dd>" + safe(stage["sandbox_reward"]) + "</dd>"
        "<dt>Reader note</dt><dd>" + safe(verified["reader_note"]) + "</dd>"
        "</dl><h3>Authored alternatives</h3><ol>" + alternatives + "</ol>"
        "<h3>Prerequisites</h3><ul>" + (dependencies or "<li>None</li>") + "</ul>"
        "</section><p>Source digest: <code>" + verified["source_digest"] + "</code></p>"
        "<p>Bookmark digest: <code>" + verified["bookmark_digest"] + "</code></p>"
        "</main></body></html>"
    )
    raw = page.encode("utf-8")
    if len(raw) > MAX_HTML_BYTES:
        raise StudioQuestError("reading bookmark HTML exceeds byte budget")
    return raw
