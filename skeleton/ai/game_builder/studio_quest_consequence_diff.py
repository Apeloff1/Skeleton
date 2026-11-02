"""Canonical, source-leased counterfactual replay of authored quest choices."""
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
    start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)

SCHEMA = "skeleton.game_builder.studio_quest_consequence_diff.v1"
PROMPT = "compare the consequences of two authored quest choice histories"
FILENAME = "studio_quest_consequence_diff.json"
MAX_RECEIPT_BYTES = 256 * 1024


def _actions(value: object) -> list[list[str]]:
    if type(value) is not list or len(value) > 64:
        raise StudioQuestError("invalid bounded consequence actions")
    checked = []
    for pair in value:
        if (type(pair) is not list or len(pair) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256
                       or x != x.strip() or any(ord(c) < 32 for c in x)
                       for x in pair)):
            raise StudioQuestError("invalid typed consequence action")
        checked.append(pair.copy())
    return checked


def _authoring(value: object) -> dict[str, list[list[str]]]:
    if (type(value) is not dict
            or set(value) != {"baseline_actions", "candidate_actions"}
            or len(_canonical(value)) > 32768):
        raise StudioQuestError("invalid typed consequence authoring")
    left, right = _actions(value["baseline_actions"]), _actions(value["candidate_actions"])
    if left == right:
        raise StudioQuestError("counterfactual histories must differ")
    return {"baseline_actions": left, "candidate_actions": right}


def _facts(program: object, actions: list[list[str]]) -> list[str]:
    by_id = {stage.key: stage for stage in program.stages}
    result: set[str] = set()
    for stage_id, choice in actions:
        stage = by_id[stage_id]
        result.update((stage_id, stage.reward))
        result.update(dict(stage.choice_effects).get(choice, ()))
    return sorted(result)


def _delta(left: list[str], right: list[str]) -> dict[str, list[str]]:
    before, after = set(left), set(right)
    return {"lost": sorted(before - after), "gained": sorted(after - before),
            "retained": sorted(before & after)}


