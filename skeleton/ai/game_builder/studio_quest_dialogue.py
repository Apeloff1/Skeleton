"""Original authored NPC dialogue tied to canonical quest and relationship replay.

No language model output is silently treated as original, reviewed dialogue.
Every playable line requires explicit author text and approval.
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
    StudioQuestError, compile_quest_program, quest_progress, replay_quest, start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json
from .studio_quest_npc_relationships import replay_quest_npc_relationships

SCHEMA = "skeleton.game_builder.studio_quest_dialogue.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_dialogue_plan.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_dialogue_handoff.v1"
PROMPT = "author reviewed original NPC dialogue for my canonical quest choices"
FILENAME = "studio_quest_dialogue.json"
MAX_SOURCE = 256 * 1024
MAX_PLAN = 196608
MAX_RECEIPT = 262144
MAX_HTML = 393216
MAX_LINES = 128
DELIVERIES = ("neutral", "whisper", "shout", "aside")


def _text(value: object, label: str, maximum: int, *, empty: bool = False) -> str:
    if (type(value) is not str or len(value) > maximum
            or (not empty and not value) or value.strip() != value
            or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f
                   or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid quest dialogue " + label)
    return value


def propose_quest_dialogue(
    documents: Mapping[str, Any], npc_receipt: object, prompt: str, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest dialogue proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported original quest dialogue prompt")
    _lease(expected_source_digest, "dialogue source")
    _lease(expected_initial_session_digest, "dialogue initial session")
    npc = replay_quest_npc_relationships(
        documents, npc_receipt, authorized=True)
    if (npc["source_digest"] != expected_source_digest
            or npc["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale dialogue source or NPC relationship lease")
    actions = npc["authoring"]["actions"]
    plan = {
        "schema": PLAN_SCHEMA,
        "npc_relationship_digest": npc["relationship_digest"],
        "actions": [list(x) for x in actions],
        "target_ending": npc["authoring"]["target_ending"],
        "lines": [
            {"stage_id": stage, "choice": choice, "beat_index": 0,
             "speaker": "", "text": "", "delivery": "neutral",
             "reviewed": False}
            for stage, choice in actions
        ],
    }
    if len(_canonical(plan)) > MAX_PLAN:
        raise StudioQuestError("dialogue proposal exceeds byte budget")
    return plan


def _plan(value: object, npc: Mapping[str, Any]) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {
            "schema", "npc_relationship_digest", "actions",
            "target_ending", "lines"}
            or value.get("schema") != PLAN_SCHEMA
            or len(_canonical(value)) > MAX_PLAN):
        raise StudioQuestError("invalid typed original dialogue plan")
    if value["npc_relationship_digest"] != npc["relationship_digest"]:
        raise StudioQuestError("dialogue NPC relationship lease changed")
    if (value["actions"] != npc["authoring"]["actions"]
            or value["target_ending"] != npc["authoring"]["target_ending"]):
        raise StudioQuestError("dialogue source actions or target changed")
    actions = npc["authoring"]["actions"]
    rows = value["lines"]
    if type(rows) is not list or len(rows) > MAX_LINES:
        raise StudioQuestError("dialogue line budget exceeded")
    actors = {x["id"] for x in npc["authoring"]["actors"]}
    clean = []
    previous_action = -1
    next_index = 0
    for row in rows:
        if type(row) is not dict or set(row) != {
                "stage_id", "choice", "beat_index", "speaker", "text",
                "delivery", "reviewed"}:
            raise StudioQuestError("invalid dialogue line fields")
        stage = _text(row["stage_id"], "stage", 256)
        choice = _text(row["choice"], "choice", 256)
        action = [stage, choice]
        # The canonical session may have repeated alternative names on distinct
        # stages, but stage IDs themselves cannot repeat in one playthrough.
        try:
            position = actions.index(action)
        except ValueError as exc:
            raise StudioQuestError("dialogue line refers to unplayed choice") from exc
        if position < previous_action:
            raise StudioQuestError("dialogue lines must preserve canonical action order")
        if position != previous_action:
            if previous_action >= 0 and next_index == 0:
                raise StudioQuestError("missing dialogue beat")
            previous_action = position
            next_index = 0
        beat = row["beat_index"]
        if type(beat) is not int or beat != next_index or beat >= 4:
            raise StudioQuestError("dialogue beats must be contiguous and bounded")
        next_index += 1
        speaker = _text(row["speaker"], "speaker", 64, empty=True)
        if speaker and speaker not in actors:
            raise StudioQuestError("dialogue speaker not in original NPC roster")
        line = _text(row["text"], "text", 1024, empty=True)
        delivery = row["delivery"]
        if type(delivery) is not str or delivery not in DELIVERIES:
            raise StudioQuestError("invalid authored dialogue delivery")
        reviewed = row["reviewed"]
        if type(reviewed) is not bool or (reviewed and (not speaker or not line)):
            raise StudioQuestError("reviewed dialogue requires speaker and original text")
        clean.append({
            "stage_id": stage, "choice": choice, "beat_index": beat,
            "speaker": speaker, "text": line, "delivery": delivery,
            "reviewed": reviewed,
        })
    # No skipped canonical action may be hidden by omitting its dialogue rows.
    if len(actions) != len({(x["stage_id"], x["choice"]) for x in clean}):
        raise StudioQuestError("dialogue requires at least one beat per played action")
    if [list(x) for x in dict.fromkeys(
            (r["stage_id"], r["choice"]) for r in clean)] != actions:
        raise StudioQuestError("dialogue action coverage or order differs")
    return {
        "schema": PLAN_SCHEMA, "npc_relationship_digest": npc["relationship_digest"],
        "actions": [list(x) for x in actions],
        "target_ending": npc["authoring"]["target_ending"], "lines": clean,
    }


def compile_quest_dialogue(
    documents: Mapping[str, Any], npc_receipt: object, authoring: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest dialogue compile requires authorization")
    _lease(expected_source_digest, "dialogue source")
    _lease(expected_initial_session_digest, "dialogue initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE:
        raise StudioQuestError("dialogue source exceeds byte budget")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    npc = replay_quest_npc_relationships(documents, npc_receipt, authorized=True)
    if (program.source_digest != expected_source_digest
            or initial.digest != expected_initial_session_digest
            or npc["source_digest"] != expected_source_digest
            or npc["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale dialogue source, session or NPC receipt")
    plan = _plan(authoring, npc)
    session = replay_quest(documents, plan["actions"], authorized=True)
    if session.digest != npc["session_digest"]:
        raise StudioQuestError("dialogue session differs from canonical NPC replay")
    progress = quest_progress(session, documents)
    reviewed = bool(plan["lines"]) and all(x["reviewed"] for x in plan["lines"])
    target_ready = plan["target_ending"] in progress["sandbox_endings_eligible"]
    if _canonical(documents) != before:
        raise StudioQuestError("dialogue source changed during compile")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "npc_relationship_digest": npc["relationship_digest"],
        "authoring": plan,
        "reviewed_line_count": sum(x["reviewed"] for x in plan["lines"]),
        "line_count": len(plan["lines"]),
        "all_lines_reviewed": reviewed,
        "target_ending_eligible": target_ready,
        "unmet_target_predicates": progress["unmet_ending_predicates"].get(
            plan["target_ending"], []),
        "playable_handoff_allowed": bool(
            reviewed and target_ready and npc["playable_handoff_allowed"]),
        "originality_author_review_required": True,
        "voice_audio_generated": False, "npc_behavior_observed": False,
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT - 128:
        raise StudioQuestError("dialogue receipt exceeds byte budget")
    result["dialogue_digest"] = _digest(result)
    return result


def replay_quest_dialogue(
    documents: Mapping[str, Any], npc_receipt: object, receipt: object, *,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dialogue replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid dialogue receipt")
    checked = compile_quest_dialogue(
        documents, npc_receipt, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("dialogue receipt differs from canonical replay")
    return checked


def compile_quest_dialogue_handoff(
    documents: Mapping[str, Any], npc_receipt: object, receipt: object, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_dialogue(
        documents, npc_receipt, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("dialogue handoff requires reviewed eligible NPC route")
    session = replay_quest(
        documents, checked["authoring"]["actions"], authorized=True)
    if session.digest != checked["session_digest"]:
        raise StudioQuestError("dialogue playable handoff diverged")
    result = {
        "schema": HANDOFF_SCHEMA, "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": session.digest,
        "npc_relationship_digest": checked["npc_relationship_digest"],
        "dialogue_digest": checked["dialogue_digest"],
        "canonical_choices": [list(x) for x in session.choices],
        "target_ending": checked["authoring"]["target_ending"],
        "authored_dialogue_lines": checked["authoring"]["lines"],
        "voice_audio_generated": False, "npc_behavior_observed": False,
        "native_gameplay_verified": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_dialogue(
    documents: Mapping[str, Any], npc_receipt: object, receipt: object,
    directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_dialogue(
        documents, npc_receipt, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("dialogue publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".quest-dialogue-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
    try:
        before = os.fstat(fd)
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
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
                raise StudioQuestError("dialogue output directory changed")
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
            "dialogue_digest": checked["dialogue_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_quest_dialogue(
    documents: Mapping[str, Any], npc_receipt: object, directory: Path, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dialogue restore requires authorization")
    _lease(expected_source_digest, "dialogue restore source")
    stored = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT)
    if stored.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale dialogue restore source")
    return replay_quest_dialogue(
        documents, npc_receipt, stored, authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  byId('export').addEventListener('click', () => {
    try {
      const plan = JSON.parse(byId('plan').textContent);
      plan.lines = plan.lines.map((line, i) => ({
        ...line,
        speaker: byId('speaker-' + i).value,
        text: byId('text-' + i).value,
        delivery: byId('delivery-' + i).value,
        reviewed: byId('review-' + i).checked
      }));
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 196608) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-dialogue-edited-plan.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      byId('status').textContent = 'Exported; canonical CLI review required.';
    } catch (_) { byId('status').textContent = 'Invalid edit; no export.'; }
  });
})();"""


