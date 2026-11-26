"""Source-leased causal witness traces for two original authored quest histories.

This is a deterministic *sandbox* explanation, not a proof of real-world
evidence, native gameplay, or player-observed causation. Every witness is
derived from an explicitly authored stage, reward, or choice-effect token.
"""
from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _open_directory, _write_all,
)
from .studio_quest_consequence_diff import (
    compile_quest_consequence_diff, compile_quest_consequence_handoff,
    replay_quest_consequence_diff,
)

SCHEMA = "skeleton.game_builder.studio_quest_causal_trace.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_causal_handoff.v1"
FILENAME = "studio_quest_causal_trace.json"
MAX_BYTES = 256 * 1024


def _facts_and_witnesses(program: object, actions: list[list[str]]) -> dict[str, list[dict[str, object]]]:
    """Record each actual producer, never infer unobserved world predicates."""
    stages = {stage.key: stage for stage in program.stages}
    result: dict[str, list[dict[str, object]]] = {}
    for index, (stage_id, choice) in enumerate(actions):
        stage = stages[stage_id]  # Canonical replay validated the stage and choice.
        for fact, origin in ((stage_id, "completed_stage"),
                             (stage.reward, "authored_reward"),
                             *((token, "authored_choice_effect")
                               for token in dict(stage.choice_effects).get(choice, ()))):
            result.setdefault(fact, []).append({
                "action_index": index, "stage_id": stage_id,
                "alternative": choice, "origin": origin,
            })
    return {key: result[key] for key in sorted(result)}


def _branch_trace(documents: Mapping[str, Any], program: object,
                  actions: list[list[str]]) -> dict[str, object]:
    previous_facts: set[str] = set()
    previous_endings: set[str] = set()
    rows: list[dict[str, object]] = []
    for index in range(len(actions)):
        prefix = actions[:index + 1]
        session = replay_quest(documents, prefix, authorized=True)
        progress = quest_progress(session, documents)
        facts = set(_facts_and_witnesses(program, prefix))
        endings = set(progress["sandbox_endings_eligible"])
        rows.append({
            "action_index": index,
            "stage_id": actions[index][0],
            "alternative": actions[index][1],
            "session_digest": session.digest,
            "facts_added": sorted(facts - previous_facts),
            "endings_unlocked": sorted(endings - previous_endings),
            "available_after": progress["available"],
            "unmet_ending_predicates": progress["unmet_ending_predicates"],
        })
        previous_facts, previous_endings = facts, endings
    final = replay_quest(documents, actions, authorized=True)
    progress = quest_progress(final, documents)
    return {
        "actions": actions,
        "session_digest": final.digest,
        "steps": rows,
        "facts": sorted(previous_facts),
        "endings": progress["sandbox_endings_eligible"],
        "available": progress["available"],
        "witnesses": _facts_and_witnesses(program, actions),
    }


def compile_quest_causal_trace(
    documents: Mapping[str, Any], consequence_receipt: object, *,
    authorized: bool,
) -> dict[str, Any]:
    """Explain every predicate and step with source-anchored replay witnesses."""
    if authorized is not True:
        raise PermissionError("quest causal trace requires authorization")
    checked = replay_quest_consequence_diff(
        documents, consequence_receipt, authorized=True)
    program = compile_quest_program(documents)
    if checked["source_digest"] != program.source_digest:
        raise StudioQuestError("causal trace source lease changed")
    before = _canonical(documents)
    left = _branch_trace(documents, program, checked["authoring"]["baseline_actions"])
    right = _branch_trace(documents, program, checked["authoring"]["candidate_actions"])
    if (_canonical(documents) != before
            or left["session_digest"] != checked["baseline_session_digest"]
            or right["session_digest"] != checked["candidate_session_digest"]):
        raise StudioQuestError("causal trace canonical replay drift")
    prefix = checked["first_divergence_index"]
    if (left["actions"][:prefix] != right["actions"][:prefix]
            or (prefix < min(len(left["actions"]), len(right["actions"]))
                and left["actions"][prefix] == right["actions"][prefix])):
        raise StudioQuestError("invalid causal divergence boundary")
    for index in range(prefix):
        if left["steps"][index]["session_digest"] != right["steps"][index]["session_digest"]:
            raise StudioQuestError("shared causal prefix changed")
    endings: list[dict[str, object]] = []
    for ending_id, requirements in program.endings:
        left_missing = sorted(set(requirements) - set(left["facts"]))
        right_missing = sorted(set(requirements) - set(right["facts"]))
        endings.append({
            "ending_id": ending_id,
            "authored_requirements": list(requirements),
            "baseline_eligible": not left_missing,
            "candidate_eligible": not right_missing,
            "baseline_missing": left_missing,
            "candidate_missing": right_missing,
            "baseline_witnesses": {
                token: left["witnesses"][token]
                for token in requirements if token in left["witnesses"]
            },
            "candidate_witnesses": {
                token: right["witnesses"][token]
                for token in requirements if token in right["witnesses"]
            },
        })
    baseline = sorted(x["ending_id"] for x in endings if x["baseline_eligible"])
    candidate = sorted(x["ending_id"] for x in endings if x["candidate_eligible"])
    if (sorted(checked["baseline_progress"]["sandbox_endings_eligible"]) != baseline
            or sorted(checked["candidate_progress"]["sandbox_endings_eligible"]) != candidate):
        raise StudioQuestError("causal ending proof diverges from consequence receipt")
    trace: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "consequence_receipt_digest": checked["receipt_digest"],
        "initial_session_digest": checked["initial_session_digest"],
        "first_divergence_index": prefix,
        "shared_prefix_session_digest": (
            left["steps"][prefix - 1]["session_digest"]
            if prefix else checked["initial_session_digest"]
        ),
        "baseline": left, "candidate": right,
        "ending_predicate_proofs": endings,
        "ending_delta": checked["ending_delta"],
        "canonical_quest_replay_verified": True,
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(trace)) > MAX_BYTES - 128:
        raise StudioQuestError("causal trace exceeds bounded receipt size")
    trace["receipt_digest"] = _digest(trace)
    return trace


