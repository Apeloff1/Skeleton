"""Source-leased, bounded quest softlock audit over authored playable quest actions.

This proves an actual terminal branch without a selected authored ending, or
proves its absence only when every reachable branch was examined. It never
claims native engine, environmental, or release qualification.
"""
from __future__ import annotations

from collections import deque
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
    _canonical, _digest, _lease, _open_directory, _write_all,
)

SCHEMA = "skeleton.game_builder.studio_quest_softlock_audit.v1"
PROMPT = "audit authored quest branches for irreversible ending softlocks"
FILENAME = "studio_quest_softlock_audit.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 512 * 1024
MAX_STATES = 2048
MAX_DEPTH = 64
MAX_ENDINGS = 16


def _actions(value: object) -> list[list[str]]:
    if type(value) is not list or len(value) > MAX_DEPTH:
        raise StudioQuestError("invalid bounded softlock prefix")
    result: list[list[str]] = []
    for pair in value:
        if (type(pair) is not list or len(pair) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256
                       or x != x.strip() or any(ord(c) < 32 for c in x)
                       for x in pair)):
            raise StudioQuestError("invalid typed softlock action")
        result.append(list(pair))
    return result


def _authoring(value: object, ending_ids: set[str]) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {
            "initial_actions", "target_endings", "max_states", "max_depth"}
            or len(_canonical(value)) > 32768):
        raise StudioQuestError("invalid bounded softlock authoring")
    states = value["max_states"]
    depth = value["max_depth"]
    if (type(states) is not int or not 1 <= states <= MAX_STATES
            or type(depth) is not int or not 1 <= depth <= MAX_DEPTH):
        raise StudioQuestError("invalid softlock exploration budget")
    actions = _actions(value["initial_actions"])
    if len(actions) > depth:
        raise StudioQuestError("softlock prefix exceeds depth budget")
    names = value["target_endings"]
    if (type(names) is not list or not 1 <= len(names) <= MAX_ENDINGS
            or any(type(name) is not str or name not in ending_ids for name in names)
            or len(set(names)) != len(names)):
        raise StudioQuestError("unknown, duplicate or unbounded target ending")
    return {"initial_actions": actions, "target_endings": names,
            "max_states": states, "max_depth": depth}


def propose_quest_softlock_audit(documents: Mapping[str, Any], prompt: str, *,
                                 authorized: bool, expected_source_digest: str,
                                 expected_initial_session_digest: str) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported softlock audit prompt")
    program = compile_quest_program(documents)
    names = [name for name, _ in program.endings]
    if len(names) > MAX_ENDINGS:
        raise StudioQuestError("too many authored endings for softlock audit")
    return compile_quest_softlock_audit(
        documents, {"initial_actions": [], "target_endings": names,
                    "max_states": 512, "max_depth": min(64, len(program.stages))},
        authorized=authorized, expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)


