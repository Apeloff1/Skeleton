"""Source-bound causal explanation of original quest endings.

This is a deterministic *authored* cause trace, not an assertion of player
telemetry, native gameplay, factual evidence, or external-world causality.
Every reported token is earned by canonical quest replay; missing predicates
remain missing. No AI output is permitted to invent a fact or award an ending.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_catalog import compile_preview
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
    start_quest, step_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json

SCHEMA = "skeleton.game_builder.studio_quest_cause_trace.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_cause_plan.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_cause_handoff.v1"
PROMPT = "explain exactly which authored choices made my quest endings eligible"
FILENAME = "studio_quest_cause_trace.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_PLAN_BYTES = 48 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
MAX_HTML_BYTES = 128 * 1024
MAX_ACTIONS = 64


def _validate_actions(actions: object) -> list[list[str]]:
    if (type(actions) is not list or len(actions) > MAX_ACTIONS
            or any(type(pair) is not list or len(pair) != 2
                   or any(type(part) is not str for part in pair)
                   for pair in actions)):
        raise StudioQuestError("invalid bounded causal action history")
    return actions


def propose_quest_cause_trace(
    documents: Mapping[str, Any], prompt: str, actions: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Return an editable typed review plan, never an automatically approved proof."""
    if authorized is not True:
        raise PermissionError("quest causal proposal requires operator authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported quest causal explanation prompt")
    _lease(expected_source_digest, "causal proposal source")
    _lease(expected_initial_session_digest, "causal proposal session")
    if len(_canonical(documents)) > MAX_SOURCE_BYTES:
        raise StudioQuestError("causal proposal source exceeds budget")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    if (program.source_digest != expected_source_digest
            or initial.digest != expected_initial_session_digest):
        raise StudioQuestError("stale causal proposal source or session")
    actions = _validate_actions(actions)
    final = replay_quest(documents, actions, authorized=True)
    plan = {
        "schema": PLAN_SCHEMA,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "final_session_digest": final.digest,
        "actions": [list(pair) for pair in final.choices],
        "target_endings": [name for name, _ in program.endings],
        "reviewed": False,
    }
    if len(_canonical(plan)) > MAX_PLAN_BYTES:
        raise StudioQuestError("causal plan exceeds budget")
    return plan


def _validate_plan(plan: object, program: Any, initial: Any, final: Any) -> dict[str, Any]:
    if (type(plan) is not dict
            or set(plan) != {
                "schema", "source_digest", "initial_session_digest",
                "final_session_digest", "actions", "target_endings", "reviewed"}
            or len(_canonical(plan)) > MAX_PLAN_BYTES
            or plan["schema"] != PLAN_SCHEMA
            or plan["source_digest"] != program.source_digest
            or plan["initial_session_digest"] != initial.digest
            or plan["final_session_digest"] != final.digest
            or plan["actions"] != [list(pair) for pair in final.choices]
            or type(plan["reviewed"]) is not bool
            or plan["reviewed"] is not True):
        raise StudioQuestError("unreviewed or stale causal plan")
    targets = plan["target_endings"]
    known = {name for name, _ in program.endings}
    if (type(targets) is not list or not 1 <= len(targets) <= 16
            or any(type(name) is not str or name not in known for name in targets)
            or len(set(targets)) != len(targets)):
        raise StudioQuestError("invalid or duplicate target endings")
    return {
        "schema": PLAN_SCHEMA,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "final_session_digest": final.digest,
        "actions": [list(pair) for pair in final.choices],
        "target_endings": list(targets),
        "reviewed": True,
    }


