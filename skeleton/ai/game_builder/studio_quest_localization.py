"""Operator-reviewed, source-leased quest localization with canonical replay.

Translations alter presentation only. They never change authored stage IDs,
choice effects, quest predicates, earned rewards, or the canonical session.
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
    StudioQuestError, compile_quest_program, quest_progress, replay_quest, start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json

SCHEMA = "skeleton.game_builder.studio_quest_localization.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_localization_plan.v1"
PROMPT = "prepare an operator-reviewed localization of my original quest"
FILENAME = "studio_quest_localization.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_PLAN_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 320 * 1024
MAX_HTML_BYTES = 512 * 1024
MAX_ROWS = 800
MAX_TEXT = 512


def _safe_text(value: object, label: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= MAX_TEXT
            or value.strip() != value
            or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f
                   or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid localization " + label)
    return value


def _source_rows(program: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for stage in program.stages:
        rows.append({"kind": "stage", "stage_id": stage.key, "source": stage.key})
        rows.append({"kind": "reward", "stage_id": stage.key, "source": stage.reward})
        for option in stage.alternatives:
            rows.append({"kind": "choice", "stage_id": stage.key, "source": option})
    for ending, _ in program.endings:
        rows.append({"kind": "ending", "stage_id": "", "source": ending})
    if len(rows) > MAX_ROWS:
        raise StudioQuestError("localization coverage exceeds row budget")
    return rows


def propose_quest_localization(
    documents: Mapping[str, Any], prompt: str, locale: str, actions: object,
    target_ending: str, *, authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Return editable source labels, never fabricated machine translations."""
    if prompt != PROMPT or type(prompt) is not str:
        raise StudioQuestError("unsupported localization prompt")
    if authorized is not True:
        raise PermissionError("localization proposal requires authorization")
    _lease(expected_source_digest, "localization source")
    _lease(expected_initial_session_digest, "localization session")
    if type(locale) is not str or re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", locale) is None:
        raise StudioQuestError("invalid BCP47 localization locale")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale localization source")
    if start_quest(documents, authorized=True).digest != expected_initial_session_digest:
        raise StudioQuestError("stale localization initial session")
    if target_ending not in dict(program.endings):
        raise StudioQuestError("unknown localization ending")
    if type(actions) is not list or len(actions) > 64:
        raise StudioQuestError("invalid localization actions")
    session = replay_quest(documents, actions, authorized=True)
    plan = {
        "schema": PLAN_SCHEMA, "locale": locale,
        "actions": [list(pair) for pair in session.choices],
        "target_ending": target_ending,
        "rows": [{**row, "translation": row["source"], "reviewed": False}
                 for row in _source_rows(program)],
    }
    if len(_canonical(plan)) > MAX_PLAN_BYTES:
        raise StudioQuestError("localization plan exceeds byte budget")
    return plan


def _validate_plan(plan: object, program: Any) -> dict[str, Any]:
    if (type(plan) is not dict or set(plan) != {
            "schema", "locale", "actions", "target_ending", "rows"}
            or plan.get("schema") != PLAN_SCHEMA):
        raise StudioQuestError("invalid localization plan schema")
    locale = plan["locale"]
    if type(locale) is not str or re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", locale) is None:
        raise StudioQuestError("invalid localization locale")
    actions = plan["actions"]
    if type(actions) is not list or len(actions) > 64:
        raise StudioQuestError("invalid localization action list")
    for pair in actions:
        if (type(pair) is not list or len(pair) != 2
                or any(type(value) is not str or not 1 <= len(value) <= 256
                       for value in pair)):
            raise StudioQuestError("invalid localization action")
    if type(plan["target_ending"]) is not str or plan["target_ending"] not in dict(program.endings):
        raise StudioQuestError("invalid localization target ending")
    expected = _source_rows(program)
    rows = plan["rows"]
    if type(rows) is not list or len(rows) != len(expected):
        raise StudioQuestError("incomplete localization source coverage")
    clean: list[dict[str, Any]] = []
    for source, row in zip(expected, rows):
        if (type(row) is not dict or set(row) != {
                "kind", "stage_id", "source", "translation", "reviewed"}
                or any(row.get(key) != value for key, value in source.items())
                or type(row.get("reviewed")) is not bool):
            raise StudioQuestError("localization source key changed or rows reordered")
        clean.append({**source, "translation": _safe_text(row["translation"], "text"),
                      "reviewed": row["reviewed"]})
    normalized = {"schema": PLAN_SCHEMA, "locale": locale,
                  "actions": [list(pair) for pair in actions],
                  "target_ending": plan["target_ending"], "rows": clean}
    if len(_canonical(normalized)) > MAX_PLAN_BYTES:
        raise StudioQuestError("localization plan exceeds byte budget")
    return normalized


