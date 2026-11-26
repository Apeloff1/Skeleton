"""Source-bound quest branch review, deterministic consequences and playable handoff.

Compares two authored alternative action histories against the canonical quest
simulator. A review approves presentation and route selection, never evidence.
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
from .studio_quest_consequence_diff import compile_quest_consequence_diff

SCHEMA = "skeleton.game_builder.studio_quest_branch_review.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_branch_plan.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_branch_handoff.v1"
PROMPT = "compare two original quest branches and review their ending consequences"
FILENAME = "studio_quest_branch_review.json"
MAX_SOURCE = 256 * 1024
MAX_PLAN = 65536
MAX_RECEIPT = 131072
MAX_HTML = 262144


def _text(value: object, label: str, maximum: int, *, allow_empty: bool = False) -> str:
    if (type(value) is not str or len(value) > maximum
            or (not allow_empty and not value) or value.strip() != value
            or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f
                   or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid branch review " + label)
    return value


def _actions(value: object) -> list[list[str]]:
    if type(value) is not list or len(value) > 64:
        raise StudioQuestError("invalid branch action budget")
    result = []
    for pair in value:
        if (type(pair) is not list or len(pair) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256 for x in pair)):
            raise StudioQuestError("invalid branch action pair")
        result.append([pair[0], pair[1]])
    return result


def propose_quest_branch_review(
    documents: Mapping[str, Any], prompt: str, left_actions: object,
    right_actions: object, target_ending: str, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("branch proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported branch proposal prompt")
    _lease(expected_source_digest, "branch source")
    _lease(expected_initial_session_digest, "branch initial session")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale branch source")
    if start_quest(documents, authorized=True).digest != expected_initial_session_digest:
        raise StudioQuestError("stale branch initial session")
    if target_ending not in dict(program.endings):
        raise StudioQuestError("unknown branch target ending")
    left = _actions(left_actions)
    right = _actions(right_actions)
    replay_quest(documents, left, authorized=True)
    replay_quest(documents, right, authorized=True)
    plan = {
        "schema": PLAN_SCHEMA, "left_actions": left, "right_actions": right,
        "target_ending": target_ending, "selected": "left",
        "reviewed": False, "review_note": "",
    }
    if len(_canonical(plan)) > MAX_PLAN:
        raise StudioQuestError("branch plan exceeds byte budget")
    return plan


def _validate_plan(plan: object, program: Any) -> dict[str, Any]:
    if (type(plan) is not dict or set(plan) != {
            "schema", "left_actions", "right_actions", "target_ending",
            "selected", "reviewed", "review_note"}
            or plan.get("schema") != PLAN_SCHEMA):
        raise StudioQuestError("invalid typed branch plan")
    if len(_canonical(plan)) > MAX_PLAN:
        raise StudioQuestError("branch plan exceeds byte budget")
    target = _text(plan["target_ending"], "target", 256)
    if target not in dict(program.endings):
        raise StudioQuestError("unknown branch ending")
    if plan["selected"] not in ("left", "right") or type(plan["selected"]) is not str:
        raise StudioQuestError("invalid branch selection")
    if type(plan["reviewed"]) is not bool:
        raise StudioQuestError("branch review must be explicit boolean")
    return {
        "schema": PLAN_SCHEMA, "left_actions": _actions(plan["left_actions"]),
        "right_actions": _actions(plan["right_actions"]),
        "target_ending": target, "selected": plan["selected"],
        "reviewed": plan["reviewed"],
        "review_note": _text(plan["review_note"], "note", 1024, allow_empty=True),
    }


def compile_quest_branch_review(
    documents: Mapping[str, Any], plan: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("branch compile requires authorization")
    _lease(expected_source_digest, "branch source")
    _lease(expected_initial_session_digest, "branch initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE:
        raise StudioQuestError("branch source exceeds byte budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale branch source lease")
    initial = start_quest(documents, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale branch initial session lease")
    checked = _validate_plan(plan, program)
    if checked["left_actions"] == checked["right_actions"]:
        raise StudioQuestError("branch comparison requires distinct authored histories")
    left = replay_quest(documents, checked["left_actions"], authorized=True)
    right = replay_quest(documents, checked["right_actions"], authorized=True)
    left_progress = quest_progress(left, documents)
    right_progress = quest_progress(right, documents)
    selected = checked["selected"]
    chosen = left if selected == "left" else right
    chosen_progress = left_progress if selected == "left" else right_progress
    common = 0
    for a, b in zip(left.choices, right.choices):
        if a != b:
            break
        common += 1
    left_ending = left_progress["sandbox_endings_eligible"]
    right_ending = right_progress["sandbox_endings_eligible"]
    counterfactual = compile_quest_consequence_diff(
        documents, {"baseline_actions": checked["left_actions"],
                    "candidate_actions": checked["right_actions"]},
        authorized=True, expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    if (counterfactual["first_divergence_index"] != common
            or counterfactual["ending_delta"]["lost"] != sorted(set(left_ending) - set(right_ending))
            or counterfactual["ending_delta"]["gained"] != sorted(set(right_ending) - set(left_ending))):
        raise StudioQuestError("independent counterfactual proof diverged")
    target = checked["target_ending"]
    if _canonical(documents) != before:
        raise StudioQuestError("branch source mutated during compilation")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "authoring": checked, "left_session_digest": left.digest,
        "right_session_digest": right.digest,
        "selected_session_digest": chosen.digest,
        "canonical_counterfactual_digest": counterfactual["receipt_digest"],
        "common_prefix_actions": common,
        "left_unique_actions": [list(x) for x in left.choices[common:]],
        "right_unique_actions": [list(x) for x in right.choices[common:]],
        "left_eligible_endings": left_ending,
        "right_eligible_endings": right_ending,
        "left_only_endings": sorted(set(left_ending) - set(right_ending)),
        "right_only_endings": sorted(set(right_ending) - set(left_ending)),
        "left_unmet_target_predicates": left_progress["unmet_ending_predicates"].get(target, []),
        "right_unmet_target_predicates": right_progress["unmet_ending_predicates"].get(target, []),
        "selected_target_eligible": target in chosen_progress["sandbox_endings_eligible"],
        "playable_handoff_allowed": (
            checked["reviewed"] and target in chosen_progress["sandbox_endings_eligible"]),
        "canonical_quest_replay_verified": True,
        "external_evidence_verified": False,
        "native_gameplay_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT - 128:
        raise StudioQuestError("branch receipt exceeds byte budget")
    result["branch_review_digest"] = _digest(result)
    return result


def replay_quest_branch_review(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("branch replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid branch receipt")
    checked = compile_quest_branch_review(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("branch receipt differs from canonical replay")
    return checked


def compile_quest_branch_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_branch_review(documents, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("branch handoff requires reviewed eligible ending")
    plan = checked["authoring"]
    actions = plan[plan["selected"] + "_actions"]
    session = replay_quest(documents, actions, authorized=True)
    if session.digest != checked["selected_session_digest"]:
        raise StudioQuestError("selected branch replay diverged")
    result = {
        "schema": HANDOFF_SCHEMA, "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": session.digest,
        "branch_review_digest": checked["branch_review_digest"],
        "target_ending": plan["target_ending"],
        "canonical_choices": [list(x) for x in session.choices],
        "eligible_endings": quest_progress(session, documents)["sandbox_endings_eligible"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_branch_review(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_branch_review(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("branch publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".quest-branch-" + secrets.token_hex(16) + ".tmp"
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
                raise StudioQuestError("branch output directory changed")
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
            "branch_review_digest": checked["branch_review_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_quest_branch_review(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("branch restore requires authorization")
    _lease(expected_source_digest, "branch restore source")
    stored = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT)
    if stored.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale branch restore source")
    return replay_quest_branch_review(documents, stored, authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  byId('export').addEventListener('click', () => {
    try {
      const plan = JSON.parse(byId('plan').textContent);
      plan.selected = byId('selected').value;
      plan.reviewed = byId('reviewed').checked;
      plan.review_note = byId('note').value;
      if (!['left', 'right'].includes(plan.selected) ||
          plan.review_note.length > 1024 ||
          plan.review_note.trim() !== plan.review_note ||
          /[\\u0000-\\u001f\\u007f-\\u009f\\u202a-\\u202e\\u2066-\\u2069]/.test(plan.review_note))
        throw Error('invalid review');
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 65536) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'}));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'quest-branch-edited-plan.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      byId('status').textContent = 'Exported; canonical CLI compile required.';
    } catch (_) {
      byId('status').textContent = 'Invalid edit; no export.';
    }
  });
})();"""


