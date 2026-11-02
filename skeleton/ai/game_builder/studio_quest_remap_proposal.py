"""Operator-reviewed quest choice remap proposal and exact-source approval.

A proposal is not approval. It is a deterministic explanation of prose changes
between a canonical quest save and a canon-checked authored revision. Nothing
is migrated or published until an explicit, separately validated approval.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
from typing import Any, Mapping
import json

from .studio_ecosystem_author_revision import preview_canon_revision
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from .studio_quest_revision_migration import (
    compile_quest_revision_migration, replay_quest_revision_migration,
)

SCHEMA = "skeleton.game_builder.studio_quest_remap_proposal.v1"
PROMPT = "propose explicit reviewed remaps for changed authored quest choices"
MAX_SOURCE_BYTES = 512 * 1024
MAX_RECEIPT_BYTES = 128 * 1024
MAX_REMAPS = 64
MAX_HTML_BYTES = 192 * 1024
EXPORT_SCHEMA = "skeleton.game_builder.studio_quest_remap_approval_export.v1"


def compile_quest_remap_proposal(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Explain selected changed prose, preserving authored choice semantics.

    The underlying migration compiler first validates the old replay, the
    canon revision, the protected graph, and ending requirements. The proposal
    is intentionally non-authoritative; no automatic migration is permitted.
    """
    if authorized is not True:
        raise PermissionError("remap proposal requires operator authorization")
    _lease(expected_source_digest, "remap proposal source")
    _lease(expected_initial_session_digest, "remap proposal session")
    original = _canonical(documents)
    if len(original) > MAX_SOURCE_BYTES:
        raise StudioQuestError("remap proposal source exceeds byte budget")
    if (type(authoring) is not dict or set(authoring) != {
            "revision_request", "actions", "target_ending"}
            or len(_canonical(authoring)) > 32768):
        raise StudioQuestError("invalid bounded remap proposal authoring")
    plan = {
        "revision_request": authoring["revision_request"],
        "actions": authoring["actions"],
        "remaps": [],
        "target_ending": authoring["target_ending"],
    }
    baseline = compile_quest_revision_migration(
        documents, plan, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
    revised, html, revision_receipt = preview_canon_revision(
        documents, authoring["revision_request"], authorized=True)
    old = compile_quest_program(documents)
    new = compile_quest_program(revised)
    if (old.source_digest != expected_source_digest
            or new.source_digest != baseline["new_quest_source_digest"]
            or revision_receipt != baseline["revision_receipt"]
            or sha256(html).hexdigest() != baseline["revised_html_sha256"]):
        raise StudioQuestError("remap proposal revision replay drift")
    candidates: list[dict[str, str]] = []
    old_stages = {stage.key: stage for stage in old.stages}
    new_stages = {stage.key: stage for stage in new.stages}
    for stage_id, choice in baseline["authoring"]["actions"]:
        before = old_stages[stage_id]
        after = new_stages[stage_id]
        position = before.alternatives.index(choice)
        updated = after.alternatives[position]
        if updated != choice:
            candidates.append({
                "stage_id": stage_id,
                "from_choice": choice,
                "to_choice": updated,
            })
    if len(candidates) > MAX_REMAPS:
        raise StudioQuestError("remap proposal candidate budget exceeded")
    if _canonical(documents) != original:
        raise StudioQuestError("remap proposal source changed during compile")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": old.project_id,
        "old_quest_source_digest": old.source_digest,
        "new_quest_source_digest": new.source_digest,
        "initial_session_digest": baseline["initial_session_digest"],
        "old_session_digest": baseline["old_session_digest"],
        "revision_receipt_digest": revision_receipt["receipt_digest"],
        "baseline_migration_digest": baseline["migration_digest"],
        "authoring": {
            "revision_request": baseline["authoring"]["revision_request"],
            "actions": baseline["authoring"]["actions"],
            "target_ending": baseline["authoring"]["target_ending"],
        },
        "candidate_remaps": candidates,
        "candidate_count": len(candidates),
        "status": "approval_required" if candidates else "no_remaps_required",
        "requires_explicit_operator_approval": True,
        "playable_handoff_allowed": False,
        "canonical_old_replay_verified": True,
        "canonical_revised_replay_verified": True,
        "native_gameplay_verified": False,
        "external_authorship_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("remap proposal receipt exceeds byte budget")
    result["proposal_digest"] = _digest(result)
    return result


def replay_quest_remap_proposal(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("remap proposal replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid remap proposal receipt")
    checked = compile_quest_remap_proposal(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("old_quest_source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("remap proposal differs from canonical replay")
    return checked


def approve_quest_remap_proposal(
    documents: Mapping[str, Any], proposal: object, approved: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Require complete explicit remap approval, then compile real migration."""
    if authorized is not True:
        raise PermissionError("quest remap approval requires operator authority")
    _lease(expected_source_digest, "remap approval source")
    _lease(expected_initial_session_digest, "remap approval session")
    checked = replay_quest_remap_proposal(documents, proposal, authorized=True)
    if (checked["old_quest_source_digest"] != expected_source_digest
            or checked["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale remap approval source or session")
    if (type(approved) is not dict
            or set(approved) != {"schema", "proposal_digest", "remaps"}
            or approved.get("schema") != EXPORT_SCHEMA
            or approved.get("proposal_digest") != checked["proposal_digest"]
            or len(_canonical(approved)) > 32768):
        raise StudioQuestError("invalid or stale typed remap approval")
    remaps = approved["remaps"]
    if (type(remaps) is not list or len(remaps) != checked["candidate_count"]
            or any(type(item) is not dict or
                   set(item) != {"stage_id", "from_choice", "to_choice"}
                   for item in remaps)):
        raise StudioQuestError("incomplete or malformed explicit remap approval")
    expected = {item["stage_id"]: item for item in checked["candidate_remaps"]}
    actual: dict[str, dict[str, str]] = {}
    for item in remaps:
        key = item["stage_id"]
        if type(key) is not str or key in actual or key not in expected:
            raise StudioQuestError("duplicate or unexpected remap approval")
        if item != expected[key]:
            raise StudioQuestError("remap approval differs from source proposal")
        actual[key] = item
    if set(actual) != set(expected):
        raise StudioQuestError("partial remap approval is forbidden")
    authoring = dict(checked["authoring"])
    authoring["remaps"] = [actual[key] for key in sorted(actual)]
    migration = compile_quest_revision_migration(
        documents, authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
    if (migration["first_unmigrated_index"] is not None
            or migration["new_quest_source_digest"] != checked["new_quest_source_digest"]
            or migration["old_session_digest"] != checked["old_session_digest"]):
        raise StudioQuestError("approved migration did not replay fully")
    return replay_quest_revision_migration(documents, migration, authorized=True)


def propose_quest_remaps(
    documents: Mapping[str, Any], prompt: str, authoring: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported quest remap proposal prompt")
    return compile_quest_remap_proposal(
        documents, authoring, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)


_SCRIPT = """(() => {
  'use strict';
  const get = id => document.getElementById(id);
  get('export').addEventListener('click', () => {
    try {
      const remaps = JSON.parse(get('remaps').value);
      if (!Array.isArray(remaps) || remaps.length > 64) throw Error('bounds');
      const expected = JSON.parse(get('expected').textContent);
      if (JSON.stringify(remaps) !== JSON.stringify(expected))
        throw Error('review must preserve exact source-proposed mapping');
      const payload = {
        schema: get('schema').value,
        proposal_digest: get('digest').value,
        remaps: remaps
      };
      const raw = JSON.stringify(payload);
      if (new TextEncoder().encode(raw).length > 32768) throw Error('bounds');
      const url = URL.createObjectURL(new Blob([raw], {type:'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-remap-approval.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      get('status').textContent = 'Exported only; CLI operator approval and canonical replay required.';
    } catch (_) {
      get('status').textContent = 'Invalid remap selection; nothing exported.';
    }
  });
})();"""


def render_quest_remap_review_html(
    documents: Mapping[str, Any], proposal: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_remap_proposal(documents, proposal, authorized=authorized)
    candidates = json.dumps(checked["candidate_remaps"], indent=2,
                            sort_keys=True, ensure_ascii=True)
    expected = json.dumps(checked["candidate_remaps"], separators=(",", ":"),
                          ensure_ascii=True)
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    def hidden(key: str, value: str) -> str:
        return '<input id="' + key + '" type="hidden" value="' + escape(value, quote=True) + '">'
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Quest choice remap review</title></head><body><main>'
        '<h1>Review authored quest choice remaps</h1>'
        '<p>Every proposed remap must be explicitly approved. '
        'Export does not authorize publication or native gameplay.</p>'
        + hidden("schema", EXPORT_SCHEMA)
        + hidden("digest", checked["proposal_digest"])
        + '<label for="remaps">Source-derived remap candidates</label>'
        '<textarea id="remaps" rows="20" cols="100">' +
        escape(candidates, quote=True) + '</textarea>'
        '<script type="application/json" id="expected">' +
        expected.replace("&", "\\u0026").replace("<", "\\u003c") +
        '</script>'
        '<button id="export" type="button">Export for explicit CLI approval</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<p>Canonical replay, operator authority, and release gates are still required.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("remap review HTML exceeds byte budget")
    return html