def render_quest_dialogue_editor_html(
    documents: Mapping[str, Any], npc_receipt: object, receipt: object, *,
    authorized: bool,
) -> bytes:
    checked = replay_quest_dialogue(
        documents, npc_receipt, receipt, authorized=authorized)
    npc = replay_quest_npc_relationships(documents, npc_receipt, authorized=True)
    actors = [x["id"] for x in npc["authoring"]["actors"]]
    plan = checked["authoring"]
    rows = []
    for i, line in enumerate(plan["lines"]):
        speaker_options = '<option value="">Select original NPC</option>' + "".join(
            '<option value="' + escape(actor, quote=True) + '"' +
            (" selected" if actor == line["speaker"] else "") + '>' +
            escape(actor) + '</option>' for actor in actors)
        delivery_options = "".join(
            '<option value="' + delivery + '"' +
            (" selected" if delivery == line["delivery"] else "") + '>' +
            delivery + '</option>' for delivery in DELIVERIES)
        rows.append(
            '<fieldset><legend>' + escape(line["stage_id"] + " / " +
                                          line["choice"]) + '</legend>'
            '<label for="speaker-' + str(i) + '">Speaker</label>'
            '<select id="speaker-' + str(i) + '">' + speaker_options + '</select>'
            '<label for="text-' + str(i) + '">Original dialogue</label>'
            '<textarea id="text-' + str(i) + '" maxlength="1024">' +
            escape(line["text"]) + '</textarea>'
            '<label for="delivery-' + str(i) + '">Text delivery</label>'
            '<select id="delivery-' + str(i) + '">' + delivery_options + '</select>'
            '<label for="review-' + str(i) + '">Reviewed</label>'
            '<input type="checkbox" id="review-' + str(i) + '"' +
            (" checked" if line["reviewed"] else "") + '></fieldset>')
    plan_json = _canonical(plan).decode("ascii").replace("<", "\\u003c")
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Original NPC quest dialogue editor</title></head><body><main>'
        '<h1>Author and review original quest dialogue</h1>'
        '<p>These are authored text lines, not synthesized voice or NPC observations.</p>' +
        "".join(rows) +
        '<script id="plan" type="application/json">' + plan_json + '</script>'
        '<button id="export" type="button">Export edited dialogue plan</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("dialogue editor exceeds byte budget")
    return html