def replay_quest_causal_trace(
    documents: Mapping[str, Any], consequence_receipt: object,
    trace_receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("causal trace replay requires authorization")
    if type(trace_receipt) is not dict or trace_receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid causal trace receipt")
    verified = compile_quest_causal_trace(
        documents, consequence_receipt, authorized=True)
    if _canonical(verified) != _canonical(trace_receipt):
        raise StudioQuestError("causal trace receipt failed replay")
    return verified


def compile_quest_causal_handoff(
    documents: Mapping[str, Any], consequence_receipt: object,
    trace_receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_causal_trace(
        documents, consequence_receipt, trace_receipt, authorized=authorized)
    handoff = compile_quest_consequence_handoff(
        documents, consequence_receipt, authorized=True)
    result: dict[str, Any] = {
        "schema": HANDOFF_SCHEMA,
        "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "causal_trace_digest": checked["receipt_digest"],
        "consequence_handoff_digest": handoff["handoff_digest"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "external_evidence_verified": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def render_quest_causal_html(
    documents: Mapping[str, Any], consequence_receipt: object,
    trace_receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_causal_trace(
        documents, consequence_receipt, trace_receipt, authorized=authorized)
    def safe(value: object) -> str:
        return escape(str(value), quote=True)
    items = []
    for row in checked["ending_predicate_proofs"]:
        predicate_rows = []
        for token in row["authored_requirements"]:
            origins = []
            for branch in ("baseline", "candidate"):
                witnesses = row[branch + "_witnesses"].get(token, [])
                for witness in witnesses:
                    origins.append(
                        "<li>" + safe(branch) + ": stage "
                        + safe(witness["stage_id"]) + ", choice "
                        + safe(witness["alternative"]) + ", action "
                        + safe(witness["action_index"]) + ", origin "
                        + safe(witness["origin"]) + "</li>"
                    )
            predicate_rows.append(
                "<li><strong>" + safe(token) + "</strong>"
                + ("<ul>" + "".join(origins) + "</ul>" if origins
                   else " (unmet in both branches)") + "</li>"
            )
        items.append(
            "<section><h2>" + safe(row["ending_id"]) + "</h2><p>"
            "Baseline eligible: " + safe(row["baseline_eligible"])
            + "; candidate eligible: " + safe(row["candidate_eligible"])
            + "</p><ul>" + "".join(predicate_rows)
            + "</ul><p>Baseline missing: "
            + safe(", ".join(row["baseline_missing"]))
            + "; candidate missing: "
            + safe(", ".join(row["candidate_missing"])) + "</p></section>"
        )
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src "
        "'none'; script-src 'none'; style-src 'none'; form-action 'none'; "
        "base-uri 'none'\"><title>Quest causal witnesses</title></head><body>"
        "<main><h1>Original quest causal witness audit</h1>"
        "<p>Source-leased sandbox replay only. Native gameplay, external "
        "evidence and release qualification are not verified.</p>"
        + "".join(items) + "</main></body></html>"
    ).encode("utf-8")
    if len(html) > 64 * 1024:
        raise StudioQuestError("causal witness HTML exceeds byte budget")
    return html


def publish_quest_causal_trace(
    documents: Mapping[str, Any], consequence_receipt: object,
    trace_receipt: object, directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_causal_trace(
        documents, consequence_receipt, trace_receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("causal publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".causal-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        try:
            os.fsync(fd)
        except OSError:
            os.unlink(FILENAME, dir_fd=fd)
            raise
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"file": FILENAME, "receipt_digest": checked["receipt_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_quest_causal_trace(
    documents: Mapping[str, Any], consequence_receipt: object | None,
    directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("causal trace restore requires authorization")
    fd = _open_directory(directory)
    try:
        inp = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                      dir_fd=fd)
        try:
            before = os.fstat(inp)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_BYTES
                    or (os.name == "posix" and
                        (before.st_uid != os.getuid() or before.st_mode & 0o077
                         or before.st_nlink != 1))):
                raise StudioQuestError("causal trace receipt must be private")
            raw = os.read(inp, MAX_BYTES + 1)
            after = os.fstat(inp)
            if (len(raw) != before.st_size
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_ino) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                     before.st_ino)):
                raise StudioQuestError("causal trace receipt changed during read")
        finally:
            os.close(inp)
    finally:
        os.close(fd)
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate causal trace JSON key")
            result[key] = value
        return result
    try:
        parsed = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite causal trace JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid causal trace JSON") from exc
    if (type(parsed) is not dict or type(parsed.get("baseline")) is not dict
            or type(parsed.get("candidate")) is not dict):
        raise StudioQuestError("invalid causal trace bundle shape")
    if consequence_receipt is None:
        # Rebuild the canonical consequence receipt from the single durable
        # causal bundle. Never trust its embedded session or release flags.
        consequence_receipt = compile_quest_consequence_diff(
            documents, {
                "baseline_actions": parsed["baseline"].get("actions"),
                "candidate_actions": parsed["candidate"].get("actions"),
            }, authorized=True,
            expected_source_digest=parsed.get("source_digest"),
            expected_initial_session_digest=parsed.get("initial_session_digest"),
        )
    return replay_quest_causal_trace(
        documents, consequence_receipt, parsed, authorized=True)