def compile_quest_localization(
    documents: Mapping[str, Any], plan: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("localization compile requires authorization")
    _lease(expected_source_digest, "localization source")
    _lease(expected_initial_session_digest, "localization initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("localization source exceeds byte budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale localization source lease")
    initial = start_quest(documents, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale localization initial session lease")
    checked = _validate_plan(plan, program)
    session = replay_quest(documents, checked["actions"], authorized=True)
    progress = quest_progress(session, documents)
    if _canonical(documents) != before:
        raise StudioQuestError("localization source mutated during compile")
    reviewed = sum(row["reviewed"] for row in checked["rows"])
    eligible = checked["target_ending"] in progress["sandbox_endings_eligible"]
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "authoring": checked, "row_count": len(checked["rows"]),
        "reviewed_count": reviewed,
        "target_ending_eligible": eligible,
        "unmet_target_predicates": progress["unmet_ending_predicates"].get(
            checked["target_ending"], []),
        "playable_handoff_allowed": eligible and reviewed == len(checked["rows"]),
        "canonical_quest_replay_verified": True,
        "translation_provenance_verified": False,
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("localization receipt exceeds byte budget")
    result["localization_digest"] = _digest(result)
    return result


def replay_quest_localization(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("localization replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid localization receipt")
    checked = compile_quest_localization(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("localization receipt differs from canonical replay")
    return checked


def compile_localized_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_localization(documents, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("localization requires complete review and eligible ending")
    session = replay_quest(
        documents, checked["authoring"]["actions"], authorized=True)
    if session.digest != checked["session_digest"]:
        raise StudioQuestError("localized handoff diverged from canonical replay")
    translations = checked["authoring"]["rows"]
    result: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_localized_handoff.v1",
        "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": session.digest,
        "localization_digest": checked["localization_digest"],
        "locale": checked["authoring"]["locale"],
        "display_rows": [{"kind": row["kind"], "stage_id": row["stage_id"],
                          "source": row["source"], "display": row["translation"]}
                         for row in translations],
        "canonical_choices": [list(pair) for pair in session.choices],
        "target_ending": checked["authoring"]["target_ending"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_localization(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_localization(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("localization publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".quest-localization-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
    try:
        before = os.fstat(fd)
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
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
                raise StudioQuestError("localization output directory changed")
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
    return {"path": str(Path(directory) / FILENAME), "bytes": len(raw),
            "localization_digest": checked["localization_digest"],
            "file_write_performed": True, "release_certified": False}


def restore_quest_localization(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("localization restore requires authorization")
    _lease(expected_source_digest, "localization restore source")
    receipt = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT_BYTES)
    if receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale localization restore source")
    return replay_quest_localization(documents, receipt, authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const get = id => document.getElementById(id);
  get('export').addEventListener('click', () => {
    try {
      const plan = JSON.parse(get('plan').textContent);
      const inputs = Array.from(document.querySelectorAll('input[data-row]'));
      if (inputs.length !== plan.rows.length) throw Error('row mismatch');
      plan.rows = plan.rows.map((row, index) => {
        const input = inputs[index];
        const translation = input.value;
        if (!translation || translation.length > 512 || translation.trim() !== translation ||
            /[\\u0000-\\u001f\\u007f-\\u009f\\u202a-\\u202e\\u2066-\\u2069]/.test(translation))
          throw Error('invalid translation');
        return {...row, translation,
          reviewed: document.getElementById('review-' + index).checked};
      });
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 262144) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type:'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-localization-edited-plan.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      get('status').textContent = 'Plan exported; CLI canonical replay is required.';
    } catch (_) { get('status').textContent = 'Invalid edit; no export.'; }
  });
})();"""


def render_localization_editor_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_localization(documents, receipt, authorized=authorized)
    fields = "".join(
        '<label for="row-' + str(index) + '">' +
        escape(row["kind"] + " " + row["stage_id"] + ": " + row["source"]) +
        '</label><input id="row-' + str(index) + '" data-row="' +
        str(index) + '" maxlength="512" value="' +
        escape(row["translation"], quote=True) + '">'
        '<label for="review-' + str(index) + '">Reviewed</label>'
        '<input type="checkbox" id="review-' + str(index) + '"' +
        (" checked" if row["reviewed"] else "") + '>'
        for index, row in enumerate(checked["authoring"]["rows"]))
    plan_json = _canonical(checked["authoring"]).decode("ascii").replace("<", "\\u003c")
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Original quest localization editor</title></head><body><main>'
        '<h1>Review quest translations</h1>'
        '<p>Labels are presentation only; source IDs and earned outcomes never change.</p>' +
        fields + '<script type="application/json" id="plan">' + plan_json +
        '</script><button id="export" type="button">Export edited plan</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<p>Canonical CLI replay and explicit review are required before handoff.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("localization editor exceeds byte budget")
    return html
