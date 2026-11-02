"""Canonical quest achievement authoring, replay, and sandbox-only unlocks.

Achievements are authored display milestones. Their eligibility is derived from
the canonical source/session, never a client claim or external account award.
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

SCHEMA = "skeleton.game_builder.studio_quest_achievements.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_achievement_plan.v1"
PROMPT = "draft original quest achievements from my authored stages and choices"
FILENAME = "studio_quest_achievements.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_PLAN_BYTES = 65536
MAX_RECEIPT_BYTES = 131072
MAX_HTML_BYTES = 262144
MAX_ACHIEVEMENTS = 64


def _text(value: object, label: str, maximum: int) -> str:
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or value.strip() != value
            or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f
                   or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid achievement " + label)
    return value


def propose_quest_achievements(
    documents: Mapping[str, Any], prompt: str, actions: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str, target_ending: str,
) -> dict[str, Any]:
    """Draft editable milestones from original authored stage rewards."""
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported quest achievement prompt")
    if authorized is not True:
        raise PermissionError("quest achievement proposal requires authorization")
    _lease(expected_source_digest, "achievement source")
    _lease(expected_initial_session_digest, "achievement initial session")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale achievement source")
    if start_quest(documents, authorized=True).digest != expected_initial_session_digest:
        raise StudioQuestError("stale achievement initial session")
    if target_ending not in dict(program.endings):
        raise StudioQuestError("unknown achievement target ending")
    if type(actions) is not list or len(actions) > 64:
        raise StudioQuestError("invalid achievement action list")
    session = replay_quest(documents, actions, authorized=True)
    rows = [
        {"id": "stage_" + str(index + 1), "title": stage.key,
         "description": "Complete " + stage.key + " to earn " + stage.reward,
         "stage_id": stage.key, "required_choice": "",
         "required_effect": "", "points": 10}
        for index, stage in enumerate(program.stages[:MAX_ACHIEVEMENTS])
    ]
    plan = {"schema": PLAN_SCHEMA, "actions": [list(x) for x in session.choices],
            "target_ending": target_ending, "achievements": rows}
    if len(_canonical(plan)) > MAX_PLAN_BYTES:
        raise StudioQuestError("achievement proposal exceeds byte budget")
    return plan


def _plan(value: object, program: Any) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {
            "schema", "actions", "target_ending", "achievements"}
            or value.get("schema") != PLAN_SCHEMA):
        raise StudioQuestError("invalid typed achievement plan")
    actions = value["actions"]
    if type(actions) is not list or len(actions) > 64:
        raise StudioQuestError("invalid achievement replay actions")
    for pair in actions:
        if (type(pair) is not list or len(pair) != 2
                or any(type(item) is not str or not 1 <= len(item) <= 256
                       for item in pair)):
            raise StudioQuestError("invalid achievement replay action")
    target = value["target_ending"]
    if type(target) is not str or target not in dict(program.endings):
        raise StudioQuestError("invalid achievement target ending")
    rows = value["achievements"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ACHIEVEMENTS:
        raise StudioQuestError("invalid achievement row count")
    stage_map = {stage.key: stage for stage in program.stages}
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for row in rows:
        if (type(row) is not dict or set(row) != {
                "id", "title", "description", "stage_id", "required_choice",
                "required_effect", "points"}):
            raise StudioQuestError("invalid achievement row fields")
        ident = _text(row["id"], "ID", 128)
        if re.fullmatch(r"[a-z][a-z0-9_]{0,127}", ident) is None or ident in seen:
            raise StudioQuestError("invalid or repeated achievement ID")
        seen.add(ident)
        stage_id = _text(row["stage_id"], "stage", 256)
        if stage_id not in stage_map:
            raise StudioQuestError("achievement refers to unknown authored stage")
        stage = stage_map[stage_id]
        choice = row["required_choice"]
        effect = row["required_effect"]
        if (type(choice) is not str or (choice and choice not in stage.alternatives)
                or type(effect) is not str or (effect and not choice)
                or (effect and effect not in dict(stage.choice_effects).get(choice, ()))):
            raise StudioQuestError("achievement contains forged choice or effect")
        points = row["points"]
        if type(points) is not int or not 1 <= points <= 100:
            raise StudioQuestError("invalid bounded achievement points")
        clean.append({
            "id": ident, "title": _text(row["title"], "title", 256),
            "description": _text(row["description"], "description", 1024),
            "stage_id": stage_id, "required_choice": choice,
            "required_effect": effect, "points": points,
        })
    plan = {"schema": PLAN_SCHEMA, "actions": [list(x) for x in actions],
            "target_ending": target, "achievements": clean}
    if len(_canonical(plan)) > MAX_PLAN_BYTES:
        raise StudioQuestError("achievement plan exceeds byte budget")
    return plan


def compile_quest_achievements(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("achievement compile requires authorization")
    _lease(expected_source_digest, "achievement source")
    _lease(expected_initial_session_digest, "achievement initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("achievement source exceeds byte budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale achievement source lease")
    initial = start_quest(documents, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale achievement initial session lease")
    plan = _plan(authoring, program)
    session = replay_quest(documents, plan["actions"], authorized=True)
    choices = dict(session.choices)
    stage_map = {stage.key: stage for stage in program.stages}
    unlocked: list[dict[str, Any]] = []
    locked: list[str] = []
    for row in plan["achievements"]:
        stage_id = row["stage_id"]
        choice = row["required_choice"]
        effect = row["required_effect"]
        earned = stage_id in session.completed
        if choice:
            earned = earned and choices.get(stage_id) == choice
        if effect:
            earned = earned and effect in dict(
                stage_map[stage_id].choice_effects).get(choice, ())
        if earned:
            unlocked.append({"id": row["id"], "points": row["points"],
                             "stage_id": stage_id})
        else:
            locked.append(row["id"])
    progress = quest_progress(session, documents)
    if _canonical(documents) != before:
        raise StudioQuestError("achievement source changed during compile")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "authoring": plan,
        "unlocked": unlocked, "locked_ids": locked,
        "sandbox_points": sum(row["points"] for row in unlocked),
        "target_ending_eligible": (
            plan["target_ending"] in progress["sandbox_endings_eligible"]),
        "unmet_target_predicates": progress[
            "unmet_ending_predicates"].get(plan["target_ending"], []),
        "canonical_quest_replay_verified": True,
        "external_account_awards_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("achievement receipt exceeds byte budget")
    result["achievement_digest"] = _digest(result)
    return result


def replay_quest_achievements(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("achievement replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid achievement receipt")
    checked = compile_quest_achievements(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("achievement receipt differs from canonical replay")
    return checked


def compile_achievement_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_achievements(documents, receipt, authorized=authorized)
    session = replay_quest(
        documents, checked["authoring"]["actions"], authorized=True)
    if session.digest != checked["session_digest"]:
        raise StudioQuestError("achievement playable handoff diverged")
    result: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_achievement_handoff.v1",
        "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": session.digest,
        "achievement_digest": checked["achievement_digest"],
        "definitions": checked["authoring"]["achievements"],
        "unlocked": checked["unlocked"],
        "sandbox_points": checked["sandbox_points"],
        "canonical_quest_replay_verified": True,
        "external_account_awards_verified": False,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_achievements(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_achievements(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("achievement publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".quest-achievements-" + secrets.token_hex(16) + ".tmp"
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
                raise StudioQuestError("achievement output directory changed")
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
            "achievement_digest": checked["achievement_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_quest_achievements(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("achievement restore requires authorization")
    _lease(expected_source_digest, "achievement restore source")
    receipt = read_studio_private_json(
        Path(directory) / FILENAME, MAX_RECEIPT_BYTES)
    if receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale achievement restore source")
    return replay_quest_achievements(documents, receipt, authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const get = id => document.getElementById(id);
  get('export').addEventListener('click', () => {
    try {
      const plan = JSON.parse(get('plan').textContent);
      const fields = Array.from(document.querySelectorAll('input[data-achievement]'));
      if (fields.length !== plan.achievements.length) throw Error('row mismatch');
      plan.achievements = plan.achievements.map((row, index) => {
        const title = fields[index].value;
        if (!title || title.length > 256 || title.trim() !== title ||
            /[\\u0000-\\u001f\\u007f-\\u009f\\u202a-\\u202e\\u2066-\\u2069]/.test(title))
          throw Error('invalid title');
        return {...row, title};
      });
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 65536) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type:'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-achievements-edited-plan.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      get('status').textContent = 'Edited plan exported; canonical CLI replay required.';
    } catch (_) { get('status').textContent = 'Invalid edit; nothing exported.'; }
  });
})();"""


def render_achievement_editor_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_achievements(documents, receipt, authorized=authorized)
    fields = "".join(
        '<label for="row-' + str(index) + '">' +
        escape(row["stage_id"] + ": " + row["description"]) +
        '</label><input id="row-' + str(index) + '" data-achievement="' +
        escape(row["id"], quote=True) + '" maxlength="256" value="' +
        escape(row["title"], quote=True) + '">'
        for index, row in enumerate(checked["authoring"]["achievements"]))
    plan_json = _canonical(checked["authoring"]).decode("ascii").replace("<", "\\u003c")
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Original quest achievement editor</title></head><body><main>'
        '<h1>Edit canonical quest milestones</h1>'
        '<p>Only authored choices unlock sandbox achievements. No external awards.</p>' +
        fields + '<script type="application/json" id="plan">' + plan_json +
        '</script><button id="export" type="button">Export edited plan</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("achievement editor exceeds byte budget")
    return html
