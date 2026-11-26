"""Canonical quest journal authoring with source-bound, editable player notes.

Player prose is never evidence of a completed action. Only the canonical quest
replay determines which stages may be annotated. Offline HTML exports a typed
edit plan; the CLI recomputes the source and stores a private, exclusive receipt.
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
    StudioQuestError, compile_quest_program, quest_progress,
    replay_quest, start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json

SCHEMA = "skeleton.game_builder.studio_quest_player_journal.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_player_journal_plan.v1"
PROMPT = "create source-grounded journal notes for my completed quest stages"
FILENAME = "studio_quest_player_journal.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_PLAN_BYTES = 32768
MAX_RECEIPT_BYTES = 65536
MAX_HTML_BYTES = 131072
MAX_ENTRIES = 64
MAX_NOTE_CHARS = 1024


def _text(value: object, label: str, maximum: int) -> str:
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or value.strip() != value
            or any(ord(c) < 32 and c not in "\n\t" for c in value)
            or "\x7f" in value):
        raise StudioQuestError("invalid authored " + label)
    return value


def _plan(value: object) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {
            "schema", "actions", "entries", "target_ending"}
            or value.get("schema") != PLAN_SCHEMA):
        raise StudioQuestError("invalid typed quest journal plan")
    actions = value["actions"]
    entries = value["entries"]
    if (type(actions) is not list or len(actions) > 64
            or type(entries) is not list or len(entries) > MAX_ENTRIES):
        raise StudioQuestError("invalid quest journal plan bounds")
    for action in actions:
        if (type(action) is not list or len(action) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256
                       or x.strip() != x or any(ord(c) < 32 for c in x)
                       for x in action)):
            raise StudioQuestError("invalid journal replay action")
    seen: set[str] = set()
    for row in entries:
        if type(row) is not dict or set(row) != {"stage_id", "note"}:
            raise StudioQuestError("invalid quest journal entry fields")
        stage_id = _text(row["stage_id"], "journal stage", 256)
        _text(row["note"], "journal note", MAX_NOTE_CHARS)
        if stage_id in seen:
            raise StudioQuestError("duplicate journal entry stage")
        seen.add(stage_id)
    _text(value["target_ending"], "journal ending", 256)
    if len(_canonical(value)) > MAX_PLAN_BYTES:
        raise StudioQuestError("quest journal plan exceeds byte budget")
    return {
        "schema": PLAN_SCHEMA,
        "actions": [list(x) for x in actions],
        "entries": [{"stage_id": x["stage_id"], "note": x["note"]}
                    for x in entries],
        "target_ending": value["target_ending"],
    }


def suggest_quest_journal(
    documents: Mapping[str, Any], prompt: str, actions: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str, target_ending: str,
) -> dict[str, Any]:
    """Deterministically draft notes from authored stage rewards, not model guesses."""
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported quest journal prompt")
    if authorized is not True:
        raise PermissionError("journal suggestion requires operator authorization")
    _lease(expected_source_digest, "journal suggestion source")
    _lease(expected_initial_session_digest, "journal suggestion session")
    if type(actions) is not list:
        raise StudioQuestError("invalid quest journal action list")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale journal suggestion source")
    if start_quest(documents, authorized=True).digest != expected_initial_session_digest:
        raise StudioQuestError("stale journal suggestion initial session")
    session = replay_quest(documents, actions, authorized=True)
    stage_map = {stage.key: stage for stage in program.stages}
    entries = [
        {"stage_id": stage_id,
         "note": "Completed " + stage_id + " by choosing " + alternative +
                 "; authored reward: " + stage_map[stage_id].reward + "."}
        for stage_id, alternative in session.choices
    ]
    for row in entries:
        if len(row["note"]) > MAX_NOTE_CHARS:
            raise StudioQuestError("authored reward cannot fit journal note")
    plan = {"schema": PLAN_SCHEMA, "actions": [list(x) for x in actions],
            "entries": entries, "target_ending": target_ending}
    # All generated text remains operator-editable and must pass the same
    # canonical source replay as manually written notes.
    return compile_quest_journal(
        documents, plan, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)


def compile_quest_journal(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest journal compile requires operator authorization")
    _lease(expected_source_digest, "quest journal source")
    _lease(expected_initial_session_digest, "quest journal session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("quest journal source exceeds byte budget")
    plan = _plan(authoring)
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale quest journal source lease")
    initial = start_quest(documents, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale quest journal initial session lease")
    if plan["target_ending"] not in {name for name, _ in program.endings}:
        raise StudioQuestError("unknown quest journal target ending")
    session = replay_quest(documents, plan["actions"], authorized=True)
    completed = set(session.completed)
    if any(row["stage_id"] not in completed for row in plan["entries"]):
        raise StudioQuestError("journal note references unearned quest stage")
    progress = quest_progress(session, documents)
    if _canonical(documents) != before:
        raise StudioQuestError("quest journal source changed during compile")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "authoring": plan,
        "completed_stage_ids": list(session.completed),
        "target_ending": plan["target_ending"],
        "target_ending_eligible": (
            plan["target_ending"] in progress["sandbox_endings_eligible"]),
        "unmet_target_predicates": progress[
            "unmet_ending_predicates"].get(plan["target_ending"], []),
        "entry_count": len(plan["entries"]),
        "canonical_quest_replay_verified": True,
        "playable_handoff_allowed": (
            plan["target_ending"] in progress["sandbox_endings_eligible"]),
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("quest journal receipt exceeds byte budget")
    result["journal_digest"] = _digest(result)
    return result


def replay_quest_journal(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest journal replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid quest journal receipt")
    checked = compile_quest_journal(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("quest journal differs from canonical replay")
    return checked


def compile_journal_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_journal(documents, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("quest journal target ending not replay-eligible")
    session = replay_quest(
        documents, checked["authoring"]["actions"], authorized=True)
    if session.digest != checked["session_digest"]:
        raise StudioQuestError("journal playable handoff replay diverged")
    result: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_journal_handoff.v1",
        "project_id": checked["project_id"],
        "quest_source_digest": checked["source_digest"],
        "quest_session_digest": session.digest,
        "journal_digest": checked["journal_digest"],
        "target_ending": checked["target_ending"],
        "entries": checked["authoring"]["entries"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_journal(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_journal(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("quest journal publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".quest-journal-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
    try:
        initial = os.fstat(fd)
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
        check_fd = _open_directory(directory)
        try:
            current = os.fstat(check_fd)
            if (initial.st_dev, initial.st_ino) != (current.st_dev, current.st_ino):
                raise StudioQuestError("quest journal output directory changed")
        finally:
            os.close(check_fd)
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
            "journal_digest": checked["journal_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_quest_journal(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest journal restore requires authorization")
    _lease(expected_source_digest, "quest journal restore source")
    receipt = read_studio_private_json(
        Path(directory) / FILENAME, MAX_RECEIPT_BYTES)
    if receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale quest journal restore source")
    return replay_quest_journal(documents, receipt, authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const get = id => document.getElementById(id);
  get('export').addEventListener('click', () => {
    try {
      const plan = JSON.parse(get('plan').textContent);
      const notes = Array.from(document.querySelectorAll('textarea[data-stage]'));
      if (notes.length !== plan.entries.length) throw Error('mismatch');
      plan.entries = notes.map((node, index) => {
        const note = node.value;
        if (!note || note.length > 1024 || note.trim() !== note ||
            /[\\u0000-\\u0008\\u000b-\\u001f\\u007f]/.test(note))
          throw Error('invalid note');
        return {stage_id: plan.entries[index].stage_id, note};
      });
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 32768) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type:'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-journal-edited-plan.json'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      get('status').textContent = 'Edited plan exported. CLI replay is required.';
    } catch (_) {
      get('status').textContent = 'Invalid edit; nothing exported.';
    }
  });
})();"""


def render_quest_journal_editor_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_journal(documents, receipt, authorized=authorized)
    fields = "".join(
        '<label for="entry-' + str(i) + '">Completed stage ' +
        escape(row["stage_id"], quote=True) + '</label>'
        '<textarea id="entry-' + str(i) + '" data-stage="' +
        escape(row["stage_id"], quote=True) + '" maxlength="1024">' +
        escape(row["note"]) + '</textarea>'
        for i, row in enumerate(checked["authoring"]["entries"]))
    # JSON data in a script element is never executable, but '<' still needs
    # escaping to prevent an authored string from closing the element.
    plan_json = _canonical(checked["authoring"]).decode("ascii").replace("<", "\\u003c")
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Quest player journal</title></head><body><main>'
        '<h1>Edit original quest journal notes</h1>'
        '<p>Only completed authored stages can receive notes. Notes are not evidence.</p>'
        + fields +
        '<script type="application/json" id="plan">' + plan_json + '</script>'
        '<button id="export" type="button">Export edited plan</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<p>CLI source replay is required before private publication.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("quest journal editor exceeds byte budget")
    return html