def compile_quest_cause_trace(
    documents: Mapping[str, Any], plan: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Explain each ending predicate using exact action/reward provenance."""
    if authorized is not True:
        raise PermissionError("quest causal compile requires operator authorization")
    _lease(expected_source_digest, "causal compile source")
    _lease(expected_initial_session_digest, "causal compile session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("causal source exceeds budget")
    if type(plan) is not dict:
        raise StudioQuestError("invalid typed causal plan")
    actions = _validate_actions(plan.get("actions"))
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    if (program.source_digest != expected_source_digest
            or initial.digest != expected_initial_session_digest):
        raise StudioQuestError("stale causal compile lease")
    final = replay_quest(documents, actions, authorized=True)
    checked = _validate_plan(plan, program, initial, final)
    by_stage = {stage.key: stage for stage in program.stages}
    origin: dict[str, dict[str, Any]] = {}
    frames: list[dict[str, Any]] = []
    current = initial
    for index, (stage_id, alternative) in enumerate(final.choices):
        stage = by_stage[stage_id]
        prior = current
        current = step_quest(current, documents, stage=stage_id,
                             alternative=alternative, authorized=True)
        tokens = [stage_id, stage.reward]
        tokens.extend(dict(stage.choice_effects).get(alternative, ()))
        # A duplicate reward may be earned more than once; retain the first
        # source witness, while recording every action's actual contribution.
        for token in tokens:
            origin.setdefault(token, {
                "action_index": index, "stage_id": stage_id,
                "alternative": alternative, "session_digest": current.digest,
            })
        frames.append({
            "action_index": index, "stage_id": stage_id,
            "alternative": alternative,
            "prerequisites": list(stage.prerequisites),
            "previous_session_digest": prior.digest,
            "session_digest": current.digest,
            "earned_tokens": tokens,
        })
    if current != final:
        raise StudioQuestError("causal replay diverged from final quest state")
    progress = quest_progress(final, documents)
    eligibility = set(progress["sandbox_endings_eligible"])
    requirements = dict(program.endings)
    explanations: list[dict[str, Any]] = []
    for name in checked["target_endings"]:
        predicates = list(requirements[name])
        causes = [
            {"predicate": token, "earned": token in origin,
             "origin": origin.get(token)}
            for token in predicates
        ]
        missing = [row["predicate"] for row in causes if not row["earned"]]
        eligible = name in eligibility
        if eligible != (not missing):
            raise StudioQuestError("causal trace contradicts canonical ending eligibility")
        explanations.append({
            "ending_id": name, "eligible": eligible,
            "predicates": causes, "missing_predicates": missing,
        })
    if _canonical(documents) != before:
        raise StudioQuestError("causal source mutated during compile")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "final_session_digest": final.digest,
        "plan": checked, "frames": frames,
        "ending_explanations": explanations,
        "status": "all_targets_eligible" if all(
            row["eligible"] for row in explanations) else "unmet_authored_predicates",
        "canonical_quest_replay_verified": True,
        "authored_predicate_provenance_verified": True,
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("causal trace receipt exceeds budget")
    result["trace_digest"] = _digest(result)
    return result


def replay_quest_cause_trace(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("causal trace replay requires operator authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid causal trace receipt")
    verified = compile_quest_cause_trace(
        documents, receipt.get("plan"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(verified) != _canonical(receipt):
        raise StudioQuestError("causal trace receipt failed source replay")
    return verified


def compile_quest_cause_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_quest_cause_trace(documents, receipt, authorized=authorized)
    # A causal explanation is not evidence that an ending is reachable or
    # that an engine implements the choice. Never mint eligibility.
    if verified["status"] != "all_targets_eligible":
        raise StudioQuestError("unearned authored ending blocks causal handoff")
    final = replay_quest(documents, verified["plan"]["actions"], authorized=True)
    if final.digest != verified["final_session_digest"]:
        raise StudioQuestError("causal handoff session changed")
    compiled = compile_preview(verified["project_id"], authorized=True)
    game_html = compiled.playable.html.encode("utf-8", "strict")
    game_receipt = compiled.receipt()
    if (game_receipt.get("project_id") != verified["project_id"]
            or game_receipt.get("validated_gameplay_proof") is not True
            or sha256(game_html).hexdigest() != game_receipt.get("html_sha256")):
        raise StudioQuestError("quest cause handoff playable compiler proof mismatch")
    handoff: dict[str, Any] = {
        "schema": HANDOFF_SCHEMA,
        "project_id": verified["project_id"],
        "quest_source_digest": verified["source_digest"],
        "quest_session_digest": final.digest,
        "cause_trace_digest": verified["trace_digest"],
        "game_html_sha256": sha256(game_html).hexdigest(),
        "canonical_html5_quest_included": True,
        "playable_compiler_proof_verified": True,
        "eligible_endings": [row["ending_id"] for row in verified["ending_explanations"]],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    handoff["handoff_digest"] = _digest(handoff)
    return handoff


def render_quest_cause_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    verified = replay_quest_cause_trace(documents, receipt, authorized=authorized)
    items = []
    for row in verified["ending_explanations"]:
        details = "".join(
            "<li>" + escape(cause["predicate"], quote=True)
            + (" — earned" if cause["earned"] else " — missing") + "</li>"
            for cause in row["predicates"])
        items.append("<li><h2>" + escape(row["ending_id"], quote=True)
                     + "</h2><p>" + ("Eligible" if row["eligible"] else "Blocked")
                     + "</p><ul>" + details + "</ul></li>")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'none'; style-src 'none'; connect-src 'none'; "
        'form-action \'none\'; base-uri \'none\'">'
        '<title>Original quest cause trace</title></head><body><main>'
        '<h1>Authored quest cause trace</h1><ol>' + "".join(items)
        + '</ol><p>Source replay only; no external or native gameplay proof.</p>'
        '</main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("causal HTML exceeds budget")
    return html


def publish_quest_cause_trace(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    verified = replay_quest_cause_trace(documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("causal publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".quest-cause-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {"file": FILENAME, "trace_digest": verified["trace_digest"],
            "file_write_performed": True, "release_certified": False}


def restore_quest_cause_trace(
    documents: Mapping[str, Any], directory: Path, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("causal restore requires operator authorization")
    _lease(expected_source_digest, "causal restore source")
    receipt = read_studio_private_json(Path(directory) / FILENAME,
                                       MAX_RECEIPT_BYTES)
    if receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale causal trace source lease")
    return replay_quest_cause_trace(documents, receipt, authorized=True)