def compile_quest_consequence_diff(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Replay two original histories and compare facts, endings and unlocks."""
    if authorized is not True:
        raise PermissionError("quest consequence comparison requires authorization")
    _lease(expected_source_digest, "consequence source")
    _lease(expected_initial_session_digest, "consequence initial session")
    before = _canonical(documents)
    if len(before) > 256 * 1024:
        raise StudioQuestError("consequence source exceeds byte budget")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    if (program.source_digest != expected_source_digest
            or initial.digest != expected_initial_session_digest):
        raise StudioQuestError("stale consequence source or session lease")
    plan = _authoring(authoring)
    left = replay_quest(documents, plan["baseline_actions"], authorized=True)
    right = replay_quest(documents, plan["candidate_actions"], authorized=True)
    lp, rp = quest_progress(left, documents), quest_progress(right, documents)
    if (_canonical(documents) != before
            or lp["session_digest"] != left.digest
            or rp["session_digest"] != right.digest):
        raise StudioQuestError("consequence source or session drift")
    divergence = next(
        (i for i in range(min(len(plan["baseline_actions"]), len(plan["candidate_actions"])))
         if plan["baseline_actions"][i] != plan["candidate_actions"][i]),
        min(len(plan["baseline_actions"]), len(plan["candidate_actions"])),
    )
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "initial_session_digest": initial.digest, "authoring": plan,
        "baseline_session_digest": left.digest, "candidate_session_digest": right.digest,
        "first_divergence_index": divergence,
        "baseline_progress": lp, "candidate_progress": rp,
        "facts_delta": _delta(_facts(program, plan["baseline_actions"]),
                              _facts(program, plan["candidate_actions"])),
        "completed_stage_delta": _delta(list(left.completed), list(right.completed)),
        "available_stage_delta": _delta(lp["available"], rp["available"]),
        "ending_delta": _delta(lp["sandbox_endings_eligible"],
                               rp["sandbox_endings_eligible"]),
        "both_branches_have_authored_ending": bool(
            lp["sandbox_endings_eligible"] and rp["sandbox_endings_eligible"]),
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "external_evidence_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("consequence receipt exceeds byte budget")
    result["receipt_digest"] = _digest(result)
    return result


def propose_quest_consequence_diff(
    documents: Mapping[str, Any], prompt: str, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported consequence comparison prompt")
    program = compile_quest_program(documents)
    roots = [s for s in program.stages if not s.prerequisites and len(s.alternatives) >= 2]
    if not roots:
        raise StudioQuestError("no authored root choice fork")
    stage = roots[0]
    return compile_quest_consequence_diff(
        documents, {
            "baseline_actions": [[stage.key, stage.alternatives[0]]],
            "candidate_actions": [[stage.key, stage.alternatives[1]]],
        }, authorized=authorized, expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest,
    )


def replay_quest_consequence_diff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest consequence replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid consequence receipt")
    checked = compile_quest_consequence_diff(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"),
    )
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("consequence receipt failed canonical replay")
    return checked


def compile_quest_consequence_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_consequence_diff(documents, receipt, authorized=authorized)
    if checked["both_branches_have_authored_ending"] is not True:
        raise StudioQuestError("both branches require authored ending eligibility")
    handoff: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_consequence_handoff.v1",
        "project_id": checked["project_id"], "source_digest": checked["source_digest"],
        "consequence_receipt_digest": checked["receipt_digest"],
        "baseline_session_digest": checked["baseline_session_digest"],
        "candidate_session_digest": checked["candidate_session_digest"],
        "ending_delta": checked["ending_delta"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "release_certified": False,
    }
    handoff["handoff_digest"] = _digest(handoff)
    return handoff


def render_quest_consequence_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_consequence_diff(documents, receipt, authorized=authorized)
    def items(values: list[str]) -> str:
        return "".join("<li>" + escape(x, quote=True) + "</li>" for x in values)
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'none'; style-src 'none'; form-action 'none'; "
        'base-uri \'none\'"><title>Quest consequences</title></head><body>'
        '<main><h1>Canonical quest choice consequences</h1><p>Divergence index: '
        + str(checked["first_divergence_index"]) + '</p>'
        '<h2>Lost endings</h2><ul>' + items(checked["ending_delta"]["lost"])
        + '</ul><h2>Gained endings</h2><ul>'
        + items(checked["ending_delta"]["gained"]) + '</ul>'
        '<h2>Lost facts</h2><ul>' + items(checked["facts_delta"]["lost"])
        + '</ul><h2>Gained facts</h2><ul>'
        + items(checked["facts_delta"]["gained"]) + '</ul>'
        '<p>Sandbox replay only. Native gameplay and release are unverified.</p>'
        '</main></body></html>'
    ).encode("utf-8")
    if len(html) > 64 * 1024:
        raise StudioQuestError("consequence HTML exceeds byte budget")
    return html


def publish_quest_consequence_diff(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_consequence_diff(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("consequence publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".consequence-" + secrets.token_hex(16) + ".tmp"
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


def restore_quest_consequence_diff(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest consequence restore requires authorization")
    _lease(expected_source_digest, "consequence restore source")
    fd = _open_directory(directory)
    try:
        inp = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                      dir_fd=fd)
        try:
            before = os.fstat(inp)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_RECEIPT_BYTES
                    or (os.name == "posix" and
                        (before.st_uid != os.getuid() or before.st_mode & 0o077
                         or before.st_nlink != 1))):
                raise StudioQuestError("consequence receipt must be private")
            raw = os.read(inp, MAX_RECEIPT_BYTES + 1)
            after = os.fstat(inp)
            if (len(raw) != before.st_size
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_ino) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                     before.st_ino)):
                raise StudioQuestError("consequence receipt changed during read")
        finally:
            os.close(inp)
    finally:
        os.close(fd)
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate consequence JSON key")
            result[key] = value
        return result
    try:
        parsed = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite consequence JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid consequence receipt JSON") from exc
    if type(parsed) is not dict or parsed.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale or malformed consequence evidence")
    return replay_quest_consequence_diff(documents, parsed, authorized=True)
