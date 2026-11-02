"""Source-leased, operator-reviewed pacing plan for original quest playthroughs.

Durations are author estimates, not observed runtime evidence. Only the
canonical quest replay decides which beats are played and which endings exist.
"""
from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest, start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json

SCHEMA = "skeleton.game_builder.studio_quest_pacing.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_pacing_plan.v1"
PROMPT = "draft an editable original quest pacing storyboard with explicit estimates"
FILENAME = "studio_quest_pacing.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_PLAN_BYTES = 65536
MAX_RECEIPT_BYTES = 131072
MAX_HTML_BYTES = 256 * 1024
MAX_BEATS = 64
MAX_ACTIONS = 64


def _label(value: object, field: str, maximum: int, *, empty: bool = False) -> str:
    if (type(value) is not str or len(value) > maximum
            or (not empty and not value) or value.strip() != value
            or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f
                   or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid pacing " + field)
    return value


def propose_quest_pacing(
    documents: Mapping[str, Any], prompt: str, actions: object, *,
    target_ending: str, authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Provide a review-required estimate, never claim measured playtime."""
    if prompt != PROMPT or type(prompt) is not str:
        raise StudioQuestError("unsupported quest pacing prompt")
    if authorized is not True:
        raise PermissionError("pacing proposal requires operator authorization")
    _lease(expected_source_digest, "pacing source")
    _lease(expected_initial_session_digest, "pacing initial session")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale pacing source")
    if start_quest(documents, authorized=True).digest != expected_initial_session_digest:
        raise StudioQuestError("stale pacing initial session")
    if target_ending not in dict(program.endings):
        raise StudioQuestError("unknown pacing ending")
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise StudioQuestError("invalid pacing actions")
    session = replay_quest(documents, actions, authorized=True)
    result = {
        "schema": PLAN_SCHEMA,
        "actions": [list(row) for row in session.choices],
        "target_ending": target_ending,
        "budget_seconds": 3600,
        "beats": [
            {"stage_id": stage.key, "label": stage.key, "estimated_seconds": 90,
             "intensity": 3, "note": "", "reviewed": False}
            for stage in program.stages
        ],
    }
    if len(_canonical(result)) > MAX_PLAN_BYTES:
        raise StudioQuestError("pacing proposal exceeds byte budget")
    return result


def _plan(value: object, program: Any) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {
            "schema", "actions", "target_ending", "budget_seconds", "beats"}
            or value["schema"] != PLAN_SCHEMA):
        raise StudioQuestError("invalid typed pacing plan")
    if len(_canonical(value)) > MAX_PLAN_BYTES:
        raise StudioQuestError("pacing plan exceeds byte budget")
    actions = value["actions"]
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise StudioQuestError("invalid pacing action count")
    for row in actions:
        if (type(row) is not list or len(row) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256 for x in row)):
            raise StudioQuestError("invalid pacing action")
    target = value["target_ending"]
    if type(target) is not str or target not in dict(program.endings):
        raise StudioQuestError("unknown pacing target ending")
    budget = value["budget_seconds"]
    if type(budget) is not int or not 60 <= budget <= 14400:
        raise StudioQuestError("invalid pacing budget")
    rows = value["beats"]
    if type(rows) is not list or len(rows) != len(program.stages) or len(rows) > MAX_BEATS:
        raise StudioQuestError("pacing beat coverage must equal authored stage graph")
    clean: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if (type(row) is not dict or set(row) != {
                "stage_id", "label", "estimated_seconds", "intensity", "note", "reviewed"}):
            raise StudioQuestError("invalid pacing beat fields")
        stage_id = _label(row["stage_id"], "stage", 256)
        if stage_id != program.stages[index].key:
            raise StudioQuestError("pacing beats must preserve canonical stage order")
        seconds = row["estimated_seconds"]
        intensity = row["intensity"]
        if (type(seconds) is not int or not 1 <= seconds <= 3600
                or type(intensity) is not int or not 1 <= intensity <= 5
                or type(row["reviewed"]) is not bool):
            raise StudioQuestError("invalid pacing estimates or review flag")
        clean.append({
            "stage_id": stage_id,
            "label": _label(row["label"], "label", 256),
            "estimated_seconds": seconds,
            "intensity": intensity,
            "note": _label(row["note"], "note", 512, empty=True),
            "reviewed": row["reviewed"],
        })
    return {"schema": PLAN_SCHEMA, "actions": [list(x) for x in actions],
            "target_ending": target, "budget_seconds": budget, "beats": clean}


def compile_quest_pacing(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("pacing compilation requires operator authorization")
    _lease(expected_source_digest, "pacing source")
    _lease(expected_initial_session_digest, "pacing initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("pacing source exceeds byte budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale pacing source lease")
    initial = start_quest(documents, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale pacing initial session lease")
    plan = _plan(authoring, program)
    session = replay_quest(documents, plan["actions"], authorized=True)
    progress = quest_progress(session, documents)
    beats = {row["stage_id"]: row for row in plan["beats"]}
    timeline: list[dict[str, Any]] = []
    elapsed = 0
    for stage_id, choice in session.choices:
        row = beats[stage_id]
        finish = elapsed + row["estimated_seconds"]
        timeline.append({
            "stage_id": stage_id, "choice": choice,
            "label": row["label"], "start_seconds": elapsed,
            "end_seconds": finish, "intensity": row["intensity"],
            "note": row["note"], "reviewed": row["reviewed"],
        })
        elapsed = finish
    target_ready = plan["target_ending"] in progress["sandbox_endings_eligible"]
    reviewed = bool(timeline) and all(row["reviewed"] for row in timeline)
    within_budget = elapsed <= plan["budget_seconds"]
    if _canonical(documents) != before:
        raise StudioQuestError("pacing source changed during compilation")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "authoring": plan,
        "timeline": timeline,
        "estimated_play_seconds": elapsed,
        "budget_seconds": plan["budget_seconds"],
        "within_estimated_budget": within_budget,
        "played_beats_reviewed": reviewed,
        "target_ending": plan["target_ending"],
        "target_ending_eligible": target_ready,
        "unmet_target_predicates": progress["unmet_ending_predicates"].get(
            plan["target_ending"], []),
        "playable_handoff_allowed": reviewed and within_budget and target_ready,
        "duration_is_author_estimate": True,
        "measured_runtime_verified": False,
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("pacing receipt exceeds byte budget")
    result["pacing_digest"] = _digest(result)
    return result


def replay_quest_pacing(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("pacing replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid pacing receipt")
    checked = compile_quest_pacing(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("pacing receipt differs from canonical replay")
    return checked


def compile_pacing_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_pacing(documents, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("pacing handoff requires reviewed eligible within-budget route")
    session = replay_quest(
        documents, checked["authoring"]["actions"], authorized=True)
    if session.digest != checked["session_digest"]:
        raise StudioQuestError("pacing handoff session diverged")
    result: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_pacing_handoff.v1",
        "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": checked["session_digest"],
        "pacing_digest": checked["pacing_digest"],
        "target_ending": checked["target_ending"],
        "timeline": checked["timeline"],
        "estimated_play_seconds": checked["estimated_play_seconds"],
        "duration_is_author_estimate": True,
        "measured_runtime_verified": False,
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_pacing(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_pacing(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("pacing publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".quest-pacing-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
    try:
        before = os.fstat(fd)
        out = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        linked = True
        os.fsync(fd)
        verify_fd = _open_directory(directory)
        try:
            after = os.fstat(verify_fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise StudioQuestError("pacing output directory changed")
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
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "pacing_digest": checked["pacing_digest"], "bytes": len(raw),
            "file_write_performed": True, "release_certified": False}


def restore_quest_pacing(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("pacing restore requires authorization")
    _lease(expected_source_digest, "pacing restore source")
    receipt = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT_BYTES)
    if receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale pacing restore source")
    return replay_quest_pacing(documents, receipt, authorized=True)


_EDITOR = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const plan = JSON.parse(byId('plan').textContent);
  byId('save').addEventListener('click', () => {
    try {
      const rows = Array.from(document.querySelectorAll('[data-beat]'));
      if (rows.length !== plan.beats.length) throw Error('beat count changed');
      plan.budget_seconds = Number(byId('budget').value);
      plan.beats = plan.beats.map((beat, i) => {
        const row = rows[i];
        return {stage_id: beat.stage_id,
          label: row.querySelector('[data-label]').value,
          estimated_seconds: Number(row.querySelector('[data-seconds]').value),
          intensity: Number(row.querySelector('[data-intensity]').value),
          note: row.querySelector('[data-note]').value,
          reviewed: row.querySelector('[data-reviewed]').checked};
      });
      const blob = new Blob([JSON.stringify(plan)], {type:'application/json'});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-pacing-plan.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { byId('status').textContent = String(error); }
  });
})();"""


def render_pacing_editor_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_pacing(documents, receipt, authorized=authorized)
    plan = checked["authoring"]
    nonce = secrets.token_urlsafe(24)
    raw_plan = json.dumps(plan, sort_keys=True, ensure_ascii=True,
                          separators=(",", ":"), allow_nan=False)
    raw_plan = (raw_plan.replace("&", "\\u0026").replace("<", "\\u003c")
                .replace(">", "\\u003e"))
    rows = []
    for row in plan["beats"]:
        def field(name: str, value: object, kind: str) -> str:
            return ('<label>' + escape(name) + ' <input data-' + kind +
                    ' value="' + escape(str(value), quote=True) + '"></label>')
        rows.append(
            '<li data-beat><strong>' + escape(row["stage_id"]) + '</strong>' +
            field("Label", row["label"], "label") +
            field("Seconds", row["estimated_seconds"], "seconds") +
            field("Intensity", row["intensity"], "intensity") +
            field("Note", row["note"], "note") +
            '<label>Reviewed <input data-reviewed type="checkbox"' +
            (' checked' if row["reviewed"] else '') + '></label></li>')
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'nonce-" + nonce +
        "'; connect-src 'none'; base-uri 'none'; form-action 'none'; "
        'object-src \'none\'">'
        '<title>Original quest pacing editor</title></head><body><main>'
        '<h1>Original quest pacing editor</h1>'
        '<p>Durations are estimates; no runtime measurements or release proof.</p>'
        '<label>Budget seconds <input id="budget" value="' +
        str(plan["budget_seconds"]) + '"></label><ol>' + ''.join(rows) +
        '</ol><button id="save" type="button">Export reviewed plan</button>'
        '<p id="status" role="status"></p>'
        '<script id="plan" type="application/json">' + raw_plan + '</script>'
        '<script nonce="' + nonce + '">' + _EDITOR + '</script>'
        '</main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("pacing editor exceeds HTML budget")
    return html