def compile_quest_softlock_audit(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Enumerate canonical quest actions; unknown coverage is never safe."""
    if authorized is not True:
        raise PermissionError("quest softlock audit requires authorization")
    _lease(expected_source_digest, "softlock source")
    _lease(expected_initial_session_digest, "softlock initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("softlock source exceeds byte budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale softlock source lease")
    plan = _authoring(authoring, {name for name, _ in program.endings})
    initial = replay_quest(documents, plan["initial_actions"], authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale softlock session lease")
    queue: deque[list[list[str]]] = deque([plan["initial_actions"]])
    expanded = 0
    truncated = False
    deadend: dict[str, Any] | None = None
    rescue: dict[str, Any] | None = None
    by_stage = {stage.key: stage for stage in program.stages}
    targets = set(plan["target_endings"])
    while queue:
        if expanded >= plan["max_states"]:
            truncated = True
            break
        actions = queue.popleft()
        session = replay_quest(documents, actions, authorized=True)
        progress = quest_progress(session, documents)
        expanded += 1
        eligible = sorted(targets.intersection(progress["sandbox_endings_eligible"]))
        if eligible:
            if rescue is None:
                rescue = {"actions": actions, "session_digest": session.digest,
                          "eligible_endings": eligible}
            # Authored quest rewards and choice effects are monotonic; once
            # an ending is eligible, no descendant can lose that fact.
            continue
        available = progress["available"]
        if not available:
            if deadend is None:
                deadend = {"actions": actions, "session_digest": session.digest,
                           "unmet_ending_predicates": {
                               key: progress["unmet_ending_predicates"][key]
                               for key in plan["target_endings"]},
                           "terminal": True}
            continue
        if len(actions) >= plan["max_depth"]:
            truncated = True
            continue
        for stage_id in available:
            for alternative in by_stage[stage_id].alternatives:
                if len(queue) >= plan["max_states"] * 8:
                    truncated = True
                    break
                queue.append(actions + [[stage_id, alternative]])
            if truncated:
                break
        if truncated:
            break
    if _canonical(documents) != before:
        raise StudioQuestError("quest source changed during softlock audit")
    status = ("softlock_proven" if deadend is not None else
              "inconclusive" if truncated else "no_softlock_in_exhaustive_search")
    payload: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "initial_session_digest": initial.digest, "authoring": plan,
        "status": status, "search_exhaustive": not truncated and not queue,
        "expanded_states": expanded, "terminal_softlock_witness": deadend,
        "safe_ending_witness": rescue,
        "playable_handoff_allowed": status == "no_softlock_in_exhaustive_search"
            and rescue is not None,
        "source_replay_verified": True, "native_gameplay_verified": False,
        "external_evidence_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("softlock audit receipt exceeds byte budget")
    payload["audit_digest"] = _digest(payload)
    return payload


def replay_quest_softlock_audit(documents: Mapping[str, Any], receipt: object, *,
                                authorized: bool) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest softlock replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid quest softlock receipt")
    checked = compile_quest_softlock_audit(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("quest softlock receipt failed canonical replay")
    return checked


def compile_quest_softlock_handoff(documents: Mapping[str, Any],
                                   receipt: object, *, authorized: bool) -> dict[str, Any]:
    checked = replay_quest_softlock_audit(documents, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("unproved quest softlock safety blocks playable handoff")
    witness = checked["safe_ending_witness"]
    session = replay_quest(documents, witness["actions"], authorized=True)
    if session.digest != witness["session_digest"]:
        raise StudioQuestError("softlock handoff witness replay drift")
    progress = quest_progress(session, documents)
    if not set(witness["eligible_endings"]).issubset(progress["sandbox_endings_eligible"]):
        raise StudioQuestError("softlock handoff lacks authored ending")
    result = {
        "schema": "skeleton.game_builder.studio_quest_softlock_handoff.v1",
        "audit_digest": checked["audit_digest"],
        "quest_source_digest": checked["source_digest"],
        "quest_session_digest": session.digest,
        "ending_ids": witness["eligible_endings"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def render_quest_softlock_html(documents: Mapping[str, Any], receipt: object,
                               *, authorized: bool) -> bytes:
    checked = replay_quest_softlock_audit(documents, receipt, authorized=authorized)
    witness = checked["terminal_softlock_witness"]
    steps = "".join(
        "<li>" + escape(stage, quote=True) + " → " + escape(choice, quote=True)
        + "</li>" for stage, choice in (witness["actions"] if witness else []))
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "\'none\'; script-src \'none\'; style-src \'none\'; "
        'form-action \'none\'; base-uri \'none\'">'
        "<title>Quest softlock audit</title></head><body><main>"
        "<h1>Source-replayed quest softlock audit</h1><p>Status: "
        + escape(checked["status"], quote=True) + "</p><p>Explored: "
        + str(checked["expanded_states"]) + "</p><ol>" + steps
        + "</ol><p>Sandbox authored quest proof only. Native gameplay and "
        "release are not verified.</p></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("softlock HTML exceeds byte budget")
    return html


def publish_quest_softlock_audit(documents: Mapping[str, Any], receipt: object,
                                 directory: Path, *, authorized: bool) -> dict[str, Any]:
    checked = replay_quest_softlock_audit(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("softlock publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".softlock-" + secrets.token_hex(16) + ".tmp"
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
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "audit_digest": checked["audit_digest"], "bytes": len(raw),
            "file_write_performed": True, "release_certified": False}


def restore_quest_softlock_audit(documents: Mapping[str, Any], directory: Path, *,
                                 authorized: bool, expected_source_digest: str) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest softlock restore requires authorization")
    _lease(expected_source_digest, "softlock restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_RECEIPT_BYTES
                    or (os.name == "posix"
                        and (before.st_uid != os.getuid() or before.st_mode & 0o077
                             or before.st_nlink != 1))):
                raise StudioQuestError("softlock receipt must be private")
            raw = os.read(handle, MAX_RECEIPT_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_ino) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                     before.st_ino)):
                raise StudioQuestError("softlock receipt changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate softlock JSON key")
            result[key] = value
        return result
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite softlock JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid softlock receipt JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale softlock restore source")
    return replay_quest_softlock_audit(documents, receipt, authorized=True)
