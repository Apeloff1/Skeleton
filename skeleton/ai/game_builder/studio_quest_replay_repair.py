"""Canonical quest replay recovery choices with explicit operator selection.

A broken authored action list is never silently rewritten. Every proposed
repair is an exact-source replay of a bounded legal prefix or one replacement
action. An operator must select one candidate digest before any handoff.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
)
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from .studio_quest_replay_diagnostic import (
    compile_replay_diagnostic, replay_replay_diagnostic,
)

SCHEMA = "skeleton.game_builder.studio_quest_replay_repair.v1"
APPROVAL_SCHEMA = "skeleton.game_builder.studio_quest_replay_repair_approval.v1"
PROMPT = "propose canonical repair choices for my first invalid quest action"
MAX_SOURCE_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 128 * 1024
MAX_HTML_BYTES = 128 * 1024


def compile_replay_repair(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Rehearse safe first-failure repairs; never infer user intent."""
    if authorized is not True:
        raise PermissionError("quest replay repair requires operator authority")
    _lease(expected_source_digest, "replay repair source")
    _lease(expected_initial_session_digest, "replay repair session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("replay repair source exceeds byte budget")
    diagnostic = compile_replay_diagnostic(
        documents, authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
    if diagnostic["status"] != "invalid_action":
        raise StudioQuestError("replay repair requires a first invalid action")
    invalid = diagnostic["first_invalid_action"]
    if type(invalid) is not dict:
        raise StudioQuestError("missing canonical invalid-action witness")
    prefix = diagnostic["accepted_actions"]
    if invalid["index"] != len(prefix):
        raise StudioQuestError("diagnostic invalid-action index diverged")
    program = compile_quest_program(documents)
    options = diagnostic["next_legal_actions"]
    if len(options) > 512:
        raise StudioQuestError("too many bounded replay repair candidates")
    candidates: list[dict[str, Any]] = []
    variants: list[tuple[str, list[list[str]]]] = [
        ("truncate_at_first_invalid", [list(pair) for pair in prefix]),
    ]
    variants.extend(
        ("replace_first_invalid_and_drop_tail",
         [list(pair) for pair in prefix] + [list(option)])
        for option in options
    )
    for kind, actions in variants:
        session = replay_quest(documents, actions, authorized=True)
        progress = quest_progress(session, documents)
        candidate: dict[str, Any] = {
            "repair_kind": kind,
            "actions": actions,
            "session_digest": session.digest,
            "target_ending_eligible": (
                diagnostic["target_ending"] in progress["sandbox_endings_eligible"]),
            "unmet_target_predicates": progress[
                "unmet_ending_predicates"].get(diagnostic["target_ending"], []),
            "dropped_action_count": (
                len(diagnostic["authoring"]["actions"]) - len(actions)),
        }
        candidate["candidate_digest"] = _digest(candidate)
        candidates.append(candidate)
    if _canonical(documents) != before:
        raise StudioQuestError("replay repair source changed during compile")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": diagnostic["initial_session_digest"],
        "original_authoring": diagnostic["authoring"],
        "original_diagnostic_digest": diagnostic["diagnostic_digest"],
        "first_invalid_action": invalid,
        "verified_prefix_session_digest": diagnostic[
            "verified_prefix_session_digest"],
        "candidates": candidates,
        "candidate_count": len(candidates),
        "status": "candidate_review_required",
        "explicit_operator_selection_required": True,
        "playable_handoff_allowed": False,
        "canonical_quest_replay_verified": True,
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("replay repair receipt exceeds byte budget")
    result["proposal_digest"] = _digest(result)
    return result


def replay_replay_repair(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest repair replay requires operator authority")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid quest repair proposal receipt")
    checked = compile_replay_repair(
        documents, receipt.get("original_authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("quest repair receipt differs from canonical replay")
    return checked


def approve_replay_repair(
    documents: Mapping[str, Any], proposal: object, approval: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Compile selected repair into a normal source-replayed diagnostic."""
    if authorized is not True:
        raise PermissionError("quest repair approval requires operator authority")
    _lease(expected_source_digest, "repair approval source")
    _lease(expected_initial_session_digest, "repair approval session")
    checked = replay_replay_repair(documents, proposal, authorized=True)
    if (checked["source_digest"] != expected_source_digest
            or checked["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale quest repair approval lease")
    if (type(approval) is not dict
            or set(approval) != {"schema", "proposal_digest", "candidate_digest"}
            or approval.get("schema") != APPROVAL_SCHEMA
            or approval.get("proposal_digest") != checked["proposal_digest"]
            or type(approval.get("candidate_digest")) is not str
            or len(_canonical(approval)) > 4096):
        raise StudioQuestError("invalid or stale quest repair approval")
    selected = [
        candidate for candidate in checked["candidates"]
        if candidate["candidate_digest"] == approval["candidate_digest"]
    ]
    if len(selected) != 1:
        raise StudioQuestError("unknown or ambiguous repair candidate")
    candidate = selected[0]
    authoring = {
        "actions": candidate["actions"],
        "target_ending": checked["original_authoring"]["target_ending"],
        "expected_final_session_digest": candidate["session_digest"],
    }
    diagnostic = compile_replay_diagnostic(
        documents, authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
    if (diagnostic["first_invalid_action"] is not None
            or diagnostic["verified_prefix_session_digest"] != candidate["session_digest"]
            or diagnostic["target_ending_eligible"] != candidate["target_ending_eligible"]):
        raise StudioQuestError("approved quest repair replay diverged")
    return replay_replay_diagnostic(documents, diagnostic, authorized=True)


def propose_replay_repair(
    documents: Mapping[str, Any], prompt: str, authoring: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported quest replay repair prompt")
    return compile_replay_repair(
        documents, authoring, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)


_SCRIPT = """(() => {
  'use strict';
  const get = id => document.getElementById(id);
  get('export').addEventListener('click', () => {
    try {
      const options = JSON.parse(get('candidates').textContent);
      const index = Number(get('choice').value);
      if (!Number.isInteger(index) || index < 0 || index >= options.length)
        throw Error('invalid candidate');
      const payload = {
        schema: get('schema').value,
        proposal_digest: get('proposal').value,
        candidate_digest: options[index]
      };
      const data = JSON.stringify(payload);
      if (new TextEncoder().encode(data).length > 4096) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([data], {type:'application/json'}));
      const a = document.createElement('a');
      a.href = url; a.download = 'quest-repair-approval.json'; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      get('status').textContent = 'Selection exported; CLI canonical approval still required.';
    } catch (_) {
      get('status').textContent = 'Invalid selection; nothing exported.';
    }
  });
})();"""


def render_replay_repair_html(
    documents: Mapping[str, Any], proposal: object, *, authorized: bool,
) -> bytes:
    checked = replay_replay_repair(documents, proposal, authorized=authorized)
    options = "".join(
        '<option value="' + str(index) + '">' +
        escape(row["repair_kind"], quote=True) + " — " +
        str(len(row["actions"])) + " steps; ending eligible: " +
        str(row["target_ending_eligible"]).lower() + "</option>"
        for index, row in enumerate(checked["candidates"])
    )
    hashes = json.dumps(
        [row["candidate_digest"] for row in checked["candidates"]],
        separators=(",", ":"), ensure_ascii=True)
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Quest replay recovery review</title></head><body><main>'
        '<h1>Review source-replayed quest recovery choices</h1>'
        '<p>Only the verified legal prefix or one legal replacement may be '
        'selected. Every discarded action requires explicit review.</p>'
        '<input type="hidden" id="schema" value="' + APPROVAL_SCHEMA + '">'
        '<input type="hidden" id="proposal" value="' +
        checked["proposal_digest"] + '">'
        '<label for="choice">Repair candidate</label><select id="choice">' +
        options + '</select><script type="application/json" id="candidates">' +
        hashes + '</script>'
        '<button type="button" id="export">Export selection</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<p>Offline preview is not native gameplay or release proof.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("quest replay repair HTML exceeds byte budget")
    return html
