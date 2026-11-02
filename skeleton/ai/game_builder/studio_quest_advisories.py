"""Original quest content advisories with source-bound consent-gated handoff.

A warning plan is not a classifier, moderation verdict, or automatic permission
to play. Every authored stage requires human review; canonical stage actions
cannot be skipped, rewritten, or silently substituted by advisory settings.
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

SCHEMA = "skeleton.game_builder.studio_quest_advisories.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_advisory_plan.v1"
PROMPT = "prepare editable original quest content advisories for human review"
FILENAME = "studio_quest_advisories.json"
TOPICS = frozenset({
    "violence", "fear", "grief", "flashing", "loud_audio",
    "social_conflict", "isolation", "injury", "medical",
})
SPOILER_LEVELS = frozenset({"none", "mild", "major"})
MAX_SOURCE_BYTES = 256 * 1024
MAX_PLAN_BYTES = 65536
MAX_RECEIPT_BYTES = 131072
MAX_HTML_BYTES = 256 * 1024
MAX_ACTIONS = 64
MAX_STAGES = 64


def _text(value: object, label: str, maximum: int, *, empty: bool = False) -> str:
    if (type(value) is not str or len(value) > maximum
            or (not empty and not value) or value.strip() != value
            or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f
                   or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid advisory " + label)
    return value


def propose_quest_advisories(
    documents: Mapping[str, Any], prompt: str, actions: object, *,
    target_ending: str, authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Create blank, explicitly unreviewed descriptors; never infer safe content."""
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported quest advisory prompt")
    if authorized is not True:
        raise PermissionError("advisory proposal requires authorization")
    _lease(expected_source_digest, "advisory source")
    _lease(expected_initial_session_digest, "advisory initial session")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale advisory source")
    if start_quest(documents, authorized=True).digest != expected_initial_session_digest:
        raise StudioQuestError("stale advisory initial session")
    if target_ending not in dict(program.endings):
        raise StudioQuestError("unknown advisory target ending")
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise StudioQuestError("invalid advisory actions")
    session = replay_quest(documents, actions, authorized=True)
    plan = {
        "schema": PLAN_SCHEMA,
        "actions": [list(row) for row in session.choices],
        "target_ending": target_ending,
        "advisories": [
            {"stage_id": stage.key, "summary": "", "topics": [],
             "severity": 0, "spoiler_level": "none", "reviewed": False}
            for stage in program.stages
        ],
    }
    if len(_canonical(plan)) > MAX_PLAN_BYTES:
        raise StudioQuestError("advisory proposal exceeds byte budget")
    return plan


def _plan(value: object, program: Any) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {
            "schema", "actions", "target_ending", "advisories"}
            or value["schema"] != PLAN_SCHEMA):
        raise StudioQuestError("invalid typed advisory plan")
    if len(_canonical(value)) > MAX_PLAN_BYTES:
        raise StudioQuestError("advisory plan exceeds byte budget")
    actions = value["actions"]
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise StudioQuestError("invalid advisory action count")
    for row in actions:
        if (type(row) is not list or len(row) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256 for x in row)):
            raise StudioQuestError("invalid advisory replay action")
    target = value["target_ending"]
    if type(target) is not str or target not in dict(program.endings):
        raise StudioQuestError("unknown advisory target ending")
    rows = value["advisories"]
    if (type(rows) is not list or len(rows) != len(program.stages)
            or len(rows) > MAX_STAGES):
        raise StudioQuestError("advisory rows must cover all authored stages")
    clean: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if (type(row) is not dict or set(row) != {
                "stage_id", "summary", "topics", "severity",
                "spoiler_level", "reviewed"}):
            raise StudioQuestError("invalid advisory fields")
        stage_id = _text(row["stage_id"], "stage", 256)
        if stage_id != program.stages[index].key:
            raise StudioQuestError("advisories must preserve authored stage order")
        topics = row["topics"]
        if (type(topics) is not list or len(topics) > len(TOPICS)
                or any(type(x) is not str or x not in TOPICS for x in topics)
                or len(set(topics)) != len(topics) or topics != sorted(topics)):
            raise StudioQuestError("invalid advisory topic list")
        severity = row["severity"]
        if type(severity) is not int or not 0 <= severity <= 3:
            raise StudioQuestError("invalid advisory severity")
        if (not topics and severity != 0) or (topics and severity == 0):
            raise StudioQuestError("advisory severity and topics disagree")
        spoiler = row["spoiler_level"]
        if type(spoiler) is not str or spoiler not in SPOILER_LEVELS:
            raise StudioQuestError("invalid advisory spoiler level")
        if type(row["reviewed"]) is not bool:
            raise StudioQuestError("invalid advisory review flag")
        summary = _text(row["summary"], "summary", 512, empty=True)
        if topics and row["reviewed"] and not summary:
            raise StudioQuestError("reviewed warning needs a human-authored summary")
        clean.append({
            "stage_id": stage_id, "summary": summary, "topics": list(topics),
            "severity": severity, "spoiler_level": spoiler,
            "reviewed": row["reviewed"],
        })
    return {"schema": PLAN_SCHEMA, "actions": [list(x) for x in actions],
            "target_ending": target, "advisories": clean}


