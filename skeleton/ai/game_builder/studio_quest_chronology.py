"""Authored quest chronology with canonical causal replay and hard time windows.

Chronology is an explicit player-facing authoring constraint, not an assertion
about wall-clock time, external observations, physics or native gameplay.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
    start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json

PLAN_SCHEMA = "skeleton.game_builder.quest_chronology_plan.v1"
SCHEMA = "skeleton.game_builder.quest_chronology.v1"
PROMPT = "schedule my original quest choices with causal time windows"
FILENAME = "studio_quest_chronology.json"
MAX_PLAN = 128 * 1024
MAX_RECEIPT = 256 * 1024
MAX_HTML = 256 * 1024
MAX_ACTIONS = 64
MAX_MINUTE = 10080


def _source(documents: Mapping[str, Any], actions: object) -> tuple[Any, Any]:
    if (type(actions) is not list or len(actions) > MAX_ACTIONS
            or any(type(row) is not list or len(row) != 2
                   or any(type(value) is not str for value in row)
                   for row in actions)):
        raise StudioQuestError("invalid typed chronology actions")
    program = compile_quest_program(documents)
    session = replay_quest(documents, actions, authorized=True)
    return program, session


def propose_quest_chronology(
    documents: Mapping[str, Any], prompt: str, actions: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("chronology proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported chronology authoring prompt")
    program, session = _source(documents, actions)
    initial = start_quest(documents, authorized=True)
    if (expected_source_digest != program.source_digest
            or expected_initial_session_digest != initial.digest):
        raise StudioQuestError("stale chronology source or initial session")
    plan = {
        "schema": PLAN_SCHEMA, "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "actions": [list(x) for x in session.choices],
        "rows": [{
            "stage_id": stage, "choice": choice,
            "start_minute": index * 30,
            "duration_minutes": 20,
            "not_before_minute": index * 30,
            "deadline_minute": (index + 1) * 30,
            "note": "", "reviewed": False,
        } for index, (stage, choice) in enumerate(session.choices)],
    }
    if len(_canonical(plan)) > MAX_PLAN:
        raise StudioQuestError("chronology plan exceeds byte budget")
    return plan


def _note(value: object) -> str:
    if (type(value) is not str or len(value) > 240
            or value.strip() != value
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in
                   "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid chronology note")
    return value


def _checked_plan(plan: object, program: Any, session: Any, initial: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if (type(plan) is not dict or set(plan) != {
            "schema", "source_digest", "initial_session_digest",
            "session_digest", "actions", "rows"}
            or plan["schema"] != PLAN_SCHEMA
            or len(_canonical(plan)) > MAX_PLAN
            or plan["source_digest"] != program.source_digest
            or plan["initial_session_digest"] != initial.digest
            or plan["session_digest"] != session.digest
            or plan["actions"] != [list(x) for x in session.choices]):
        raise StudioQuestError("stale or invalid typed chronology plan")
    rows = plan["rows"]
    if type(rows) is not list or len(rows) != len(session.choices):
        raise StudioQuestError("chronology must cover every played action")
    checked = []
    previous_end = 0
    for index, (row, (stage, choice)) in enumerate(zip(rows, session.choices)):
        if (type(row) is not dict or set(row) != {
                "stage_id", "choice", "start_minute", "duration_minutes",
                "not_before_minute", "deadline_minute", "note", "reviewed"}
                or row["stage_id"] != stage or row["choice"] != choice):
            raise StudioQuestError("chronology changed canonical action identity")
        start = row["start_minute"]
        duration = row["duration_minutes"]
        earliest = row["not_before_minute"]
        deadline = row["deadline_minute"]
        if (any(type(value) is not int for value in (
                start, duration, earliest, deadline))
                or not 0 <= earliest <= MAX_MINUTE
                or not 0 <= start <= MAX_MINUTE
                or not 1 <= duration <= 1440
                or not 1 <= deadline <= MAX_MINUTE
                or start < earliest or start < previous_end
                or start + duration > deadline
                or type(row["reviewed"]) is not bool):
            raise StudioQuestError("impossible chronology window or overlapping actions")
        checked.append({
            "stage_id": stage, "choice": choice,
            "start_minute": start, "duration_minutes": duration,
            "end_minute": start + duration,
            "not_before_minute": earliest,
            "deadline_minute": deadline,
            "slack_minutes": deadline - (start + duration),
            "note": _note(row["note"]), "reviewed": row["reviewed"],
        })
        previous_end = start + duration
    return {"schema": PLAN_SCHEMA, "source_digest": program.source_digest,
            "initial_session_digest": initial.digest,
            "session_digest": session.digest,
            "actions": [list(x) for x in session.choices],
            "rows": [{k: row[k] for k in (
                "stage_id", "choice", "start_minute", "duration_minutes",
                "not_before_minute", "deadline_minute", "note", "reviewed")}
                     for row in checked]}, checked


def compile_quest_chronology(
    documents: Mapping[str, Any], plan: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("chronology compile requires authorization")
    before = _canonical(documents)
    if len(before) > 256 * 1024:
        raise StudioQuestError("chronology source exceeds byte budget")
    if type(plan) is not dict:
        raise StudioQuestError("invalid chronology plan")
    program, session = _source(documents, plan.get("actions"))
    initial = start_quest(documents, authorized=True)
    if (program.source_digest != expected_source_digest
            or initial.digest != expected_initial_session_digest):
        raise StudioQuestError("stale chronology compilation lease")
    checked_plan, timeline = _checked_plan(plan, program, session, initial)
    if not timeline or not all(row["reviewed"] for row in timeline):
        raise StudioQuestError("chronology requires a reviewed played path")
    progress = quest_progress(session, documents)
    if _canonical(documents) != before:
        raise StudioQuestError("canonical quest changed during chronology compile")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "authoring": checked_plan,
        "timeline": timeline,
        "end_minute": timeline[-1]["end_minute"],
        "sandbox_endings_eligible": progress["sandbox_endings_eligible"],
        "unmet_ending_predicates": progress["unmet_ending_predicates"],
        "canonical_quest_replay_verified": True,
        "temporal_window_consistency_verified": True,
        "external_clock_verified": False,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT - 128:
        raise StudioQuestError("chronology receipt exceeds byte budget")
    result["chronology_digest"] = _digest(result)
    return result


def replay_quest_chronology(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("chronology replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid chronology replay receipt")
    checked = compile_quest_chronology(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("chronology receipt differs from canonical replay")
    return checked


def publish_quest_chronology(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_chronology(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("chronology publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".quest-chronology-" + secrets.token_hex(16) + ".tmp"
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
                raise StudioQuestError("chronology output directory changed")
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
            "chronology_digest": checked["chronology_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_quest_chronology(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("chronology restore requires authorization")
    stored = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT)
    return replay_quest_chronology(documents, stored, authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  byId('export').addEventListener('click', () => {
    try {
      const plan = JSON.parse(byId('plan').textContent);
      plan.rows = plan.rows.map((row, i) => ({
        ...row,
        start_minute: Number(byId('start-' + i).value),
        duration_minutes: Number(byId('duration-' + i).value),
        not_before_minute: Number(byId('earliest-' + i).value),
        deadline_minute: Number(byId('deadline-' + i).value),
        note: byId('note-' + i).value,
        reviewed: byId('review-' + i).checked
      }));
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 131072) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'original-quest-chronology.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      byId('status').textContent = 'Exported; canonical compile must verify windows.';
    } catch (_) { byId('status').textContent = 'Invalid edit; no export.'; }
  });
})();"""


