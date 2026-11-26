"""Source-bound, operator-selected quest branch workbench.

Preview every immediately legal fork from an authored replay checkpoint.  A
preview cannot modify a quest or mint evidence.  Only a separate, exact-source
approval can commit one fork to a private, replay-verified checkpoint.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
    start_quest, step_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json

SCHEMA = "skeleton.game_builder.studio_quest_branch_workbench.v1"
APPROVAL_SCHEMA = "skeleton.game_builder.studio_quest_branch_approval.v1"
COMMIT_SCHEMA = "skeleton.game_builder.studio_quest_branch_checkpoint.v1"
PROMPT = "preview legal canonical quest forks from my current checkpoint"
FILENAME = "studio_quest_branch_checkpoint.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_PLAN_BYTES = 32768
MAX_RECEIPT_BYTES = 65536
MAX_HTML_BYTES = 131072
MAX_ACTIONS = 64
MAX_CANDIDATES = 512


def _authoring(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {"actions", "target_ending"}:
        raise StudioQuestError("invalid quest fork authoring fields")
    actions = value["actions"]
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise StudioQuestError("invalid quest fork action count")
    for action in actions:
        if (type(action) is not list or len(action) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256
                       or x.strip() != x or any(ord(c) < 32 for c in x)
                       for x in action)):
            raise StudioQuestError("invalid typed quest fork action")
    target = value["target_ending"]
    if type(target) is not str or not 1 <= len(target) <= 256:
        raise StudioQuestError("invalid quest fork target ending")
    if len(_canonical(value)) > MAX_PLAN_BYTES:
        raise StudioQuestError("quest fork authoring exceeds byte budget")
    return {"actions": [list(x) for x in actions], "target_ending": target}


def compile_branch_workbench(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Produce source-replayed candidates; never silently select a branch."""
    if authorized is not True:
        raise PermissionError("quest fork preview requires operator authorization")
    _lease(expected_source_digest, "quest fork source")
    _lease(expected_initial_session_digest, "quest fork initial session")
    original = _canonical(documents)
    if len(original) > MAX_SOURCE_BYTES:
        raise StudioQuestError("quest fork source exceeds byte budget")
    plan = _authoring(authoring)
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale quest fork source lease")
    initial = start_quest(documents, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale quest fork initial session lease")
    if plan["target_ending"] not in {name for name, _ in program.endings}:
        raise StudioQuestError("unknown quest fork target ending")
    checkpoint = replay_quest(documents, plan["actions"], authorized=True)
    baseline = quest_progress(checkpoint, documents)
    stage_map = {stage.key: stage for stage in program.stages}
    candidates: list[dict[str, Any]] = []
    for stage_id in baseline["available"]:
        stage = stage_map[stage_id]
        for alternative in stage.alternatives:
            if len(candidates) >= MAX_CANDIDATES:
                raise StudioQuestError("quest fork candidate budget exceeded")
            fork = step_quest(
                checkpoint, documents, stage=stage_id,
                alternative=alternative, authorized=True)
            progress = quest_progress(fork, documents)
            row: dict[str, Any] = {
                "action": [stage_id, alternative],
                "fork_session_digest": fork.digest,
                "newly_eligible_endings": sorted(
                    set(progress["sandbox_endings_eligible"]) -
                    set(baseline["sandbox_endings_eligible"])),
                "target_ending_eligible": (
                    plan["target_ending"] in progress["sandbox_endings_eligible"]),
                "unmet_target_predicates": progress[
                    "unmet_ending_predicates"].get(plan["target_ending"], []),
                "available_after": progress["available"],
            }
            row["candidate_digest"] = _digest(row)
            candidates.append(row)
    if _canonical(documents) != original:
        raise StudioQuestError("quest fork source changed during preview")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "authoring": plan,
        "checkpoint_session_digest": checkpoint.digest,
        "target_ending": plan["target_ending"],
        "checkpoint_eligible_endings": baseline["sandbox_endings_eligible"],
        "candidates": candidates,
        "candidate_count": len(candidates),
        "status": "operator_selection_required" if candidates else "no_legal_forks",
        "explicit_operator_selection_required": True,
        "playable_handoff_allowed": False,
        "canonical_quest_replay_verified": True,
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("quest fork preview exceeds receipt budget")
    result["proposal_digest"] = _digest(result)
    return result


def propose_branch_workbench(
    documents: Mapping[str, Any], prompt: str, authoring: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported quest fork prompt")
    return compile_branch_workbench(
        documents, authoring, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)


def replay_branch_workbench(
    documents: Mapping[str, Any], proposal: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest fork replay requires authorization")
    if type(proposal) is not dict or proposal.get("schema") != SCHEMA:
        raise StudioQuestError("invalid quest fork proposal receipt")
    checked = compile_branch_workbench(
        documents, proposal.get("authoring"), authorized=True,
        expected_source_digest=proposal.get("source_digest"),
        expected_initial_session_digest=proposal.get("initial_session_digest"))
    if _canonical(checked) != _canonical(proposal):
        raise StudioQuestError("quest fork proposal differs from canonical replay")
    return checked


def approve_branch_fork(
    documents: Mapping[str, Any], proposal: object, approval: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Commit exactly one approved fork; no implicit selection or file write."""
    if authorized is not True:
        raise PermissionError("quest fork approval requires operator authorization")
    _lease(expected_source_digest, "quest fork approval source")
    _lease(expected_initial_session_digest, "quest fork approval session")
    checked = replay_branch_workbench(documents, proposal, authorized=True)
    if (checked["source_digest"] != expected_source_digest
            or checked["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale quest fork approval lease")
    if (type(approval) is not dict
            or set(approval) != {"schema", "proposal_digest", "candidate_digest"}
            or approval.get("schema") != APPROVAL_SCHEMA
            or approval.get("proposal_digest") != checked["proposal_digest"]
            or type(approval.get("candidate_digest")) is not str
            or len(_canonical(approval)) > 4096):
        raise StudioQuestError("invalid or stale quest fork approval")
    selected = [c for c in checked["candidates"]
                if c["candidate_digest"] == approval["candidate_digest"]]
    if len(selected) != 1:
        raise StudioQuestError("unknown or ambiguous quest fork candidate")
    row = selected[0]
    actions = checked["authoring"]["actions"] + [row["action"]]
    session = replay_quest(documents, actions, authorized=True)
    progress = quest_progress(session, documents)
    if (session.digest != row["fork_session_digest"]
            or (checked["target_ending"] in progress["sandbox_endings_eligible"])
            != row["target_ending_eligible"]):
        raise StudioQuestError("approved quest fork replay diverged")
    result: dict[str, Any] = {
        "schema": COMMIT_SCHEMA,
        "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "initial_session_digest": checked["initial_session_digest"],
        "authoring": checked["authoring"],
        "approval": dict(approval),
        "proposal_digest": checked["proposal_digest"],
        "checkpoint_session_digest": checked["checkpoint_session_digest"],
        "actions": actions,
        "fork_session_digest": session.digest,
        "target_ending": checked["target_ending"],
        "target_ending_eligible": row["target_ending_eligible"],
        "unmet_target_predicates": row["unmet_target_predicates"],
        "playable_handoff_allowed": row["target_ending_eligible"],
        "canonical_quest_replay_verified": True,
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("approved quest fork exceeds receipt budget")
    result["checkpoint_digest"] = _digest(result)
    return result


def replay_approved_branch(
    documents: Mapping[str, Any], checkpoint: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest fork checkpoint replay requires authorization")
    if type(checkpoint) is not dict or checkpoint.get("schema") != COMMIT_SCHEMA:
        raise StudioQuestError("invalid quest fork checkpoint")
    proposal = compile_branch_workbench(
        documents, checkpoint.get("authoring"), authorized=True,
        expected_source_digest=checkpoint.get("source_digest"),
        expected_initial_session_digest=checkpoint.get("initial_session_digest"))
    checked = approve_branch_fork(
        documents, proposal, checkpoint.get("approval"), authorized=True,
        expected_source_digest=checkpoint.get("source_digest"),
        expected_initial_session_digest=checkpoint.get("initial_session_digest"))
    if _canonical(checked) != _canonical(checkpoint):
        raise StudioQuestError("quest fork checkpoint differs from canonical replay")
    return checked


def compile_branch_handoff(
    documents: Mapping[str, Any], checkpoint: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_approved_branch(documents, checkpoint, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("quest fork ending is not eligible for playable handoff")
    session = replay_quest(documents, checked["actions"], authorized=True)
    if session.digest != checked["fork_session_digest"]:
        raise StudioQuestError("quest fork handoff replay diverged")
    result = {
        "schema": "skeleton.game_builder.studio_quest_branch_handoff.v1",
        "project_id": checked["project_id"],
        "quest_source_digest": checked["source_digest"],
        "quest_session_digest": session.digest,
        "target_ending": checked["target_ending"],
        "checkpoint_digest": checked["checkpoint_digest"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_branch_checkpoint(
    documents: Mapping[str, Any], checkpoint: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    """Exclusive, private, fsynced checkpoint; never overwrite existing work."""
    checked = replay_approved_branch(documents, checkpoint, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("quest fork checkpoint exceeds disk byte budget")
    fd = _open_directory(directory)
    temporary = ".quest-branch-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
    try:
        initial = os.fstat(fd)
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
        check_fd = _open_directory(directory)
        try:
            current = os.fstat(check_fd)
            if (initial.st_dev, initial.st_ino) != (current.st_dev, current.st_ino):
                raise StudioQuestError("quest fork output directory changed")
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
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {
        "path": str(Path(directory) / FILENAME),
        "checkpoint_digest": checked["checkpoint_digest"],
        "bytes": len(raw),
        "file_write_performed": True,
        "release_certified": False,
    }


def restore_branch_checkpoint(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest fork restore requires authorization")
    _lease(expected_source_digest, "quest fork restore source")
    receipt = read_studio_private_json(Path(directory) / FILENAME,
                                       MAX_RECEIPT_BYTES)
    if receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale quest fork restore source")
    return replay_approved_branch(documents, receipt, authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const get = id => document.getElementById(id);
  get('export').addEventListener('click', () => {
    try {
      const candidates = JSON.parse(get('candidates').textContent);
      const index = Number(get('choice').value);
      if (!Number.isInteger(index) || index < 0 || index >= candidates.length)
        throw Error('invalid choice');
      const payload = {schema: get('schema').value,
        proposal_digest: get('proposal').value,
        candidate_digest: candidates[index]};
      const raw = JSON.stringify(payload);
      if (new TextEncoder().encode(raw).length > 4096) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type:'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-branch-approval.json'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      get('status').textContent = 'Selection exported. CLI source replay required.';
    } catch (_) {
      get('status').textContent = 'Invalid selection; nothing exported.';
    }
  });
})();"""


def render_branch_workbench_html(
    documents: Mapping[str, Any], proposal: object, *, authorized: bool,
) -> bytes:
    checked = replay_branch_workbench(documents, proposal, authorized=authorized)
    options = "".join(
        '<option value="' + str(i) + '">' +
        escape(row["action"][0], quote=True) + " — " +
        escape(row["action"][1], quote=True) + " | target eligible: " +
        str(row["target_ending_eligible"]).lower() + "</option>"
        for i, row in enumerate(checked["candidates"]))
    digests = json.dumps([row["candidate_digest"] for row in checked["candidates"]],
                         ensure_ascii=True, separators=(",", ":"))
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Quest branch workbench</title></head><body><main>'
        '<h1>Review canonical quest branches</h1>'
        '<p>Every choice is source-replayed. Preview never commits or publishes.</p>'
        '<input id="schema" type="hidden" value="' + APPROVAL_SCHEMA + '">'
        '<input id="proposal" type="hidden" value="' +
        checked["proposal_digest"] + '">'
        '<label for="choice">Next legal authored choice</label>'
        '<select id="choice">' + options + '</select>'
        '<script type="application/json" id="candidates">' + digests + '</script>'
        '<button id="export" type="button">Export selected fork</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<p>Offline preview is not native gameplay or release proof.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("quest fork HTML exceeds byte budget")
    return html