def compile_quest_advisories(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("advisory compilation requires authorization")
    _lease(expected_source_digest, "advisory source")
    _lease(expected_initial_session_digest, "advisory initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("advisory source exceeds byte budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale advisory source lease")
    initial = start_quest(documents, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale advisory initial session lease")
    plan = _plan(authoring, program)
    session = replay_quest(documents, plan["actions"], authorized=True)
    progress = quest_progress(session, documents)
    rows = {row["stage_id"]: row for row in plan["advisories"]}
    played = [dict(rows[stage]) for stage in session.completed]
    next_rows = [dict(rows[stage]) for stage in progress["available"]]
    all_reviewed = all(row["reviewed"] for row in plan["advisories"])
    target_ready = plan["target_ending"] in progress["sandbox_endings_eligible"]
    if _canonical(documents) != before:
        raise StudioQuestError("advisory source changed during compilation")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "authoring": plan,
        "played_stage_ids": list(session.completed),
        "available_stage_ids": progress["available"],
        "reviewed_stage_count": sum(row["reviewed"] for row in plan["advisories"]),
        "all_stages_reviewed": all_reviewed,
        "target_ending": plan["target_ending"],
        "target_ending_eligible": target_ready,
        "unmet_target_predicates": progress["unmet_ending_predicates"].get(
            plan["target_ending"], []),
        "advisory_handoff_allowed": all_reviewed and target_ready,
        "content_safety_inferred": False,
        "player_consent_granted": False,
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("advisory receipt exceeds byte budget")
    result["advisory_digest"] = _digest(result)
    return result


def replay_quest_advisories(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("advisory replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid advisory receipt")
    checked = compile_quest_advisories(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("advisory receipt differs from canonical replay")
    return checked


def evaluate_player_advisories(
    documents: Mapping[str, Any], receipt: object, accepted_topics: object, *,
    authorized: bool,
) -> dict[str, Any]:
    """Consent is explicit and local; this function does not skip quest actions."""
    checked = replay_quest_advisories(documents, receipt, authorized=authorized)
    if (type(accepted_topics) is not list or len(accepted_topics) > len(TOPICS)
            or any(type(x) is not str or x not in TOPICS for x in accepted_topics)
            or accepted_topics != sorted(set(accepted_topics))):
        raise StudioQuestError("invalid player consent topic set")
    if not checked["all_stages_reviewed"]:
        raise StudioQuestError("unreviewed authored advisories cannot be shown as safe")
    by_stage = {row["stage_id"]: row for row in checked["authoring"]["advisories"]}
    considered = checked["played_stage_ids"] + checked["available_stage_ids"]
    # Show warnings for already played stages and currently available stages.
    rows = [by_stage[stage] for stage in considered]
    rejected = sorted({tag for row in rows for tag in row["topics"]
                       if tag not in accepted_topics})
    result: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_player_consent.v1",
        "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": checked["session_digest"],
        "advisory_digest": checked["advisory_digest"],
        "accepted_topics": list(accepted_topics),
        "unaccepted_topics": rejected,
        "warnings": rows,
        "can_continue": not rejected,
        "target_ending_eligible": checked["target_ending_eligible"],
        "consent_scope": "current_canonical_checkpoint",
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    result["consent_digest"] = _digest(result)
    return result


def compile_advisory_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_advisories(documents, receipt, authorized=authorized)
    if not checked["advisory_handoff_allowed"]:
        raise StudioQuestError("advisory handoff requires reviewed eligible quest")
    session = replay_quest(
        documents, checked["authoring"]["actions"], authorized=True)
    if session.digest != checked["session_digest"]:
        raise StudioQuestError("advisory handoff canonical replay diverged")
    result: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_advisory_handoff.v1",
        "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": checked["session_digest"],
        "advisory_digest": checked["advisory_digest"],
        "target_ending": checked["target_ending"],
        "advisories": checked["authoring"]["advisories"],
        "content_safety_inferred": False,
        "player_consent_granted": False,
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_advisories(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_advisories(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("advisory publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".quest-advisory-" + secrets.token_hex(16) + ".tmp"
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
                raise StudioQuestError("advisory output directory changed")
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
            "advisory_digest": checked["advisory_digest"], "bytes": len(raw),
            "file_write_performed": True, "release_certified": False}


def restore_quest_advisories(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("advisory restore requires authorization")
    _lease(expected_source_digest, "advisory restore source")
    receipt = read_studio_private_json(
        Path(directory) / FILENAME, MAX_RECEIPT_BYTES)
    if receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale advisory restore source")
    return replay_quest_advisories(documents, receipt, authorized=True)


_EDITOR = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const plan = JSON.parse(byId('plan').textContent);
  byId('save').addEventListener('click', () => {
    try {
      const rows = Array.from(document.querySelectorAll('[data-advisory]'));
      if (rows.length !== plan.advisories.length) throw Error('row count changed');
      plan.advisories = plan.advisories.map((item, i) => {
        const row = rows[i];
        const topics = row.querySelector('[data-topics]').value
          .split(',').map(x => x.trim()).filter(Boolean).sort();
        return {stage_id:item.stage_id,
          summary:row.querySelector('[data-summary]').value,
          topics:topics, severity:Number(row.querySelector('[data-severity]').value),
          spoiler_level:row.querySelector('[data-spoiler]').value,
          reviewed:row.querySelector('[data-reviewed]').checked};
      });
      const blob = new Blob([JSON.stringify(plan)], {type:'application/json'});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-advisory-plan.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { byId('status').textContent = String(error); }
  });
})();"""


def render_advisory_editor_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_advisories(documents, receipt, authorized=authorized)
    nonce = secrets.token_urlsafe(24)
    plan = checked["authoring"]
    raw_plan = json.dumps(plan, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)
    raw_plan = (raw_plan.replace("&", "\\u0026").replace("<", "\\u003c")
                .replace(">", "\\u003e"))
    rows: list[str] = []
    for row in plan["advisories"]:
        def field(name: str, value: object, kind: str) -> str:
            return ('<label>' + escape(name) + ' <input data-' + kind +
                    ' value="' + escape(str(value), quote=True) + '"></label>')
        rows.append(
            '<li data-advisory><strong>' + escape(row["stage_id"]) + '</strong>' +
            field("Summary", row["summary"], "summary") +
            field("Topics, comma separated", ",".join(row["topics"]), "topics") +
            field("Severity 0-3", row["severity"], "severity") +
            field("Spoiler none/mild/major", row["spoiler_level"], "spoiler") +
            '<label>Reviewed <input data-reviewed type="checkbox"' +
            (' checked' if row["reviewed"] else '') + '></label></li>')
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'nonce-" + nonce +
        "'; connect-src 'none'; base-uri 'none'; form-action 'none'; "
        'object-src \'none\'">'
        '<title>Original quest content advisory editor</title></head><body><main>'
        '<h1>Human-reviewed original quest advisories</h1>'
        '<p>Unreviewed content is not assumed safe. Consent is separate.</p>'
        '<ol>' + ''.join(rows) + '</ol>'
        '<button id="save" type="button">Export reviewed advisory plan</button>'
        '<p id="status" role="status"></p>'
        '<script id="plan" type="application/json">' + raw_plan + '</script>'
        '<script nonce="' + nonce + '">' + _EDITOR + '</script>'
        '</main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("advisory editor exceeds HTML budget")
    return html
