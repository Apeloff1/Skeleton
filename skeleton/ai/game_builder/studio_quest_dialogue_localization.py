"""Human-reviewed localization of original NPC dialogue, with exact source leases.

Translations affect display text only. No speaker, quest action, NPC trust,
ending, or canonical session can be altered by localization authoring.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import os
from pathlib import Path
import re
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest, start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json
from .studio_quest_dialogue import (
    replay_quest_dialogue, compile_quest_dialogue_handoff,
)

SCHEMA = "skeleton.game_builder.studio_quest_dialogue_localization.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_dialogue_localization_plan.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_dialogue_localized_handoff.v1"
PROMPT = "review translations of my original NPC quest dialogue"
FILENAME = "studio_quest_dialogue_localization.json"
MAX_SOURCE = 256 * 1024
MAX_PLAN = 262144
MAX_RECEIPT = 393216
MAX_HTML = 524288
MAX_ROWS = 128


def _text(value: object, label: str, maximum: int) -> str:
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or value.strip() != value
            or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f
                   or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid dialogue localization " + label)
    return value


def _locale(value: object) -> str:
    if type(value) is not str or re.fullmatch(
            r"[a-z]{2,3}(?:-[A-Z]{2})?", value) is None:
        raise StudioQuestError("invalid bounded dialogue locale")
    return value


def propose_dialogue_localization(
    documents: Mapping[str, Any], npc_receipt: object, dialogue_receipt: object,
    prompt: str, locale: str, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dialogue localization proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported dialogue localization prompt")
    _lease(expected_source_digest, "dialogue localization source")
    _lease(expected_initial_session_digest, "dialogue localization initial session")
    checked_locale = _locale(locale)
    dialogue = replay_quest_dialogue(
        documents, npc_receipt, dialogue_receipt, authorized=True)
    if not dialogue["playable_handoff_allowed"]:
        raise StudioQuestError("dialogue localization requires reviewed original dialogue")
    if (dialogue["source_digest"] != expected_source_digest
            or dialogue["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale dialogue localization source or session")
    plan = {
        "schema": PLAN_SCHEMA, "locale": checked_locale,
        "dialogue_digest": dialogue["dialogue_digest"],
        "rows": [
            {"stage_id": x["stage_id"], "choice": x["choice"],
             "beat_index": x["beat_index"], "speaker": x["speaker"],
             "source_text": x["text"], "translation": x["text"],
             "reviewed": False}
            for x in dialogue["authoring"]["lines"]
        ],
    }
    if len(_canonical(plan)) > MAX_PLAN:
        raise StudioQuestError("dialogue localization plan exceeds byte budget")
    return plan


def _plan(value: object, dialogue: Mapping[str, Any]) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {
            "schema", "locale", "dialogue_digest", "rows"}
            or value.get("schema") != PLAN_SCHEMA
            or len(_canonical(value)) > MAX_PLAN):
        raise StudioQuestError("invalid typed dialogue localization plan")
    if value["dialogue_digest"] != dialogue["dialogue_digest"]:
        raise StudioQuestError("dialogue localization source receipt changed")
    rows = value["rows"]
    original = dialogue["authoring"]["lines"]
    if (type(rows) is not list or len(rows) != len(original)
            or len(rows) > MAX_ROWS):
        raise StudioQuestError("dialogue translation coverage differs from original")
    clean = []
    for source, row in zip(original, rows):
        if type(row) is not dict or set(row) != {
                "stage_id", "choice", "beat_index", "speaker",
                "source_text", "translation", "reviewed"}:
            raise StudioQuestError("invalid dialogue translation row")
        if (row["stage_id"] != source["stage_id"]
                or row["choice"] != source["choice"]
                or row["beat_index"] != source["beat_index"]
                or row["speaker"] != source["speaker"]
                or row["source_text"] != source["text"]):
            raise StudioQuestError("dialogue translation changed canonical source identity")
        if type(row["reviewed"]) is not bool:
            raise StudioQuestError("dialogue translation review must be boolean")
        clean.append({
            "stage_id": source["stage_id"], "choice": source["choice"],
            "beat_index": source["beat_index"], "speaker": source["speaker"],
            "source_text": source["text"],
            "translation": _text(row["translation"], "translation", 2048),
            "reviewed": row["reviewed"],
        })
    return {"schema": PLAN_SCHEMA, "locale": _locale(value["locale"]),
            "dialogue_digest": dialogue["dialogue_digest"], "rows": clean}


def compile_dialogue_localization(
    documents: Mapping[str, Any], npc_receipt: object, dialogue_receipt: object,
    authoring: object, *, authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dialogue localization compile requires authorization")
    _lease(expected_source_digest, "dialogue localization source")
    _lease(expected_initial_session_digest, "dialogue localization initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE:
        raise StudioQuestError("dialogue localization source exceeds byte budget")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    dialogue = replay_quest_dialogue(
        documents, npc_receipt, dialogue_receipt, authorized=True)
    if (program.source_digest != expected_source_digest
            or initial.digest != expected_initial_session_digest
            or dialogue["source_digest"] != expected_source_digest
            or dialogue["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale dialogue localization source or session")
    plan = _plan(authoring, dialogue)
    session = replay_quest(
        documents, dialogue["authoring"]["actions"], authorized=True)
    if session.digest != dialogue["session_digest"]:
        raise StudioQuestError("dialogue localization canonical session diverged")
    reviewed = bool(plan["rows"]) and all(x["reviewed"] for x in plan["rows"])
    if _canonical(documents) != before:
        raise StudioQuestError("dialogue localization source changed during compile")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "dialogue_digest": dialogue["dialogue_digest"],
        "authoring": plan, "row_count": len(plan["rows"]),
        "reviewed_count": sum(x["reviewed"] for x in plan["rows"]),
        "all_rows_reviewed": reviewed,
        "playable_handoff_allowed": bool(
            reviewed and dialogue["playable_handoff_allowed"]),
        "translation_provenance_verified": False,
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT - 128:
        raise StudioQuestError("dialogue localization receipt exceeds byte budget")
    result["dialogue_localization_digest"] = _digest(result)
    return result


def replay_dialogue_localization(
    documents: Mapping[str, Any], npc_receipt: object, dialogue_receipt: object,
    receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dialogue localization replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid dialogue localization receipt")
    checked = compile_dialogue_localization(
        documents, npc_receipt, dialogue_receipt, receipt.get("authoring"),
        authorized=True, expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("dialogue localization receipt differs from replay")
    return checked


def compile_dialogue_localized_handoff(
    documents: Mapping[str, Any], npc_receipt: object, dialogue_receipt: object,
    receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_dialogue_localization(
        documents, npc_receipt, dialogue_receipt, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("dialogue localization requires complete review")
    dialogue = compile_quest_dialogue_handoff(
        documents, npc_receipt, dialogue_receipt, authorized=True)
    if dialogue["session_digest"] != checked["session_digest"]:
        raise StudioQuestError("localized dialogue handoff session diverged")
    result = {
        "schema": HANDOFF_SCHEMA, "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": checked["session_digest"],
        "dialogue_digest": checked["dialogue_digest"],
        "dialogue_localization_digest": checked["dialogue_localization_digest"],
        "locale": checked["authoring"]["locale"],
        "target_ending": dialogue["target_ending"],
        "canonical_choices": dialogue["canonical_choices"],
        "localized_dialogue_lines": [
            {"stage_id": x["stage_id"], "choice": x["choice"],
             "beat_index": x["beat_index"], "speaker": x["speaker"],
             "original": x["source_text"], "display": x["translation"]}
            for x in checked["authoring"]["rows"]
        ],
        "translation_provenance_verified": False,
        "native_gameplay_verified": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_dialogue_localization(
    documents: Mapping[str, Any], npc_receipt: object, dialogue_receipt: object,
    receipt: object, directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_dialogue_localization(
        documents, npc_receipt, dialogue_receipt, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("dialogue localization publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".dialogue-localization-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
    try:
        before = os.fstat(fd)
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        linked = True
        os.fsync(fd)
        verify_fd = _open_directory(directory)
        try:
            after = os.fstat(verify_fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise StudioQuestError("dialogue localization output directory changed")
        finally:
            os.close(verify_fd)
    except BaseException:
        if linked:
            os.unlink(FILENAME, dir_fd=fd)
            os.fsync(fd)
        raise
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "dialogue_localization_digest": checked["dialogue_localization_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_dialogue_localization(
    documents: Mapping[str, Any], npc_receipt: object, dialogue_receipt: object,
    directory: Path, *, authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dialogue localization restore requires authorization")
    _lease(expected_source_digest, "dialogue localization restore source")
    stored = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT)
    if stored.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale dialogue localization restore source")
    return replay_dialogue_localization(
        documents, npc_receipt, dialogue_receipt, stored, authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  byId('export').addEventListener('click', () => {
    try {
      const plan = JSON.parse(byId('plan').textContent);
      plan.rows = plan.rows.map((row, i) => ({
        ...row,
        translation: byId('translation-' + i).value,
        reviewed: byId('review-' + i).checked
      }));
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 262144) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-dialogue-translation-edited-plan.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      byId('status').textContent = 'Exported; canonical CLI review required.';
    } catch (_) { byId('status').textContent = 'Invalid edit; no export.'; }
  });
})();"""


