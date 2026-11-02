"""Canonical per-ending quest reachability witnesses, never native certification."""
from __future__ import annotations
from collections import deque
from html import escape
from pathlib import Path
import json
import os
import secrets
import stat
from typing import Any, Mapping
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_softlock_audit import _authoring

SCHEMA = "skeleton.game_builder.studio_quest_ending_coverage.v1"
PROMPT = "prove every selected authored quest ending has a canonical replay witness"
FILENAME = "studio_quest_ending_coverage.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 512 * 1024
MAX_QUEUE = 4096


def compile_ending_coverage(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Prove each ending independently, with bounded replay and explicit unknown."""
    if authorized is not True:
        raise PermissionError("ending coverage requires operator authorization")
    _lease(expected_source_digest, "ending coverage source")
    _lease(expected_initial_session_digest, "ending coverage session")
    source = _canonical(documents)
    if len(source) > MAX_SOURCE_BYTES:
        raise StudioQuestError("ending coverage source exceeds byte budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale ending coverage source lease")
    plan = _authoring(authoring, {name for name, _ in program.endings})
    initial = replay_quest(documents, plan["initial_actions"], authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale ending coverage session lease")
    targets = set(plan["target_endings"])
    by_stage = {stage.key: stage for stage in program.stages}
    queue: deque[list[list[str]]] = deque([plan["initial_actions"]])
    seen: set[tuple[tuple[str, str], ...]] = set()
    witnesses: dict[str, dict[str, Any]] = {}
    expanded = 0
    truncated = False
    while queue:
        if expanded >= plan["max_states"]:
            truncated = True
            break
        actions = queue.popleft()
        session = replay_quest(documents, actions, authorized=True)
        # Choice effects and completed prerequisites depend on the set of
        # completed stage/choice pairs, not their legal chronological order.
        identity = tuple(sorted(session.choices))
        if identity in seen:
            continue
        seen.add(identity)
        progress = quest_progress(session, documents)
        expanded += 1
        for ending in sorted(targets.intersection(
            progress["sandbox_endings_eligible"]
        )):
            witnesses.setdefault(ending, {
                "ending_id": ending, "actions": [list(pair) for pair in actions],
                "session_digest": session.digest,
            })
        if len(witnesses) == len(targets):
            break
        if len(actions) >= plan["max_depth"]:
            if progress["available"]:
                truncated = True
            continue
        for stage_id in progress["available"]:
            for choice in by_stage[stage_id].alternatives:
                if len(queue) >= MAX_QUEUE:
                    truncated = True
                    break
                queue.append(actions + [[stage_id, choice]])
            if truncated:
                break
        if truncated:
            break
    if _canonical(documents) != source:
        raise StudioQuestError("ending coverage source changed during replay")
    missing = sorted(targets.difference(witnesses))
    exhaustive = not truncated and not queue
    status = ("all_targets_witnessed" if not missing else
              "unreachable_in_exhaustive_search" if exhaustive else
              "inconclusive_budget_exhausted")
    payload: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest, "authoring": plan,
        "status": status,
        "witnesses": [witnesses[name] for name in sorted(witnesses)],
        "uncovered_endings": missing,
        "coverage_complete": not missing,
        "search_exhaustive": exhaustive,
        "expanded_states": expanded,
        "playable_handoff_allowed": not missing,
        "source_replay_verified": True,
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("ending coverage receipt exceeds byte budget")
    payload["coverage_digest"] = _digest(payload)
    return payload


def propose_ending_coverage(
    documents: Mapping[str, Any], prompt: str, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported ending coverage prompt")
    program = compile_quest_program(documents)
    if len(program.endings) > 16:
        raise StudioQuestError("too many authored endings for bounded proof")
    return compile_ending_coverage(
        documents, {"initial_actions": [],
                    "target_endings": [name for name, _ in program.endings],
                    "max_states": 1024,
                    "max_depth": min(64, len(program.stages))},
        authorized=authorized, expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)


def replay_ending_coverage(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("ending coverage replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid ending coverage receipt")
    verified = compile_ending_coverage(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(verified) != _canonical(receipt):
        raise StudioQuestError("ending coverage receipt differs from source replay")
    return verified


def compile_ending_coverage_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_ending_coverage(documents, receipt, authorized=authorized)
    if not verified["playable_handoff_allowed"]:
        raise StudioQuestError("unproved ending coverage blocks playable handoff")
    for witness in verified["witnesses"]:
        session = replay_quest(documents, witness["actions"], authorized=True)
        if (session.digest != witness["session_digest"]
                or witness["ending_id"] not in
                quest_progress(session, documents)["sandbox_endings_eligible"]):
            raise StudioQuestError("ending coverage handoff witness drift")
    result: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_ending_coverage_handoff.v1",
        "project_id": verified["project_id"],
        "quest_source_digest": verified["source_digest"],
        "coverage_digest": verified["coverage_digest"],
        "ending_witnesses": verified["witnesses"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def render_ending_coverage_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    verified = replay_ending_coverage(documents, receipt, authorized=authorized)
    rows = "".join(
        "<li>" + escape(w["ending_id"], quote=True) + " — "
        + str(len(w["actions"])) + " authored steps</li>"
        for w in verified["witnesses"])
    missing = "".join(
        "<li>" + escape(name, quote=True) + "</li>"
        for name in verified["uncovered_endings"])
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'none'; style-src 'none'; form-action 'none'; "
        'base-uri \'none\'"><title>Quest ending coverage</title></head>'
        '<body><main><h1>Source-replayed ending coverage</h1><p>Status: '
        + escape(verified["status"], quote=True) + "</p><h2>Witnesses</h2><ol>"
        + rows + "</ol><h2>Uncovered endings</h2><ul>" + missing
        + "</ul><p>Sandbox replay only; native gameplay, external evidence "
        "and release remain unverified.</p></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("ending coverage HTML exceeds byte budget")
    return html


def publish_ending_coverage(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    verified = replay_ending_coverage(documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("ending coverage publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".ending-coverage-" + secrets.token_hex(16) + ".tmp"
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
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        if created:
            os.unlink(temp, dir_fd=fd)
        os.close(fd)
    return {"file": FILENAME, "coverage_digest": verified["coverage_digest"],
            "file_write_performed": True, "release_certified": False}


def restore_ending_coverage(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("ending coverage restore requires authorization")
    fd = _open_directory(directory)
    try:
        inp = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            info = os.fstat(inp)
            if (not stat.S_ISREG(info.st_mode)
                    or not 0 < info.st_size <= MAX_RECEIPT_BYTES):
                raise StudioQuestError("invalid ending coverage evidence file")
            raw = os.read(inp, MAX_RECEIPT_BYTES + 1)
            if len(raw) != info.st_size:
                raise StudioQuestError("ending coverage file changed during read")
        finally:
            os.close(inp)
    finally:
        os.close(fd)
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, entry in pairs:
            if key in value:
                raise StudioQuestError("duplicate ending coverage JSON key")
            value[key] = entry
        return value
    try:
        result = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite ending coverage JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid ending coverage evidence JSON") from exc
    if type(result) is not dict or result.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale or malformed ending coverage evidence")
    return replay_ending_coverage(documents, result, authorized=True)