def render_quest_chronology_editor(
    documents: Mapping[str, Any], plan: object, *, authorized: bool,
) -> bytes:
    if authorized is not True:
        raise PermissionError("chronology editor requires authorization")
    if type(plan) is not dict:
        raise StudioQuestError("invalid chronology editor plan")
    program, session = _source(documents, plan.get("actions"))
    initial = start_quest(documents, authorized=True)
    checked, _ = _checked_plan(plan, program, session, initial)
    rows = []
    for i, row in enumerate(checked["rows"]):
        fields = "".join(
            '<label>' + escape(label) + '<input type="number" step="1" min="0" '
            'max="10080" id="' + key + '-' + str(i) + '" value="' +
            str(row[name]) + '"></label>'
            for key, name, label in (
                ("start", "start_minute", "Start minute"),
                ("duration", "duration_minutes", "Duration minutes"),
                ("earliest", "not_before_minute", "Not before minute"),
                ("deadline", "deadline_minute", "Deadline minute")))
        rows.append(
            '<fieldset><legend>' + escape(row["stage_id"] + " / " + row["choice"]) +
            '</legend>' + fields +
            '<label>Continuity note<textarea id="note-' + str(i) +
            '" maxlength="240">' + escape(row["note"]) + '</textarea></label>'
            '<label>Reviewed<input type="checkbox" id="review-' + str(i) + '"' +
            (" checked" if row["reviewed"] else "") + '></label></fieldset>')
    plan_json = _canonical(checked).decode("ascii").replace("<", "\\u003c")
    hash_value = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + hash_value +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="' + csp +
            '"><title>Original quest chronology</title></head><body><main>'
            '<h1>Review causal quest time windows</h1>' + ''.join(rows) +
            '<script type="application/json" id="plan">' + plan_json +
            '</script><button type="button" id="export">Export edited chronology'
            '</button><p id="status" role="status" aria-live="polite"></p></main>'
            '<script>' + _SCRIPT + '</script></body></html>').encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("chronology editor exceeds byte budget")
    return html


def render_quest_chronology_preview(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_chronology(documents, receipt, authorized=authorized)
    rows = "".join(
        '<li>' + escape(row["stage_id"] + " / " + row["choice"]) +
        ': ' + str(row["start_minute"]) + '–' + str(row["end_minute"]) +
        ' minutes (deadline ' + str(row["deadline_minute"]) + ')</li>'
        for row in checked["timeline"])
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src '
            "\'none\'; connect-src \'none\'; base-uri \'none\'; object-src \'none\'\">"
            '<title>Quest chronology preview</title></head><body><main>'
            '<h1>Canonical quest chronology</h1><ol>' + rows +
            '</ol><p>Author-reviewed windows, not observed wall-clock time.</p>'
            '</main></body></html>').encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("chronology preview exceeds byte budget")
    return html