def render_dialogue_localization_editor_html(
    documents: Mapping[str, Any], npc_receipt: object, dialogue_receipt: object,
    receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_dialogue_localization(
        documents, npc_receipt, dialogue_receipt, receipt, authorized=authorized)
    plan = checked["authoring"]
    rows = "".join(
        '<fieldset><legend>' + escape(x["speaker"] + " / " +
                                      x["stage_id"] + " / " + x["choice"]) +
        '</legend><p>' + escape(x["source_text"]) + '</p>'
        '<label for="translation-' + str(i) + '">Reviewed translation</label>'
        '<textarea id="translation-' + str(i) + '" maxlength="2048">' +
        escape(x["translation"]) + '</textarea>'
        '<label for="review-' + str(i) + '">Reviewed</label>'
        '<input type="checkbox" id="review-' + str(i) + '"' +
        (" checked" if x["reviewed"] else "") + '></fieldset>'
        for i, x in enumerate(plan["rows"]))
    plan_json = _canonical(plan).decode("ascii").replace("<", "\\u003c")
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Original NPC dialogue translation editor</title></head><body><main>'
        '<h1>Review original dialogue translations</h1>'
        '<p>Display-only text; canonical speakers, choices and trust are immutable.</p>' +
        rows + '<script id="plan" type="application/json">' + plan_json +
        '</script><button id="export" type="button">Export edited translations</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("dialogue localization HTML exceeds byte budget")
    return html