def render_quest_branch_editor_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_branch_review(documents, receipt, authorized=authorized)
    plan = checked["authoring"]
    plan_json = _canonical(plan).decode("ascii").replace("<", "\\u003c")
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    def rows(side: str) -> str:
        actions = checked[side + "_unique_actions"]
        return "<ol>" + "".join(
            "<li>" + escape(stage) + " → " + escape(choice) + "</li>"
            for stage, choice in actions) + "</ol>"
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Original quest branch review</title></head><body><main>'
        '<h1>Canonical quest branch comparison</h1>'
        '<h2>Left branch</h2>' + rows("left") +
        '<h2>Right branch</h2>' + rows("right") +
        '<p>Shared action prefix: ' + str(checked["common_prefix_actions"]) + '</p>'
        '<p>Left-only eligible endings: ' +
        escape(", ".join(checked["left_only_endings"])) + '</p>'
        '<p>Right-only eligible endings: ' +
        escape(", ".join(checked["right_only_endings"])) + '</p>'
        '<label for="selected">Approved route</label><select id="selected">'
        '<option value="left"' + (" selected" if plan["selected"] == "left" else "") +
        '>Left</option><option value="right"' +
        (" selected" if plan["selected"] == "right" else "") + '>Right</option></select>'
        '<label for="note">Review note</label><textarea id="note" maxlength="1024">' +
        escape(plan["review_note"]) + '</textarea>'
        '<label for="reviewed">Explicit review complete</label>'
        '<input id="reviewed" type="checkbox"' +
        (" checked" if plan["reviewed"] else "") + '>'
        '<script id="plan" type="application/json">' + plan_json + '</script>'
        '<button id="export" type="button">Export reviewed plan</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<p>Review cannot mint quest predicates, external evidence or release proof.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("branch HTML exceeds byte budget")
    return html
